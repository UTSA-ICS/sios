# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2012 OpenStack Foundation.
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

from sios.api.v1 import pdp
from sios.common import wsgi


class API(wsgi.Router):

    """WSGI router for SIOS v1 API requests."""

    def __init__(self, mapper):

        pdp_resource = pdp.create_resource()
        mapper.connect('/pdp/check',
                       controller=pdp_resource,
                       action='check',
                       conditions={'method': ['POST']})
        mapper.connect('/pdp/enforce',
                       controller=pdp_resource,
                       action='enforce',
                       conditions={'method': ['POST']})

        super(API, self).__init__(mapper)
