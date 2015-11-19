# Copyright 2011, OpenStack Foundation
# Copyright 2012, Red Hat, Inc.
# Copyright 2013 IBM Corp.
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

import abc

from oslo_config import cfg
from oslo_log import log as logging
import oslo_messaging
from oslo_utils import excutils
from oslo_utils import timeutils
import six
import webob

from glance.common import exception
from glance.common import utils
from glance import i18n

_ = i18n._
_LE = i18n._LE

notifier_opts = [
    cfg.StrOpt('default_publisher_id', default="image.localhost",
               help='Default publisher_id for outgoing notifications.'),
    cfg.ListOpt('disabled_notifications', default=[],
                help='List of disabled notifications. A notification can be '
                     'given either as a notification type to disable a single '
                     'event, or as a notification group prefix to disable all '
                     'events within a group. Example: if this config option '
                     'is set to ["image.create", "metadef_namespace"], then '
                     '"image.create" notification will not be sent after '
                     'image is created and none of the notifications for '
                     'metadefinition namespaces will be sent.'),
]

CONF = cfg.CONF
CONF.register_opts(notifier_opts)

LOG = logging.getLogger(__name__)

_ALIASES = {
    'glance.openstack.common.rpc.impl_kombu': 'rabbit',
    'glance.openstack.common.rpc.impl_qpid': 'qpid',
    'glance.openstack.common.rpc.impl_zmq': 'zmq',
}


def get_transport():
    return oslo_messaging.get_transport(CONF, aliases=_ALIASES)


class Notifier(object):
    """Uses a notification strategy to send out messages about events."""

    def __init__(self):
        publisher_id = CONF.default_publisher_id
        self._transport = get_transport()
        self._notifier = oslo_messaging.Notifier(self._transport,
                                                 publisher_id=publisher_id)

    def warn(self, event_type, payload):
        self._notifier.warn({}, event_type, payload)

    def info(self, event_type, payload):
        self._notifier.info({}, event_type, payload)

    def error(self, event_type, payload):
        self._notifier.error({}, event_type, payload)


def _get_notification_group(notification):
    return notification.split('.', 1)[0]


def _is_notification_enabled(notification):
    disabled_notifications = CONF.disabled_notifications
    notification_group = _get_notification_group(notification)

    notifications = (notification, notification_group)
    for disabled_notification in disabled_notifications:
        if disabled_notification in notifications:
            return False

    return True


def _send_notification(notify, notification_type, payload):
    if _is_notification_enabled(notification_type):
        notify(notification_type, payload)


def format_task_notification(task):
    # NOTE(nikhil): input is not passed to the notifier payload as it may
    # contain sensitive info.
    return {
        'id': task.task_id,
        'type': task.type,
        'status': task.status,
        'result': None,
        'owner': task.owner,
        'message': None,
        'expires_at': timeutils.isotime(task.expires_at),
        'created_at': timeutils.isotime(task.created_at),
        'updated_at': timeutils.isotime(task.updated_at),
        'deleted': False,
        'deleted_at': None,
    }


def format_metadef_namespace_notification(metadef_namespace):
    return {
        'namespace': metadef_namespace.namespace,
        'namespace_old': metadef_namespace.namespace,
        'display_name': metadef_namespace.display_name,
        'protected': metadef_namespace.protected,
        'visibility': metadef_namespace.visibility,
        'owner': metadef_namespace.owner,
        'description': metadef_namespace.description,
        'created_at': timeutils.isotime(metadef_namespace.created_at),
        'updated_at': timeutils.isotime(metadef_namespace.updated_at),
        'deleted': False,
        'deleted_at': None,
    }


def format_metadef_object_notification(metadef_object):
    object_properties = metadef_object.properties or {}
    properties = []
    for name, prop in six.iteritems(object_properties):
        object_property = _format_metadef_object_property(name, prop)
        properties.append(object_property)

    return {
        'namespace': metadef_object.namespace,
        'name': metadef_object.name,
        'name_old': metadef_object.name,
        'properties': properties,
        'required': metadef_object.required,
        'description': metadef_object.description,
        'created_at': timeutils.isotime(metadef_object.created_at),
        'updated_at': timeutils.isotime(metadef_object.updated_at),
        'deleted': False,
        'deleted_at': None,
    }


