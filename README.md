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
- Copy raw code from address https://github.com/fpatwa/nova/blob/master/glance/policy.py to /opt/stack/glance/glance/api/policy.py 
- Copy raw code from address https://github.com/fpatwa/nova/blob/master/nova/policy.py to /opt/stack/nova/nova/policy.py

To start SIOS service:
Run the following command:

cd /opt/stack/sios; /opt/stack/sios/bin/sios-api --config-file=/etc/sios/sios-api.conf || touch "/opt/stack/status/stack/sios-api.failure"

To Test Use:
============
- curl -i -X GET http://[Your machine's IP address]:5253/v1/pdp/enforce -H 'Content-Type: application/json' -H 'X-Auth-Token: [ADD A VALID AUTH TOKEN HERE]'

- curl -i -X GET http://[Your machine's IP address]:5253/v1/pdp/check -H 'Content-Type: application/json' -H 'X-Auth-Token: [ADD A VALID AUTH TOKEN HERE]'
