# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2010 United States Government as represented by the
# Administrator of the National Aeronautics and Space Administration.
# Copyright 2010 OpenStack LLC.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

"""
Utility methods for working with WSGI servers
"""

import datetime
import errno
import json
import logging
import os
import signal
import sys
import time

import eventlet
from eventlet.green import socket, ssl
import eventlet.greenio
import eventlet.wsgi
from oslo.config import cfg
import routes
import routes.middleware
import webob.dec
import webob.exc

from sios.common import exception
from sios.common import utils
import sios.openstack.common.log as os_logging


bind_opts = [
    cfg.StrOpt('bind_host', default='0.0.0.0',
               help=_('Address to bind the server.  Useful when '
                      'selecting a particular network interface.')),
    cfg.IntOpt('bind_port',
               help=_('The port on which the server will listen.')),
]

socket_opts = [
    cfg.IntOpt('backlog', default=4096,
               help=_('The backlog value that will be used when creating the '
                      'TCP listener socket.')),
    cfg.IntOpt('tcp_keepidle', default=600,
               help=_('The value for the socket option TCP_KEEPIDLE.  This is'
                      'the time in seconds that the connection must be idle '
                      'before TCP starts sending keepalive probes.')),
    cfg.StrOpt('ca_file', help=_('CA certificate file to use to verify '
                                 'connecting clients.')),
    cfg.StrOpt('cert_file', help=_('Certificate file to use when starting API '
                                   'server securely.')),
    cfg.StrOpt('key_file', help=_('Private key file to use when starting API '
                                  'server securely.')),
]

eventlet_opts = [
    cfg.IntOpt('workers', default=1,
               help=_('The number of child process workers that will be '
                      'created to service API requests.')),
    cfg.StrOpt('eventlet_hub', default='poll',
               help=_('Name of eventlet hub to use. Traditionally, we have '
                      'only supported \'poll\', however \'selects\' may be '
                      'appropriate for some platforms. See '
                      'http://eventlet.net/doc/hubs.html for more details.')),
]


CONF = cfg.CONF
CONF.register_opts(bind_opts)
CONF.register_opts(socket_opts)
CONF.register_opts(eventlet_opts)


class WritableLogger(object):
    """A thin wrapper that responds to `write` and logs."""

    def __init__(self, logger, level=logging.DEBUG):
        self.logger = logger
        self.level = level

    def write(self, msg):
        self.logger.log(self.level, msg.strip("\n"))


def get_bind_addr(default_port=None):
    """Return the host and port to bind to."""
    return (CONF.bind_host, CONF.bind_port or default_port)


def get_socket(default_port):
    """
    Bind socket to bind ip:port in conf

    note: Mostly comes from Swift with a few small changes...

    :param default_port: port to bind to if none is specified in conf

    :returns : a socket object as returned from socket.listen or
               ssl.wrap_socket if conf specifies cert_file
    """
    bind_addr = get_bind_addr(default_port)

    # TODO(jaypipes): eventlet's greened socket module does not actually
    # support IPv6 in getaddrinfo(). We need to get around this in the
    # future or monitor upstream for a fix
    address_family = [
        addr[0] for addr in socket.getaddrinfo(bind_addr[0],
                                               bind_addr[1],
                                               socket.AF_UNSPEC,
                                               socket.SOCK_STREAM)
        if addr[0] in (socket.AF_INET, socket.AF_INET6)
    ][0]

    cert_file = CONF.cert_file
    key_file = CONF.key_file
    use_ssl = cert_file or key_file
    if use_ssl and (not cert_file or not key_file):
        raise RuntimeError(_("When running server in SSL mode, you must "
                             "specify both a cert_file and key_file "
                             "option value in your configuration file"))

    def wrap_ssl(sock):
        utils.validate_key_cert(key_file, cert_file)

        ssl_kwargs = {
            'server_side': True,
            'certfile': cert_file,
            'keyfile': key_file,
            'cert_reqs': ssl.CERT_NONE,
        }

        if CONF.ca_file:
            ssl_kwargs['ca_certs'] = CONF.ca_file
            ssl_kwargs['cert_reqs'] = ssl.CERT_REQUIRED

        return ssl.wrap_socket(sock, **ssl_kwargs)

    sock = utils.get_test_suite_socket()
    retry_until = time.time() + 30

    if sock and use_ssl:
        sock = wrap_ssl(sock)
    while not sock and time.time() < retry_until:
        try:
            sock = eventlet.listen(bind_addr,
                                   backlog=CONF.backlog,
                                   family=address_family)
            if use_ssl:
                sock = wrap_ssl(sock)

        except socket.error as err:
            if err.args[0] != errno.EADDRINUSE:
                raise
            eventlet.sleep(0.1)
    if not sock:
        raise RuntimeError(_("Could not bind to %s:%s after trying for 30 "
                             "seconds") % bind_addr)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    # in my experience, sockets can hang around forever without keepalive
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)

    # This option isn't available in the OS X version of eventlet
    if hasattr(socket, 'TCP_KEEPIDLE'):
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE,
                        CONF.tcp_keepidle)

    return sock


