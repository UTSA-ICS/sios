
# Copyright 2013 OpenStack Foundation
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
/ics_api endpoint for Sios v1 API
"""

import copy
import eventlet
from oslo.config import cfg
from webob.exc import (HTTPError,
                       HTTPNotFound,
                       HTTPConflict,
                       HTTPBadRequest,
                       HTTPForbidden,
                       HTTPRequestEntityTooLarge,
                       HTTPInternalServerError,
                       HTTPServiceUnavailable)
from webob import Response

from sios.api import common
from sios.api import policy
import sios.api.v1
from sios.common import exception
from sios.common import utils
from sios.common import wsgi
import sios.openstack.common.log as logging
from sios.openstack.common import strutils
from sios import notifier

CONF = cfg.CONF
LOG = logging.getLogger(__name__)
SUPPORTED_PARAMS = sios.api.v1.SUPPORTED_PARAMS
SUPPORTED_FILTERS = sios.api.v1.SUPPORTED_FILTERS
CONTAINER_FORMATS = ['ami', 'ari', 'aki', 'bare', 'ovf']
DISK_FORMATS = ['ami', 'ari', 'aki', 'vhd', 'vmdk', 'raw', 'qcow2', 'vdi',
                'iso']


class Controller(object):
    """
    WSGI controller for images resource in Sios v1 API

    The images resource API is a RESTful web service for image data. The API
    is as follows::

        GET /images -- Returns a set of brief metadata about images
        GET /images/detail -- Returns a set of detailed metadata about
                              images
        HEAD /images/<ID> -- Return metadata about an image with id <ID>
        GET /images/<ID> -- Return image data for image with id <ID>
        POST /images -- Store image data and return metadata about the
                        newly-stored image
        PUT /images/<ID> -- Update image metadata and/or upload image
                            data for a previously-reserved image
        DELETE /images/<ID> -- Delete the image with id <ID>
    """

    def __init__(self):
        self.notifier = notifier.Notifier()
        self.policy = policy.Enforcer()
        self.pool = eventlet.GreenPool(size=1024)
   
    def my_roles(self, req):
	return req.context.roles

    def my_tenant(self, req):
	return req.context.tenant

    def my_service_catalog(self, req):
	return req.context.service_catalog

    def _enforce(self, req, action):
        """Authorize an action against our policies"""
        try:
            self.policy.enforce(req.context, action, {})
        except exception.Forbidden:
            raise HTTPForbidden()


class Deserializer(wsgi.JSONRequestDeserializer):
    """Handles deserialization of specific controller method requests."""

    def _deserialize(self, request):
        result = {}
        return result

    def create(self, request):
        return self._deserialize(request)

    def update(self, request):
        return self._deserialize(request)


class Serializer(wsgi.JSONResponseSerializer):
    """Handles serialization of specific controller method responses."""

    def __init__(self):
        self.notifier = notifier.Notifier()

    def meta(self, response, result):
       return response

    def show(self, response, result):
        return response

    def update(self, response, result):
       return response

    def create(self, response, result):
       return response


def create_resource():
    """Resource factory method"""
    deserializer = Deserializer()
    serializer = Serializer()
    return wsgi.Resource(Controller(), deserializer, serializer)
