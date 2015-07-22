Ravstack - Run OpenStack on Ravello
===================================

Ravstack provides a set of utilities that make it easy to run OpenStack on
`Ravello Systems`_. It provides for the following:

* Ironic_ power control driver for Ravello.
* Commands to create new "virtual bare metal" nodes and create an RDO-Manager_
  compatible ``instackenv.json`` file for them.
* Commands to do post-install fixups of networking settings.

Ravstack has been designed to work together with RDO-Manager. Other TripleO_
distributions might work as well with some configuration, but are not tested.
The Ironic power driver should work with any recent version of Ironic.

Installing RDO-Manager
----------------------

The hard way to use ravstack is to install a new RDO-Manager from scratch as
per the `installation instructions`_. You then install ravstack on the
RDO-Manager using::

  $ sudo pip3 install ravstack

Note that you need to have a working Python3 environment. Ravstack does not
work with Python 2.x. The easiest is to use the one from EPEL_.

The recommended way however is to download an already pre-configured undercloud
image from the `Ravello Repo`_. The image contains an installed RDO-Manager
with configured bare metal images and has ravstack installed pre-configured.
It will save you a few hours of work. This installation method is what we will
assume for the rest of this document.

Installing From the Ravello Repo
--------------------------------

First step is to get the required images and create a new Ravello application:

* Go to the `ManageIQ Repo`_ page on Ravello Repo.
* Copy the VM named "RDO Manager" into your account.
* Copy the ISO named "ipxe.iso" into your account.
* Create a new application.
* Add the RDO Manager VM to it from the library.
* Give the VM a shorter, easier name (I suggest "under").
* Configure an SSH keypair for the VM.
* Publish the application.

Once the VM is up and running, log on via SSH as the "stack" user, and edit the
file ``/etc/ravstack/ravstack.conf``. Change the ``username`` and ``password``
settings to match your Ravello username and password. Ravstack needs access to
your account so that it can create new nodes and perform power control
operations.

Once this is done, create the nodes and add them to Ironic::

  $ ravstack node-create -n 3
  Created 3 nodes: node1, node2, node3.
  $ ravstack node-dump
  Wrote 3 nodes to `~/instackenv.json`.
  $ source ~/.stackrc
  $ openstack baremetal import --json instackenv.json
  $ openstack baremetal configure boot
  $ openstack baremetal introspection bulk start

We are now ready to deploy the overcloud. The following command may take up to
an hour to complete::

  $ openstack overcloud deploy --plan overcloud

After the installation is done, you should the overcloud in a state of
"CREATE_COMPLETE"::

  $ heat stack-list

Two post install steps are required. This will fixup the Ravello networking
settings to reflect the DHCP addresses allocated to the bare metal nodes. It
will also create public services for the overcloud Horizon and VNC proxy, and
configure the public IP endpoints of these on the nodes. Note that you must run
these commands in the order given here::

  $ ravstack fixup-network
  $ ravstack fixup-nodes

That's it! You now have a working under- and overcloud.

* To access the undercloud from the CLI, source the file ``~/stackrc`` on the
  undercloud VM, and use any of the available OpenStack commands.
* To access the undercloud from Horizon, got to the Ravello web UI and open the
  "http" server on the "under" VM.
* To access the Overcloud from the CLI, source the file ``~/overcloudrc`` on
  the undercloud VM, and use any of the available OpenStack commands.
* To access the Overcloud Horizon, go to the Ravello web UI, and open the
  "http" service on the "controller-1" VM.

Comments
--------

Feel free to report issues on Github or mail me at geertj@gmail.com.

.. _Ravello Systems: http://www.ravellosystems.com/
.. _Ironic: https://wiki.openstack.org/wiki/Ironic
.. _RDO-Manager: https://www.rdoproject.org/RDO-Manager
.. _TripleO: https://wiki.openstack.org/wiki/TripleO
.. _installation instructions: https://repos.fedorapeople.org/repos/openstack-m/docs/master/
.. _EPEL: https://fedoraproject.org/wiki/EPEL
.. _Ravello Repo: http://www.ravellosystems.com/repo
.. _ManageIQ Repo: https://www.ravellosystems.com/repo/profile/public/manageiq