class Server(object):
    """Server class to manage multiple WSGI sockets and applications."""

    def __init__(self, threads=1000):
        self.threads = threads
        self.children = []
        self.running = True

    def start(self, application, default_port):
        """
        Run a WSGI server with the given application.

        :param application: The application to be run in the WSGI server
        :param default_port: Port to bind to if none is specified in conf
        """
        pgid = os.getpid()
        try:
            # NOTE(flaper87): Make sure this process
            # runs in its own process group.
            os.setpgid(pgid, pgid)
        except OSError:
            # NOTE(flaper87): When running sios-control,
            # (sios's functional tests, for example)
            # setpgid fails with EPERM as sios-control
            # creates a fresh session, of which the newly
            # launched service becomes the leader (session
            # leaders may not change process groups)
            #
            # Running sios-(api|registry) is safe and
            # shouldn't raise any error here.
            pgid = 0

        def kill_children(*args):
            """Kills the entire process group."""
            signal.signal(signal.SIGTERM, signal.SIG_IGN)
            signal.signal(signal.SIGINT, signal.SIG_IGN)
            self.running = False
            os.killpg(pgid, signal.SIGTERM)

        def hup(*args):
            """
            Shuts down the server, but allows running requests to complete
            """
            signal.signal(signal.SIGHUP, signal.SIG_IGN)
            self.running = False

        self.application = application
        self.sock = get_socket(default_port)

        os.umask(0o27)  # ensure files are created with the correct privileges
        self.logger = os_logging.getLogger('eventlet.wsgi.server')

        if CONF.workers == 0:
            # Useful for profiling, test, debug etc.
            self.pool = self.create_pool()
            self.pool.spawn_n(self._single_run, self.application, self.sock)
            return
        else:
            self.logger.info(_("Starting %d workers") % CONF.workers)
            signal.signal(signal.SIGTERM, kill_children)
            signal.signal(signal.SIGINT, kill_children)
            signal.signal(signal.SIGHUP, hup)
            while len(self.children) < CONF.workers:
                self.run_child()

    def create_pool(self):
        return eventlet.GreenPool(size=self.threads)

    def wait_on_children(self):
        while self.running:
            try:
                pid, status = os.wait()
                if os.WIFEXITED(status) or os.WIFSIGNALED(status):
                    self.logger.info(_('Removing dead child %s') % pid)
                    self.children.remove(pid)
                    if os.WIFEXITED(status) and os.WEXITSTATUS(status) != 0:
                        self.logger.error(_('Not respawning child %d, cannot '
                                            'recover from termination') % pid)
                        if not self.children:
                            self.logger.info(
                                _('All workers have terminated. Exiting'))
                            self.running = False
                    else:
                        self.run_child()
            except OSError as err:
                if err.errno not in (errno.EINTR, errno.ECHILD):
                    raise
            except KeyboardInterrupt:
                self.logger.info(_('Caught keyboard interrupt. Exiting.'))
                break
        eventlet.greenio.shutdown_safe(self.sock)
        self.sock.close()
        self.logger.debug(_('Exited'))

    def wait(self):
        """Wait until all servers have completed running."""
        try:
            if self.children:
                self.wait_on_children()
            else:
                self.pool.waitall()
        except KeyboardInterrupt:
            pass

    def run_child(self):
        pid = os.fork()
        if pid == 0:
            signal.signal(signal.SIGHUP, signal.SIG_DFL)
            signal.signal(signal.SIGTERM, signal.SIG_DFL)
            # ignore the interrupt signal to avoid a race whereby
            # a child worker receives the signal before the parent
            # and is respawned unneccessarily as a result
            signal.signal(signal.SIGINT, signal.SIG_IGN)
            self.run_server()
            self.logger.info(_('Child %d exiting normally') % os.getpid())
            # self.pool.waitall() has been called by run_server, so
            # its safe to exit here
            sys.exit(0)
        else:
            self.logger.info(_('Started child %s') % pid)
            self.children.append(pid)

    def run_server(self):
        """Run a WSGI server."""
        if cfg.CONF.pydev_worker_debug_host:
            utils.setup_remote_pydev_debug(cfg.CONF.pydev_worker_debug_host,
                                           cfg.CONF.pydev_worker_debug_port)

        eventlet.wsgi.HttpProtocol.default_request_version = "HTTP/1.0"
        try:
            eventlet.hubs.use_hub(cfg.CONF.eventlet_hub)
        except Exception:
            msg = _("eventlet '%s' hub is not available on this platform")
            raise exception.WorkerCreationFailure(
                reason=msg % cfg.CONF.eventlet_hub)
        self.pool = self.create_pool()
        try:
            eventlet.wsgi.server(self.sock,
                                 self.application,
                                 log=WritableLogger(self.logger),
                                 custom_pool=self.pool,
                                 debug=False)
        except socket.error as err:
            if err[0] != errno.EINVAL:
                raise
        self.pool.waitall()

    def _single_run(self, application, sock):
        """Start a WSGI server in a new green thread."""
        self.logger.info(_("Starting single process server"))
        eventlet.wsgi.server(sock, application, custom_pool=self.pool,
                             log=WritableLogger(self.logger), debug=False)


