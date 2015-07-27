Ravstack - Run OpenStack on Ravello
===================================

Ravstack is a toolkit that make it easy to run OpenStack on `Ravello Systems`_.
It focuses on OpenStack distributions that are installed by TripleO_ based
installers, such as RDO-Manager_. Ravstack offers:

* Ironic_ power control for Ravello.
* Commands to create new "virtual bare metal" nodes and create an instack
  compatible ``instackenv.json`` file for them.
* Commands to do certain post-install fixups requires because of the split
  inside/outside network offered by Ravello.

Installing RDO-Manager
----------------------

The hard way to install ravstack is to create a new CentOS VM in a new Ravello
application, and install RDO-Manager per its `installation instructions`_. You
then install ravstack on the RDO-Manager using::

  $ sudo pip3 install ravstack
  $ sudo ravstack config-create
  Created config file `/etc/ravstack/ravstack.conf`.
  $ ravstack proxy-create

Note that you need to have a working Python3 environment. Ravstack does not
work with Python 2.x. The easiest is to use the ``python34`` package from
EPEL_.

The recommended way however is to download an already pre-configured undercloud
image from the `Ravello Repo`_. The image contains an installed RDO-Manager
with configured bare metal images and has ravstack installed and configured.
This installation method is what we will assume for the rest of this document.

Installing From the Ravello Repo
--------------------------------

First step is to get the required images and create a new Ravello application:

* Go to the `ManageIQ page`_ on the Ravello Repo.
* Copy the VM named "RDO Manager" into your account.
* Copy the ISO named "ipxe.iso" into your account.
* Create a new application.
* Add the RDO Manager VM to the application.
* Give the VM a shorter, easier name (I suggest "undercloud").
* Configure an SSH keypair for the VM.
* Publish the application.

Once the VM is up and running, log on via SSH as the "stack" user. Note that
the undercloud VM is set up to use port mapping and so its ssh service will run
on a non-standard port somewhere in the range of 10000. The exact address and
port number of the SSH service are available from Ravello web UI in the
"summary" pane of the undercloud VM.

On the undercloud VM, edit the file ``/etc/ravstack/ravstack.conf``. Change the
``[ravello]username`` and ``[ravello]password`` settings to match your Ravello
username and password. Ravstack needs access to your account so that it can
create new nodes and perform power control operations.

Once this is done, create the nodes and add them to Ironic::

  $ ravstack node-create -n 3
  Created 3 nodes: node1, node2, node3.
  $ ravstack node-dump
  Wrote 3 nodes to `~/instackenv.json`.
  Wrote 6 mac addresses to `/etc/ethers`.
  $ source ~/stackrc
  $ openstack baremetal import --json instackenv.json

The following commands might issue a few warnings that nodes are locked. The
operation will retry automatically. This is OK and expected::

  $ openstack baremetal configure boot
  $ openstack baremetal introspection bulk start

We are now ready to deploy the overcloud. The following command may take up to
an hour to complete::

  $ openstack overcloud deploy --plan overcloud

After the installation is done, you should see the overcloud in a state of
``CREATE_COMPLETE``::

  $ heat stack-list

A post install step is required. Ravello has a split inside/outside networking
model, where VMs on the inside communicate with the outside through one of the
available NAT options. The following command will set up the required port
mappings and makes some re-configurations on the installed nodes::

  $ ravstack fixup

That's it! You now have a working undercloud and overcloud.

* To access the undercloud from the CLI, source the file ``~/stackrc`` on the
  undercloud VM, and use any of the available OpenStack commands.
* To access the undercloud from Horizon, go to the Ravello web UI and open the
  "http" server on the "undercloud" VM.
* To access the Overcloud from the CLI, source the file ``~/overcloudrc`` on
  the undercloud VM, and use any of the available OpenStack commands.
* To access the Overcloud Horizon, go to the Ravello web UI, and open the
  "http" service on the "overcloud-controller-1" VM.

Comments
--------

Feel free to report issues on Github or mail me at geertj@gmail.com.

.. _Ravello Systems: http://www.ravellosystems.com/
.. _TripleO: https://wiki.openstack.org/wiki/TripleO
.. _RDO-Manager: https://www.rdoproject.org/RDO-Manager
.. _Ironic: https://wiki.openstack.org/wiki/Ironic
.. _installation instructions: https://repos.fedorapeople.org/repos/openstack-m/docs/master/
.. _EPEL: https://fedoraproject.org/wiki/EPEL
.. _Ravello Repo: https://www.ravellosystems.com/repo/profile/public/manageiq
.. _ManageIQ Page: https://www.ravellosystems.com/repo/profile/public/manageiq
