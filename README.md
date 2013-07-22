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

To Test Use:
============
curl -i -X GET http://[Your machine's IP address]:5253/v1/ics_api/my_roles -H 'Content-Type: application/json' -H 'X-Auth-Token: [ADD A VALID AUTH TOKEN HERE]'
curl -i -X GET http://[Your machine's IP address]:5253/v1/ics_api/my_tenant -H 'Content-Type: application/json' -H 'X-Auth-Token: [ADD A VALID AUTH TOKEN HERE]'
curl -i -X GET http://[Your machine's IP address]:5253/v1/ics_api/my_service_catalog -H 'Content-Type: application/json' -H 'X-Auth-Token: [ADD A VALID AUTH TOKEN HERE]'