class Middleware(object):
    """
    Base WSGI middleware wrapper. These classes require an application to be
    initialized that will be called next.  By default the middleware will
    simply call its wrapped app, or you can override __call__ to customize its
    behavior.
    """

    def __init__(self, application):
        self.application = application

    @classmethod
    def factory(cls, global_conf, **local_conf):
        def filter(app):
            return cls(app)
        return filter

    def process_request(self, req):
        """
        Called on each request.

        If this returns None, the next application down the stack will be
        executed. If it returns a response then that response will be returned
        and execution will stop here.

        """
        return None

    def process_response(self, response):
        """Do whatever you'd like to the response."""
        return response

    @webob.dec.wsgify
    def __call__(self, req):
        response = self.process_request(req)
        if response:
            return response
        response = req.get_response(self.application)
        response.request = req
        return self.process_response(response)


class Debug(Middleware):
    """
    Helper class that can be inserted into any WSGI application chain
    to get information about the request and response.
    """

    @webob.dec.wsgify
    def __call__(self, req):
        print ("*" * 40) + " REQUEST ENVIRON"
        for key, value in req.environ.items():
            print key, "=", value
        print
        resp = req.get_response(self.application)

        print ("*" * 40) + " RESPONSE HEADERS"
        for (key, value) in resp.headers.iteritems():
            print key, "=", value
        print

        resp.app_iter = self.print_generator(resp.app_iter)

        return resp

    @staticmethod
    def print_generator(app_iter):
        """
        Iterator that prints the contents of a wrapper string iterator
        when iterated.
        """
        print ("*" * 40) + " BODY"
        for part in app_iter:
            sys.stdout.write(part)
            sys.stdout.flush()
            yield part
        print


class APIMapper(routes.Mapper):
    """
    Handle route matching when url is '' because routes.Mapper returns
    an error in this case.
    """

    def routematch(self, url=None, environ=None):
        if url is "":
            result = self._match("", environ)
            return result[0], result[1]
        return routes.Mapper.routematch(self, url, environ)


class Router(object):
    """
    WSGI middleware that maps incoming requests to WSGI apps.
    """

    def __init__(self, mapper):
        """
        Create a router for the given routes.Mapper.

        Each route in `mapper` must specify a 'controller', which is a
        WSGI app to call.  You'll probably want to specify an 'action' as
        well and have your controller be a wsgi.Controller, who will route
        the request to the action method.

        Examples:
          mapper = routes.Mapper()
          sc = ServerController()

          # Explicit mapping of one route to a controller+action
          mapper.connect(None, "/svrlist", controller=sc, action="list")

          # Actions are all implicitly defined
          mapper.resource("server", "servers", controller=sc)

          # Pointing to an arbitrary WSGI app.  You can specify the
          # {path_info:.*} parameter so the target app can be handed just that
          # section of the URL.
          mapper.connect(None, "/v1.0/{path_info:.*}", controller=BlogApp())
        """
        mapper.redirect("", "/")
        self.map = mapper
        self._router = routes.middleware.RoutesMiddleware(self._dispatch,
                                                          self.map)

    @classmethod
    def factory(cls, global_conf, **local_conf):
        return cls(APIMapper())

    @webob.dec.wsgify
    def __call__(self, req):
        """
        Route the incoming request to a controller based on self.map.
        If no match, return a 404.
        """
        return self._router

    @staticmethod
    @webob.dec.wsgify
    def _dispatch(req):
        """
        Called by self._router after matching the incoming request to a route
        and putting the information into req.environ.  Either returns 404
        or the routed WSGI app's response.
        """
        match = req.environ['wsgiorg.routing_args'][1]
        if not match:
            return webob.exc.HTTPNotFound()
        app = match['controller']
        return app


