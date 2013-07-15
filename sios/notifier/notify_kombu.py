# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2011, OpenStack LLC.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.


import json
import time

import kombu.connection
import kombu.entity
from oslo.config import cfg

from sios.notifier import strategy
import sios.openstack.common.log as logging

LOG = logging.getLogger(__name__)

rabbit_opts = [
    cfg.StrOpt('rabbit_host', default='localhost',
               help=_('The host name of the rabbitmq server')),
    cfg.IntOpt('rabbit_port', default=5672,
               help=_('The port on which the rabbitmq server is listening')),
    cfg.BoolOpt('rabbit_use_ssl', default=False,
                help=_('A boolean value indicating if the selected rabbitmq '
                       'server uses SSL.')),
    cfg.StrOpt('rabbit_userid', default='guest',
               help=_('The user ID for authentication with rabbitmq.')),
    cfg.StrOpt('rabbit_password', default='guest', secret=True,
               help=_('The password that will be used for authentication '
                      'with the rabbitmq server.')),
    cfg.StrOpt('rabbit_virtual_host', default='/',
               help=_('The virtual host used in the rabbitmq connection.')),
    cfg.StrOpt('rabbit_notification_exchange', default='sios',
               help=_('Exchange name to use for connection when using rabbit'
               ' strategy.')),
    cfg.StrOpt('rabbit_notification_topic', default='notifications',
               help=_('Topic to use for connection when using rabbit '
               'strategy.')),
    cfg.IntOpt('rabbit_max_retries', default=0,
               help=_('The maximum number of times to attempt to connect to '
                      'the AMQP server.')),
    cfg.StrOpt('rabbit_retry_backoff', default=2,
               help=_('This value multiplied by the number of connection '
                      'attempts gives the amount of time in seconds to sleep '
                      'between connection attempts to the AMQP server.')),
    cfg.StrOpt('rabbit_retry_max_backoff', default=30,
               help=_('The maximum amount of time to wait between connection '
                      'attempts.  The delay time will be the smaller of this '
                      'value and the value of <rabbit_retry_backoff> * '
                      '<the number of failed connection attempts so far>.')),
    cfg.BoolOpt('rabbit_durable_queues', default=False,
                help='A boolean to determine if the queues used for messaging '
                     'should be retained after a restart.'),
]

CONF = cfg.CONF
CONF.register_opts(rabbit_opts)


class KombuMaxRetriesReached(Exception):
    pass


