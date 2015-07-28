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

Installation
------------

The recommended way is to download an already pre-configured undercloud VM from
the `Ravello Repo`_. The VM contains an installed RDO-Manager with pre-built
bare metal images and has ravstack installed and configured.

Installing from the Ravello Repo
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

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

Now create the nodes and add them to Ironic. You can create as many nodes are
you want. The default networking range configured in RDO-Manager allows up to
100 IPs for the nodes, and in addition 40 IPs for introspection (see below).
The example below creates 3 nodes::

  $ ravstack node-create -n 3
  Created 3 nodes: node1, node2, node3.
  $ ravstack node-dump
  Wrote 3 nodes to `~/instackenv.json`.
  Wrote 6 mac addresses to `/etc/ethers`.
  $ source ~/stackrc
  $ openstack baremetal import --json instackenv.json

The nodes should now be visible in Ironic (output abridged)::

  $ ironic node-list
  +--------------------------------------+-------------+-----------------+-------------+
  | UUID                                 | Power State | Provision State | Maintenance |
  +--------------------------------------+-------------+-----------------+-------------+
  | cf30c3ba-7294-44cd-b835-664069289228 | power off   | available       | False       |
  | e8f715b1-8c07-4361-8bb6-74dbe66dc134 | power off   | available       | False       |
  | a12beebc-7e04-42e6-9f70-9fe9b585454f | power off   | available       | False       |
  +--------------------------------------+-------------+-----------------+-------------+

Configure the boot order for the nodes and start introspection. The following
commands might issue a few warnings that nodes are locked. This is OK and
expected. The operation will retry automatically. Introspection should take
less than 10 minutes to complete::

  $ openstack baremetal configure boot
  $ openstack baremetal introspection bulk start

We are now ready to deploy the overcloud. The following command may take up to
an hour to complete::

  $ openstack overcloud deploy --plan overcloud --compute-scale 2

After the installation is done, you should see the overcloud in a state of
``CREATE_COMPLETE`` (output abridged)::

  $ heat stack-list
  +--------------------------------------+------------+-----------------+
  | id                                   | stack_name | stack_status    |
  +--------------------------------------+------------+-----------------+
  | 8e53c52f-8a02-4a7a-9ef8-4de530e37ff4 | overcloud  | CREATE_COMPLETE |
  +--------------------------------------+------------+-----------------+

A post install step is required. The VMs in a Ravello application are connected
by an isolated network, and they communicate with the outside through one of
the available NAT options. The following command will set up the required port
mappings and makes sure that Horizon and the VNC proxy have the correct
configuration::

  $ ravstack fixup
  Fixed Ravello config for 3 nodes.
  Fixed OS config for 3 nodes.

That's it! You now have a working undercloud and overcloud.

* To access the undercloud from the CLI, source the file ``~/stackrc`` on the
  undercloud VM, and use any of the available OpenStack commands.
* To access the overcloud from the CLI, source the file ``~/overcloudrc`` on
  the undercloud VM, and use any of the available OpenStack commands.
* To access the overcloud Horizon, go to the Ravello web UI, and open the
  "http" service on the "overcloud-controller-1" VM.

**NOTE**: the following post-installation steps still remain to be done to make
the installation useful. These will be automated soon:

Create an image in Glance::

  $ glance image-create --name fedora --file fedora-user.qcow2 \
        --disk-format qcow2 --container-format bare

Setup overcloud networking. The following creates a simple provider network. It
will allow you to start up an instance, but not yet have it communicate to the
outside world. TBD::

  $ neutron net-create nova --router:external
  $ neutron subnet-create --name nova --disable-dhcp \
        --allocation-pool start=192.168.2.100,end=192.168.2.200 \
        --gateway 192.168.2.1 nova 192.168.2.0/24

Enable the undercloud Horizon for remote access. The image does not have the
undercloud Horizon service exposed because it contains a pre-installed
undercloud with fixed passwords. To enable this service, either we need to
change all password (can this be done easily?) or maybe more simply, install a
unique random password at the Apache level.

Installing from Scratch
~~~~~~~~~~~~~~~~~~~~~~~

If you want to RDO-Manager yourself then that is possible as well. You need to
start by installing a new CentOS VM in Ravello, and after that you need to
following the RDO-Manager `installation instructions`_. Also make sure you read
the `Ravello Notes`_ and `RDO-Manager Notes`_. Installation of ravstack
itself::

  $ sudo pip3 install ravstack
  $ sudo ravstack config-create
  Created config file `/etc/ravstack/ravstack.conf`.
  $ sudo mkdir /var/log/ravstack
  $ sudo chown stack:stack /var/log/ravstack
  $ ravstack proxy-create
  Private key created as: `~/.ssh/id_ravstack`.
  Proxy created at: `~/bin/ironic-proxy`.

Note that you need to have a working Python3 environment. Ravstack does not
work with Python 2.x. The easiest is to use the ``python34`` package from
EPEL_.

Once you've installed ravstack, follow the instructions for installing from the
Ravello Repo above.

Documentation
-------------

In addition to this README, the following documents exist:

* `Ravello Notes`_ - Some notes on working with Ravello.
* `RDO-Manager Notes`_ - Some notes on working with RDO Manager.

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
.. _Ravello Notes: https://github.com/geertj/ravstack/blob/master/docs/ravello.rst
.. _RDO-Manager Notes: https://github.com/geertj/ravstack/blob/master/docs/rdomanager.rst
