
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
/PDP endpoint for Sios v1 API
"""

import copy
import eventlet
from oslo_config import cfg
from webob.exc import (HTTPError,
                       HTTPNotFound,
                       HTTPConflict,
                       HTTPBadRequest,
                       HTTPForbidden,
                       HTTPRequestEntityTooLarge,
                       HTTPInternalServerError,
                       HTTPServiceUnavailable)
from webob import Response
from sios.api import policy
import sios.api.v1
from sios.common import exception
from sios.common import utils
from sios.common import wsgi
from oslo_utils import strutils
import oslo_log.log as logging
from sios.i18n import _

CONF = cfg.CONF
LOG = logging.getLogger(__name__)


class Controller(object):
    """
    WSGI controller for Policy Decision Point in Sios v1 API

    The PDP resource API is a RESTful web service for Policy Decisions. The API
    is as follows::

        POST /check -- check the Policy Decision
        POST /enforce -- check the Policy Decision to be enforced
    """

    def __init__(self):
        self.policy = policy.Enforcer()
        self.pool = eventlet.GreenPool(size=1024)
   
    """
    PDP for glance OpenStack Service
    """
    def enforce_glance(self, req):
        """Authorize an action against our policies"""
        try:
	    LOG.debug(_('Evaluating Policy decision for action [%s]') % req.context.action)
            pdp_decision = self.policy.enforce(req.context, req.context.action, req.context.target)
	    LOG.debug(_('The Policy decision for action [%s] is [%s]') % (req.context.action, pdp_decision))
   	    return pdp_decision
        except exception:
	    LOG.debug(_('Exception Raised for action [%s]') % req.context.action)
	    LOG.debug(_('The Policy decision for action [%s] is [False]') % req.context.action)
	    LOG.debug(exception)
            return False

    def check_glance(self, req):
        """Authorize an action against our policies"""
        try:
	    LOG.debug(_('Evaluating Policy decision for action [%s]') % req.context.action)
            pdp_decision = self.policy.check(req.context, req.context.action, req.context.target)
	    LOG.debug(_('The Policy decision for action [%s] is [%s]') % (req.context.action, pdp_decision))
   	    return pdp_decision
        except exception:
	    LOG.debug(_('Exception Raised for action [%s]') % req.context.action)
	    LOG.debug(_('The Policy decision for action [%s] is [False]') % req.context.action)
	    LOG.debug(exception)
            return False

    """
    PDP for nova OpenStack Service
    """
    def enforce_nova(self, req):
        """Authorize an action against our policies"""
        try:
	    LOG.debug(_('Evaluating Policy decision for action [%s]') % req.context.action)
            pdp_decision =  self.policy.enforce(req.context, req.context.action, req.context.target)
	    LOG.debug(_('The Policy decision for action [%s] is [%s]') % (req.context.action, pdp_decision))
	    return pdp_decision
        except exception:
	    LOG.debug(_('Exception Raised for action [%s]') % req.context.action)
	    LOG.debug(_('The Policy decision for action [%s] is [False]') % req.context.action)
	    LOG.debug(exception)
            return False

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
        self.notifier = None

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
