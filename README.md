sios
====

SIOS PDP service for Openstack

This service will act as a Policy Decision Point (PDP) for any OpenStack service.<br>
A OpenStack service's Policy Enforcement engine will make a REST call to SIOS PDP service for a Policy Decision.<br>
The SIOS PDP service will always respond with a 'True' of 'False' as a result of the Policy Query.<br>
In addition to the standard OpenStack HTTP headers, the follwing two HTTP headers are required by SIOS PDP api:<br>
1. 'X-Action'<br>
2. 'X-Target'

To be able to use this service do the following:<br>
1.) Copy sios/etc to /etc/sios<br>
sudo cp /opt/stack/sios/etc/* /etc/sios/.<br>
2.) Create a directory called /var/cache/sios and give it 777 permission (chmod 777 /var/cache/sios)<br>
3.) Create a user [sios] with password [admin] in the service tenant with 'admin' role<br>
4.) Create a service called 'sios' in Keystone<br>
5.) Update the policy.py file for glance service to use sios PDP api for Policy Decisions:<br>
wget -O /opt/stack/glance/glance/api/policy.py https://raw.github.com/fpatwa/sios/master/external_service_policy_files/glance/policy.py<br>
6.) Update the policy.py file for nova service to use sios PDP api for Policy Decisions:<br>
wget -O /opt/stack/nova/nova/policy.py https://raw.github.com/fpatwa/sios/master/external_service_policy_files/nova/policy.py<br>
7.) To start the SIOS service run the following command:<br>
cd /opt/stack/sios; /opt/stack/sios/bin/sios-api --config-file=/etc/sios/sios-api.conf || touch "/opt/stack/status/stack/sios-api.failure"<br>
8.) Restart nova api and glance api services (from screen)<br>

To Test Usage:
==============
- Run nova commands (e.g. nova list)
- Run glance commands (e.g glance image-list)
