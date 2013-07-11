# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2011-2012 OpenStack LLC.
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

from sios.api import policy
from sios.openstack.common import local
from sios.openstack.common import uuidutils


class RequestContext(object):
    """
    Stores information about the security context under which the user
    accesses the system, as well as additional request information.
    """

    def __init__(self, auth_tok=None, user=None, tenant=None, roles=None,
                 is_admin=False, read_only=False, show_deleted=False,
                 owner_is_tenant=True, service_catalog=None,
                 policy_enforcer=None):
        self.auth_tok = auth_tok
        self.user = user
        self.tenant = tenant
        self.roles = roles or []
        self.read_only = read_only
        self._show_deleted = show_deleted
        self.owner_is_tenant = owner_is_tenant
        self.request_id = uuidutils.generate_uuid()
        self.service_catalog = service_catalog
        self.policy_enforcer = policy_enforcer or policy.Enforcer()
        self.is_admin = is_admin
        if not self.is_admin:
            self.is_admin = \
                self.policy_enforcer.check_is_admin(self)

        if not hasattr(local.store, 'context'):
            self.update_store()

    def to_dict(self):
        # NOTE(ameade): These keys are named to correspond with the default
        # format string for logging the context in openstack common
        return {
            'request_id': self.request_id,

            #NOTE(bcwaldon): openstack-common logging expects 'user'
            'user': self.user,
            'user_id': self.user,

            #NOTE(bcwaldon): openstack-common logging expects 'tenant'
            'tenant': self.tenant,
            'tenant_id': self.tenant,
            'project_id': self.tenant,

            'is_admin': self.is_admin,
            'read_deleted': self.show_deleted,
            'roles': self.roles,
            'auth_token': self.auth_tok,
            'service_catalog': self.service_catalog,
        }

    @classmethod
    def from_dict(cls, values):
        return cls(**values)

    def update_store(self):
        local.store.context = self

    @property
    def owner(self):
        """Return the owner to correlate with an image."""
        return self.tenant if self.owner_is_tenant else self.user

    @property
    def show_deleted(self):
        """Admins can see deleted by default"""
        if self._show_deleted or self.is_admin:
            return True
        return False
