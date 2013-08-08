sios
====

SIOS service for Openstack

Write a new service that simulates communications with Keystone 
Authenticate itself with Keystone
Mapping request to local request 

To be able to use this service do the following:
- Copy sios/etc to /etc/sios
- Create a directory called /var/cache/sios and give it 777 permission (chmod 777 /var/cache/sios)
- Create a user [sios] with password [admin] in the service tenant with 'admin' role
- Create a service called 'sios' in Keystone
- Update the policy.py file for glance service to use sios PDP api for Policy Decisions:
wget -O /opt/stack/glance/glance/api/policy.py https://raw.github.com/fpatwa/sios/master/external_service_policy_files/glance/policy.py
- Update the policy.py file for nova service to use sios PDP api for Policy Decisions:
wget -O /opt/stack/nova/nova/policy.py https://raw.github.com/fpatwa/sios/master/external_service_policy_files/nova/policy.py

To start the SIOS service run the following command:
cd /opt/stack/sios; /opt/stack/sios/bin/sios-api --config-file=/etc/sios/sios-api.conf || touch "/opt/stack/status/stack/sios-api.failure"

To Test Use:
============
- curl -i -X GET http://[Your machine's IP address]:5253/v1/pdp/enforce_glance -H 'Content-Type: application/json' -H 'X-Auth-Token: [ADD A VALID AUTH TOKEN HERE]'

- curl -i -X GET http://[Your machine's IP address]:5253/v1/pdp/enforce_nova -H 'Content-Type: application/json' -H 'X-Auth-Token: [ADD A VALID AUTH TOKEN HERE]'

- curl -i -X GET http://[Your machine's IP address]:5253/v1/pdp/check_glance -H 'Content-Type: application/json' -H 'X-Auth-Token: [ADD A VALID AUTH TOKEN HERE]'
