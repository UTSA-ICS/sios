# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright (c) 2011 OpenStack, LLC.
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

"""Policy Engine For Glance"""
import datetime
import httplib
import json
import logging
import os
import stat
import time
import urllib
import webob.exc
import os.path
import traceback

from oslo.config import cfg

from glance.common import exception
import glance.openstack.common.log as logging
from glance.openstack.common import jsonutils
from glance.openstack.common import timeutils

LOG = logging.getLogger(__name__)

opts = [
    cfg.StrOpt('auth_admin_prefix', default=''),
    cfg.StrOpt('keystone_auth_host', default='127.0.0.1'),
    cfg.IntOpt('keystone_auth_port', default=35357),
    cfg.StrOpt('sios_auth_host', default='127.0.0.1'),
    cfg.IntOpt('sios_auth_port', default=5253),
    cfg.StrOpt('auth_protocol', default='http'),
    cfg.StrOpt('auth_version', default=None),
    cfg.BoolOpt('delay_auth_decision', default=False),
    cfg.BoolOpt('http_connect_timeout', default=None),
    cfg.StrOpt('http_handler', default=None),
    cfg.StrOpt('admin_token', secret=True),
    cfg.StrOpt('admin_user'),
    cfg.StrOpt('admin_password', secret=True),
    cfg.StrOpt('admin_tenant_name', default='admin'),
    cfg.StrOpt('certfile'),
    cfg.StrOpt('keyfile'),
    cfg.IntOpt('token_cache_time', default=300),
    cfg.StrOpt('memcache_security_strategy', default=None),
    cfg.StrOpt('memcache_secret_key', default=None, secret=True)
]
CONF = cfg.CONF
CONF.register_opts(opts, group='authtoken')