class RabbitStrategy(strategy.Strategy):
    """A notifier that puts a message on a queue when called."""

    def __init__(self):
        """Initialize the rabbit notification strategy."""
        self.topic = CONF.rabbit_notification_topic
        self.max_retries = CONF.rabbit_max_retries
        # NOTE(comstud): When reading the config file, these values end
        # up being strings, and we need them as ints.
        self.retry_backoff = int(CONF.rabbit_retry_backoff)
        self.retry_max_backoff = int(CONF.rabbit_retry_max_backoff)

        self.connection = None
        self.retry_attempts = 0
        try:
            self.reconnect()
        except KombuMaxRetriesReached:
            pass

    def _close(self):
        """Close connection to rabbit."""
        try:
            self.connection.close()
        except self.connection_errors:
            pass
        self.connection = None

    def _connect(self):
        """Connect to rabbit.  Exceptions should be handled by the
        caller.
        """
        log_info = {}
        log_info['hostname'] = CONF.rabbit_host
        log_info['port'] = CONF.rabbit_port
        if self.connection:
            LOG.info(_("Reconnecting to AMQP server on "
                       "%(hostname)s:%(port)d") % log_info)
            self._close()
        else:
            LOG.info(_("Connecting to AMQP server on "
                       "%(hostname)s:%(port)d") % log_info)
        self.connection = kombu.connection.BrokerConnection(
                hostname=CONF.rabbit_host,
                port=CONF.rabbit_port,
                userid=CONF.rabbit_userid,
                password=CONF.rabbit_password,
                virtual_host=CONF.rabbit_virtual_host,
                ssl=CONF.rabbit_use_ssl)
        self.connection_errors = self.connection.connection_errors
        self.connection.connect()
        self.channel = self.connection.channel()
        self.exchange = kombu.entity.Exchange(
                channel=self.channel,
                type="topic",
                durable=CONF.rabbit_durable_queues,
                name=CONF.rabbit_notification_exchange)

        # NOTE(jerdfelt): Normally the consumer would create the queues,
        # but we do this to ensure that messages don't get dropped if the
        # consumer is started after we do
        for priority in ["WARN", "INFO", "ERROR"]:
            routing_key = "%s.%s" % (self.topic, priority.lower())
            queue = kombu.entity.Queue(
                    channel=self.channel,
                    exchange=self.exchange,
                    durable=CONF.rabbit_durable_queues,
                    name=routing_key,
                    routing_key=routing_key)
            queue.declare()
        LOG.info(_("Connected to AMQP server on "
                   "%(hostname)s:%(port)d") % log_info)

    def reconnect(self):
        """Handles reconnecting and re-establishing queues."""
        while True:
            self.retry_attempts += 1
            try:
                self._connect()
                return
            except self.connection_errors as e:
                pass
            except Exception as e:
                # NOTE(comstud): Unfortunately it's possible for amqplib
                # to return an error not covered by its transport
                # connection_errors in the case of a timeout waiting for
                # a protocol response.  (See paste link in LP888621 for
                # nova.)  So, we check all exceptions for 'timeout' in them
                # and try to reconnect in this case.
                if 'timeout' not in str(e):
                    raise

            log_info = {}
            log_info['err_str'] = str(e)
            log_info['max_retries'] = self.max_retries
            log_info['hostname'] = CONF.rabbit_host
            log_info['port'] = CONF.rabbit_port

            if self.retry_attempts >= self.max_retries:
                LOG.exception(_('Unable to connect to AMQP server on '
                                '%(hostname)s:%(port)d after %(max_retries)d '
                                'tries: %(err_str)s') % log_info)
                if self.connection:
                    self._close()
                raise KombuMaxRetriesReached

            sleep_time = self.retry_backoff * self.retry_attempts
            if self.retry_max_backoff:
                sleep_time = min(sleep_time, self.retry_max_backoff)

            log_info['sleep_time'] = sleep_time
            LOG.exception(_('AMQP server on %(hostname)s:%(port)d is'
                            ' unreachable: %(err_str)s. Trying again in '
                            '%(sleep_time)d seconds.') % log_info)
            time.sleep(sleep_time)

    def log_failure(self, msg, priority):
        """Fallback to logging when we can't send to rabbit."""
        message = _('Notification with priority %(priority)s failed: '
                    'msg=%(msg)s')
        LOG.error(message % {'msg': msg, 'priority': priority})

    def _send_message(self, msg, routing_key):
        """Send a message.  Caller needs to catch exceptions for retry."""
        msg = self.exchange.Message(json.dumps(msg),
                                    content_type='application/json')
        self.exchange.publish(msg, routing_key=routing_key)

    def _notify(self, msg, priority):
        """Send a notification and retry if needed."""
        self.retry_attempts = 0

        if not self.connection:
            try:
                self.reconnect()
            except KombuMaxRetriesReached:
                self.log_failure(msg, priority)
                return

        routing_key = "%s.%s" % (self.topic, priority.lower())

        while True:
            try:
                self._send_message(msg, routing_key)
                return
            except self.connection_errors as e:
                pass
            except Exception as e:
                # NOTE(comstud): Unfortunately it's possible for amqplib
                # to return an error not covered by its transport
                # connection_errors in the case of a timeout waiting for
                # a protocol response.  (See paste link in LP888621 for
                # nova.)  So, we check all exceptions for 'timeout' in them
                # and try to reconnect in this case.
                if 'timeout' not in str(e):
                    raise

            LOG.exception(_("Unable to send notification: %s") % str(e))

            try:
                self.reconnect()
            except KombuMaxRetriesReached:
                break
        self.log_failure(msg, priority)

    def warn(self, msg):
        self._notify(msg, "WARN")

    def info(self, msg):
        self._notify(msg, "INFO")

    def error(self, msg):
        self._notify(msg, "ERROR")
