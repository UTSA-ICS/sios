# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2012, Red Hat, Inc.
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

from oslo.config import cfg
import qpid.messaging

from sios.notifier import strategy
import sios.openstack.common.log as logging

LOG = logging.getLogger(__name__)

qpid_opts = [
    cfg.StrOpt('qpid_notification_exchange',
               default='sios',
               help='Qpid exchange for notifications'),
    cfg.StrOpt('qpid_notification_topic',
               default='notifications',
               help='Qpid topic for notifications'),
    cfg.StrOpt('qpid_hostname',
               default='localhost',
               help='Qpid broker hostname'),
    cfg.StrOpt('qpid_port',
               default='5672',
               help='Qpid broker port'),
    cfg.StrOpt('qpid_username',
               default='',
               help='Username for qpid connection'),
    cfg.StrOpt('qpid_password',
               default='',
               help='Password for qpid connection',
               secret=True),
    cfg.StrOpt('qpid_sasl_mechanisms',
               default='',
               help='Space separated list of SASL mechanisms to use for auth'),
    cfg.IntOpt('qpid_reconnect_timeout',
               default=0,
               help='Reconnection timeout in seconds'),
    cfg.IntOpt('qpid_reconnect_limit',
               default=0,
               help='Max reconnections before giving up'),
    cfg.IntOpt('qpid_reconnect_interval_min',
               default=0,
               help='Minimum seconds between reconnection attempts'),
    cfg.IntOpt('qpid_reconnect_interval_max',
               default=0,
               help='Maximum seconds between reconnection attempts'),
    cfg.IntOpt('qpid_reconnect_interval',
               default=0,
               help='Equivalent to setting max and min to the same value'),
    cfg.IntOpt('qpid_heartbeat',
               default=60,
               help='Seconds between connection keepalive heartbeats'),
    cfg.StrOpt('qpid_protocol',
               default='tcp',
               help="Transport to use, either 'tcp' or 'ssl'"),
    cfg.BoolOpt('qpid_tcp_nodelay',
                default=True,
                help='Disable Nagle algorithm'),
]

CONF = cfg.CONF
CONF.register_opts(qpid_opts)


class QpidStrategy(strategy.Strategy):
    """A notifier that puts a message on a queue when called."""

    def _open_connection(self):
        """Initialize the Qpid notification strategy."""
        broker = CONF.qpid_hostname + ":" + CONF.qpid_port
        self.connection = qpid.messaging.Connection(broker)
        self.connection.username = CONF.qpid_username
        self.connection.password = CONF.qpid_password
        self.connection.sasl_mechanisms = CONF.qpid_sasl_mechanisms
        # Hard code this option as enabled so that reconnect logic isn't needed
        # in this file at all.
        self.connection.reconnect = True
        if CONF.qpid_reconnect_timeout:
            self.connection.reconnect_timeout = CONF.qpid_reconnect_timeout
        if CONF.qpid_reconnect_limit:
            self.connection.reconnect_limit = CONF.qpid_reconnect_limit
        if CONF.qpid_reconnect_interval_max:
            self.connection.reconnect_interval_max = (
                                        CONF.qpid_reconnect_interval_max)
        if CONF.qpid_reconnect_interval_min:
            self.connection.reconnect_interval_min = (
                                        CONF.qpid_reconnect_interval_min)
        if CONF.qpid_reconnect_interval:
            self.connection.reconnect_interval = CONF.qpid_reconnect_interval
        self.connection.heartbeat = CONF.qpid_heartbeat
        self.connection.protocol = CONF.qpid_protocol
        self.connection.tcp_nodelay = CONF.qpid_tcp_nodelay
        self.connection.open()
        LOG.info(_('Connected to AMQP server on %s') % broker)

    def _send(self, priority, msg):
        addr_opts = {
            "create": "always",
            "node": {
                "type": "topic",
                "x-declare": {
                    "durable": False,
                    # auto-delete isn't implemented for exchanges in qpid,
                    # but put in here anyway
                    "auto-delete": True,
                },
            },
        }
        topic = "%s.%s" % (CONF.qpid_notification_topic, priority)
        address = "%s/%s ; %s" % (CONF.qpid_notification_exchange, topic,
                                  json.dumps(addr_opts))

        try:
            self.connection = None
            self._open_connection()
            session = self.connection.session()
            sender = session.sender(address)
            qpid_msg = qpid.messaging.Message(content=msg)
            sender.send(qpid_msg)
        except Exception:
            details = dict(priority=priority, msg=msg)
            LOG.exception(_('Notification error.  Priority: %(priority)s '
                            'Message: %(msg)s' % details))
            raise
        finally:
            if self.connection and self.connection.opened():
                self.connection.close()

    def warn(self, msg):
        self._send('warn', msg)

    def info(self, msg):
        self._send('info', msg)

    def error(self, msg):
        self._send('error', msg)
