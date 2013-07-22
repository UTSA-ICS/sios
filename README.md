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

To Test USe:
============
curl -i -X GET http://10.245.123.87:5253/v1/ics_api/ics -H 'Content-Type: application/json' -H 'X-Auth-Token: [ADD A VALID AUTH TOKEN HERE]'
