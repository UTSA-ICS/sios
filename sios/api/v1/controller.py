# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2011 OpenStack LLC.
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

import webob.exc

from sios.common import exception
import sios.openstack.common.log as logging
import sios.registry.client.v1.api as registry
import sios.store as store

LOG = logging.getLogger(__name__)


class BaseController(object):
    def get_image_meta_or_404(self, request, image_id):
        """
        Grabs the image metadata for an image with a supplied
        identifier or raises an HTTPNotFound (404) response

        :param request: The WSGI/Webob Request object
        :param image_id: The opaque image identifier

        :raises HTTPNotFound if image does not exist
        """
        context = request.context
        try:
            return registry.get_image_metadata(context, image_id)
        except exception.NotFound:
            msg = _("Image with identifier %s not found") % image_id
            LOG.debug(msg)
            raise webob.exc.HTTPNotFound(
                    msg, request=request, content_type='text/plain')
        except exception.Forbidden:
            msg = _("Forbidden image access")
            LOG.debug(msg)
            raise webob.exc.HTTPForbidden(msg,
                                          request=request,
                                          content_type='text/plain')

    def get_active_image_meta_or_404(self, request, image_id):
        """
        Same as get_image_meta_or_404 except that it will raise a 404 if the
        image isn't 'active'.
        """
        image = self.get_image_meta_or_404(request, image_id)
        if image['status'] != 'active':
            msg = _("Image %s is not active") % image_id
            LOG.debug(msg)
            raise webob.exc.HTTPNotFound(
                    msg, request=request, content_type='text/plain')
        return image

    def update_store_acls(self, req, image_id, location_uri, public=False):
        if location_uri:
            try:
                read_tenants = []
                write_tenants = []
                members = registry.get_image_members(req.context, image_id)
                if members:
                    for member in members:
                        if member['can_share']:
                            write_tenants.append(member['member_id'])
                        else:
                            read_tenants.append(member['member_id'])
                store.set_acls(req.context, location_uri, public=public,
                               read_tenants=read_tenants,
                               write_tenants=write_tenants)
            except exception.UnknownScheme:
                msg = _("Store for image_id not found: %s") % image_id
                raise webob.exc.HTTPBadRequest(explanation=msg,
                                               request=req,
                                               content_type='text/plain')