class Enforcer(object):
    """Responsible for loading and enforcing rules"""


    def __init__(self):
        # where to find the auth service (we use this to validate tokens)
        self.keystone_auth_host = self._conf_get('keystone_auth_host')
        self.keystone_auth_port = int(self._conf_get('keystone_auth_port'))
        self.sios_auth_host = self._conf_get('sios_auth_host')
        self.sios_auth_port = int(self._conf_get('sios_auth_port'))
        self.auth_protocol = self._conf_get('auth_protocol')
        if not self._conf_get('http_handler'):
            if self.auth_protocol == 'http':
                self.http_client_class = httplib.HTTPConnection
            else:
                self.http_client_class = httplib.HTTPSConnection
        else:
            # Really only used for unit testing, since we need to
            # have a fake handler set up before we issue an http
            # request to get the list of versions supported by the
            # server at the end of this initialization
            self.http_client_class = self._conf_get('http_handler')

        self.auth_admin_prefix = self._conf_get('auth_admin_prefix')

        # SSL
        self.cert_file = self._conf_get('certfile')
        self.key_file = self._conf_get('keyfile')

        # Credentials used to verify this component with the Auth service since
        # validating tokens is a privileged call
        self.admin_token = self._conf_get('admin_token')
        self.admin_token_expiry = None
        self.admin_user = self._conf_get('admin_user')
        self.admin_password = self._conf_get('admin_password')
        self.admin_tenant_name = self._conf_get('admin_tenant_name')

        http_connect_timeout_cfg = self._conf_get('http_connect_timeout')
        self.http_connect_timeout = (http_connect_timeout_cfg and
                                     int(http_connect_timeout_cfg))
        self.auth_version = None


        self.admin_token=None
        self.admin_user='glance'
        self.admin_password='admin'
        self.admin_tenant_name='service'
        self.admin_token_expiry = None
	self.key_file = None
	self.cert_file = None

        if self.auth_protocol == 'http':
        	self.http_client_class = httplib.HTTPConnection
        else:
        	self.http_client_class = httplib.HTTPSConnection

    def _conf_get(self, name):
        return CONF.authtoken[name]

    def _request_admin_token(self):
        """Retrieve new token as admin user from keystone.

        :return token id upon success
        :raises ServerError when unable to communicate with keystone

        Irrespective of the auth version we are going to use for the
        user token, for simplicity we always use a v2 admin token to
        validate the user token.

        """
        params = {
		'auth': {
			'passwordCredentials': {
				'username': self.admin_user,
				'password': self.admin_password,
				},
			'tenantName': self.admin_tenant_name,
			}
		}

        response, data = self._json_request(self.keystone_auth_host,
					    self.keystone_auth_port,
					    'POST',
                                            '/v2.0/tokens',
                                            body=params)
        try:
            token = data['access']['token']['id']
            expiry = data['access']['token']['expires']
            assert token
            assert expiry
            datetime_expiry = timeutils.parse_isotime(expiry)
            return (token, timeutils.normalize_time(datetime_expiry))
        except (AssertionError, KeyError):
            self.LOG.warn(
                "Unexpected response from keystone service: %s", data)
            raise ServiceError('invalid json response')
        except (ValueError):
            self.LOG.warn(
                "Unable to parse expiration time from token: %s", data)
            raise ServiceError('invalid json response')

    def get_admin_token(self):
        """Return admin token, possibly fetching a new one.

        if self.admin_token_expiry is set from fetching an admin token, check
        it for expiration, and request a new token is the existing token
        is about to expire.

        :return admin token id
        :raise ServiceError when unable to retrieve token from keystone

        """
        if self.admin_token_expiry:
            if will_expire_soon(self.admin_token_expiry):
                self.admin_token = None

        if not self.admin_token:
            (self.admin_token,
             self.admin_token_expiry) = self._request_admin_token()

        return self.admin_token

    def _get_http_connection(self, auth_host, auth_port):
        if self.auth_protocol == 'http':
            return self.http_client_class(auth_host, auth_port,
                                          timeout=self.http_connect_timeout)
        else:
            return self.http_client_class(auth_host,
                                          auth_port,
                                          self.key_file,
                                          self.cert_file,
                                          timeout=self.http_connect_timeout)


    def _http_request(self, auth_host, auth_port, method, path, **kwargs):
        """HTTP request helper used to make unspecified content type requests.

        :param method: http method
        :param path: relative request url
        :return (http response object, response body)
        :raise ServerError when unable to communicate with keystone

        """
        conn = self._get_http_connection(auth_host, auth_port)
        RETRIES = 3
        retry = 0

        while True:
            try:
                conn.request(method, path, **kwargs)
                response = conn.getresponse()
                body = response.read()
                break
            except Exception as e:
                if retry == RETRIES:
                    self.LOG.error('HTTP connection exception: %s' % e)
                    raise ServiceError('Unable to communicate with keystone')
                # NOTE(vish): sleep 0.5, 1, 2
                self.LOG.warn('Retrying on HTTP connection exception: %s' % e)
                time.sleep(2.0 ** retry / 2)
                retry += 1
            finally:
                conn.close()

        return response, body

    def _json_request(self, auth_host, auth_port, method, path, body=None, additional_headers=None):
        """HTTP request helper used to make json requests.

        :param method: http method
        :param path: relative request url
        :param body: dict to encode to json as request body. Optional.
        :param additional_headers: dict of additional headers to send with
                                   http request. Optional.
        :return (http response object, response body parsed as json)
        :raise ServerError when unable to communicate with keystone

        """
        kwargs = {
            'headers': {
                'Content-type': 'application/json',
                'Accept': 'application/json',
            },
        }

        if additional_headers:
            kwargs['headers'].update(additional_headers)

        if body:
            kwargs['body'] = jsonutils.dumps(body)

        path = self.auth_admin_prefix + path

        response, body = self._http_request(auth_host, auth_port, method, path, **kwargs)
        try:
            data = jsonutils.loads(body)
        except ValueError:
            self.LOG.debug('Keystone did not return json-encoded body')
            data = {}

        return response, data

    def check_is_admin(self, context):
        """Check if the given context is associated with an admin role,
           as defined via the 'context_is_admin' RBAC rule.

           :param context: Glance request context
           :returns: A non-False value if context role is admin.
        """
        target = context.to_dict()
        return self.check(context, 'context_is_admin', target)

    def check(self, context, action, target):
        """Verifies that the action is valid on the target in this context.

           :param context: Glance request context
           :param action: String representing the action to be checked
           :param object: Dictionary representing the object of the action.
           :returns: A non-False value if access is allowed.
        """
        if (context.auth_tok == None):
	  return False
        headers = {'X-Auth-Token': context.auth_tok, 'X-Action': action, 'X-Target': target}
        response, data = self._json_request(self.sios_auth_host, self.sios_auth_port, 'POST',
                                            '/v1/pdp/check_glance', additional_headers=headers)
	return data

    def enforce(self, context, action, target):
        """Verifies that the action is valid on the target in this context.

           :param context: Glance request context
           :param action: String representing the action to be checked
           :param object: Dictionary representing the object of the action.
           :raises: `glance.common.exception.Forbidden`
           :returns: A non-False value if access is allowed.
        """
        headers = {'X-Auth-Token': context.auth_tok, 'X-Action': action, 'X-Target': target}
        response, data = self._json_request(self.sios_auth_host, self.sios_auth_port, 'POST',
                                            '/v1/pdp/enforce_glance', additional_headers=headers)
	if (data == False):
	  raise exception.Forbidden
        else:
	  return data