def _format_metadef_object_property(name, metadef_property):
    return {
        'name': name,
        'type': metadef_property.type or None,
        'title': metadef_property.title or None,
        'description': metadef_property.description or None,
        'default': metadef_property.default or None,
        'minimum': metadef_property.minimum or None,
        'maximum': metadef_property.maximum or None,
        'enum': metadef_property.enum or None,
        'pattern': metadef_property.pattern or None,
        'minLength': metadef_property.minLength or None,
        'maxLength': metadef_property.maxLength or None,
        'confidential': metadef_property.confidential or None,
        'items': metadef_property.items or None,
        'uniqueItems': metadef_property.uniqueItems or None,
        'minItems': metadef_property.minItems or None,
        'maxItems': metadef_property.maxItems or None,
        'additionalItems': metadef_property.additionalItems or None,
    }


def format_metadef_property_notification(metadef_property):
    schema = metadef_property.schema

    return {
        'namespace': metadef_property.namespace,
        'name': metadef_property.name,
        'name_old': metadef_property.name,
        'type': schema.get('type'),
        'title': schema.get('title'),
        'description': schema.get('description'),
        'default': schema.get('default'),
        'minimum': schema.get('minimum'),
        'maximum': schema.get('maximum'),
        'enum': schema.get('enum'),
        'pattern': schema.get('pattern'),
        'minLength': schema.get('minLength'),
        'maxLength': schema.get('maxLength'),
        'confidential': schema.get('confidential'),
        'items': schema.get('items'),
        'uniqueItems': schema.get('uniqueItems'),
        'minItems': schema.get('minItems'),
        'maxItems': schema.get('maxItems'),
        'additionalItems': schema.get('additionalItems'),
        'deleted': False,
        'deleted_at': None,
    }


def format_metadef_resource_type_notification(metadef_resource_type):
    return {
        'namespace': metadef_resource_type.namespace,
        'name': metadef_resource_type.name,
        'name_old': metadef_resource_type.name,
        'prefix': metadef_resource_type.prefix,
        'properties_target': metadef_resource_type.properties_target,
        'created_at': timeutils.isotime(metadef_resource_type.created_at),
        'updated_at': timeutils.isotime(metadef_resource_type.updated_at),
        'deleted': False,
        'deleted_at': None,
    }


def format_metadef_tag_notification(metadef_tag):
    return {
        'namespace': metadef_tag.namespace,
        'name': metadef_tag.name,
        'name_old': metadef_tag.name,
        'created_at': timeutils.isotime(metadef_tag.created_at),
        'updated_at': timeutils.isotime(metadef_tag.updated_at),
        'deleted': False,
        'deleted_at': None,
    }


class NotificationBase(object):
    def get_payload(self, obj):
        return {}

    def send_notification(self, notification_id, obj, extra_payload=None):
        payload = self.get_payload(obj)
        if extra_payload is not None:
            payload.update(extra_payload)

        _send_notification(self.notifier.info, notification_id, payload)


@six.add_metaclass(abc.ABCMeta)
class NotificationProxy(NotificationBase):
    def __init__(self, repo, context, notifier):
        self.repo = repo
        self.context = context
        self.notifier = notifier

        super_class = self.get_super_class()
        super_class.__init__(self, repo)

    @abc.abstractmethod
    def get_super_class(self):
        pass


@six.add_metaclass(abc.ABCMeta)
class NotificationRepoProxy(NotificationBase):
    def __init__(self, repo, context, notifier):
        self.repo = repo
        self.context = context
        self.notifier = notifier
        proxy_kwargs = {'context': self.context, 'notifier': self.notifier}

        proxy_class = self.get_proxy_class()
        super_class = self.get_super_class()
        super_class.__init__(self, repo, proxy_class, proxy_kwargs)

    @abc.abstractmethod
    def get_super_class(self):
        pass

    @abc.abstractmethod
    def get_proxy_class(self):
        pass


@six.add_metaclass(abc.ABCMeta)
class NotificationFactoryProxy(object):
    def __init__(self, factory, context, notifier):
        kwargs = {'context': context, 'notifier': notifier}

        proxy_class = self.get_proxy_class()
        super_class = self.get_super_class()
        super_class.__init__(self, factory, proxy_class, kwargs)

    @abc.abstractmethod
    def get_super_class(self):
        pass

    @abc.abstractmethod
    def get_proxy_class(self):
        pass


