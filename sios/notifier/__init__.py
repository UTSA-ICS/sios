# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2011, OpenStack LLC.
# Copyright 2012, Red Hat, Inc.
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


import socket
import uuid

from oslo.config import cfg

from sios.common import exception
from sios.openstack.common import importutils
import sios.openstack.common.log as logging
from sios.openstack.common import timeutils

notifier_opts = [
    cfg.StrOpt('notifier_strategy', default='default',
               help=_('Notifications can be sent when images are create, '
                      'updated or deleted. There are three methods of sending '
                      'notifications, logging (via the log_file directive), '
                      'rabbit (via a rabbitmq queue), qpid (via a Qpid '
                      'message queue), or noop (no notifications sent, the '
                      'default).'))
]

CONF = cfg.CONF
CONF.register_opts(notifier_opts)

LOG = logging.getLogger(__name__)

_STRATEGY_ALIASES = {
    "logging": "sios.notifier.notify_log.LoggingStrategy",
    "rabbit": "sios.notifier.notify_kombu.RabbitStrategy",
    "qpid": "sios.notifier.notify_qpid.QpidStrategy",
    "noop": "sios.notifier.notify_noop.NoopStrategy",
    "default": "sios.notifier.notify_noop.NoopStrategy",
}


class Notifier(object):
    """Uses a notification strategy to send out messages about events."""

    def __init__(self, strategy=None):
        _strategy = CONF.notifier_strategy
        try:
            strategy = _STRATEGY_ALIASES[_strategy]
            msg = _('Converted strategy alias %s to %s')
            LOG.debug(msg % (_strategy, strategy))
        except KeyError:
            strategy = _strategy
            LOG.debug(_('No strategy alias found for %s') % strategy)

        try:
            strategy_class = importutils.import_class(strategy)
        except ImportError:
            raise exception.InvalidNotifierStrategy(strategy=strategy)
        else:
            self.strategy = strategy_class()

    @staticmethod
    def generate_message(event_type, priority, payload):
        return {
            "message_id": str(uuid.uuid4()),
            "publisher_id": socket.gethostname(),
            "event_type": event_type,
            "priority": priority,
            "payload": payload,
            "timestamp": str(timeutils.utcnow()),
        }

    def warn(self, event_type, payload):
        msg = self.generate_message(event_type, "WARN", payload)
        self.strategy.warn(msg)

    def info(self, event_type, payload):
        msg = self.generate_message(event_type, "INFO", payload)
        self.strategy.info(msg)

    def error(self, event_type, payload):
        msg = self.generate_message(event_type, "ERROR", payload)
        self.strategy.error(msg)