class Request(webob.Request):
    """Add some Openstack API-specific logic to the base webob.Request."""

    def best_match_content_type(self):
        """Determine the requested response content-type."""
        supported = ('application/json',)
        bm = self.accept.best_match(supported)
        return bm or 'application/json'

    def get_content_type(self, allowed_content_types):
        """Determine content type of the request body."""
        if "Content-Type" not in self.headers:
            raise exception.InvalidContentType(content_type=None)

        content_type = self.content_type

        if content_type not in allowed_content_types:
            raise exception.InvalidContentType(content_type=content_type)
        else:
            return content_type


class JSONRequestDeserializer(object):
    def has_body(self, request):
        """
        Returns whether a Webob.Request object will possess an entity body.

        :param request:  Webob.Request object
        """
        if 'transfer-encoding' in request.headers:
            return True
        elif request.content_length > 0:
            return True

        return False

    def _sanitizer(self, obj):
        """Sanitizer method that will be passed to json.loads."""
        return obj

    def from_json(self, datastring):
        try:
            return json.loads(datastring, object_hook=self._sanitizer)
        except ValueError:
            msg = _('Malformed JSON in request body.')
            raise webob.exc.HTTPBadRequest(explanation=msg)

    def default(self, request):
        if self.has_body(request):
            return {'body': self.from_json(request.body)}
        else:
            return {}


class JSONResponseSerializer(object):

    def _sanitizer(self, obj):
        """Sanitizer method that will be passed to json.dumps."""
        if isinstance(obj, datetime.datetime):
            return obj.isoformat()
        if hasattr(obj, "to_dict"):
            return obj.to_dict()
        return obj

    def to_json(self, data):
        return json.dumps(data, default=self._sanitizer)

    def default(self, response, result):
        response.content_type = 'application/json'
        response.body = self.to_json(result)


class Resource(object):
    """
    WSGI app that handles (de)serialization and controller dispatch.

    Reads routing information supplied by RoutesMiddleware and calls
    the requested action method upon its deserializer, controller,
    and serializer. Those three objects may implement any of the basic
    controller action methods (create, update, show, index, delete)
    along with any that may be specified in the api router. A 'default'
    method may also be implemented to be used in place of any
    non-implemented actions. Deserializer methods must accept a request
    argument and return a dictionary. Controller methods must accept a
    request argument. Additionally, they must also accept keyword
    arguments that represent the keys returned by the Deserializer. They
    may raise a webob.exc exception or return a dict, which will be
    serialized by requested content type.
    """

    def __init__(self, controller, deserializer=None, serializer=None):
        """
        :param controller: object that implement methods created by routes lib
        :param deserializer: object that supports webob request deserialization
                             through controller-like actions
        :param serializer: object that supports webob response serialization
                           through controller-like actions
        """
        self.controller = controller
        self.serializer = serializer or JSONResponseSerializer()
        self.deserializer = deserializer or JSONRequestDeserializer()

    @webob.dec.wsgify(RequestClass=Request)
    def __call__(self, request):
        """WSGI method that controls (de)serialization and method dispatch."""
        action_args = self.get_action_args(request.environ)
        action = action_args.pop('action', None)

        deserialized_request = self.dispatch(self.deserializer,
                                             action, request)
        action_args.update(deserialized_request)

        action_result = self.dispatch(self.controller, action,
                                      request, **action_args)
        try:
            response = webob.Response(request=request)
            self.dispatch(self.serializer, action, response, action_result)
            return response

        # return unserializable result (typically a webob exc)
        except Exception:
            return action_result

    def dispatch(self, obj, action, *args, **kwargs):
        """Find action-specific method on self and call it."""
        try:
            method = getattr(obj, action)
        except AttributeError:
            method = getattr(obj, 'default')

        return method(*args, **kwargs)

    def get_action_args(self, request_environment):
        """Parse dictionary created by routes library."""
        try:
            args = request_environment['wsgiorg.routing_args'][1].copy()
        except Exception:
            return {}

        try:
            del args['controller']
        except KeyError:
            pass

        try:
            del args['format']
        except KeyError:
            pass

        return args
