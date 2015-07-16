Raviron - RDO-Manager and OpenStack Ironic in Ravello
=====================================================

Raviron provides a power control driver for `OpenStack Ironic`_ for `Ravello
Systems`_. 

The main use case for Raviron is to allow you to use RDO-Manager_ to install a
"bare metal" RDO_ OpenStack in Ravello. While Raviron should work with any
OpenStack Ironic version, we will assume that you will be using the one
provided by RDO-Manager

Installing RDO-Manager
----------------------

The first step is to install RDO-Manager it in Ravello. You can use one of two
approaches:

* Upload a CentOS 7 `cloud image` in Ravello, create a new VM from it, and then
  use the RDO-Manager `installation instructions`_.
* (the easy way) Copy a pre-installed RDO-Manager VM from the `Ravello Repo`_
  (TBD).

Installing Raviron
------------------

It is recommended to install Raviron on the RDO-Manager VM. This is not
strictly required but there is no reason to run it elsewhere.

First you need to install EPEL and Python 3.4::

  $ sudo yum install https://dl.fedoraproject.org/pub/epel/epel-release-latest-7.noarch.rpm
  $ sudo yum install python34

Now you need to install Raviron. It is recommended to install it in the "stack"
account::

  $ sudo pip install raviron
  $ sudo mkdir /etc/raviron
  $ python -mraviron.config | sudo cat > /etc/raviron/raviron.conf
  $ sudo mkdir /var/log/raviron
  $ sudo chown stack.stack /var/log/raviron

You may also install raviron in a virtualenv. This is useful for debugging
purposes::

  $ pyvenv venv
  $ . venv/bin/activate
  (venv) $ pip install raviron
  (venv) $ python -mraviron.config > $VIRTUAL_ENV/raviron.conf
  (venv) $ # Log file will be $VIRTUAL_ENV/raviron.log

After this edit the configuration file that you created above. You need to set
at least the following variables:

* ``username`` - Your Ravello login name (email address).
* ``password`` - Your Ravello password.
* ``application`` - The Ravello application that you'll be using.
* ``pxe_iso`` - The name of an ISO to be used for PXE booting. It is
  recommended you use iPXE. You can download the latest version from
  the ipxe.org web site and upload it to Ravello, or you may copy it from the
  `Ravello Repo`_

Creating the Proxy
------------------

Raviron is executed by the "ssh" power driver from Ironic. The setup involves
an SSH keypair of which the public key is added to ``~/.ssh/authorized_keys``.
The key is bound the raviron API proxy using the ``command=`` option on the
public key. When executed by the "ssh" power driver, the API proxy will
interpret the various "virsh" commands  translate them to the respective
Ravello API calls.

To install the SSH key and the proxy, execute::

  $ raviron proxy-create
  Private key created as: ~/.ssh/id_raviron
  Proxy created at: ~/bin/raviron-proxy

This setup is only required once per system.

Creating Nodes
--------------

Raviron can create new nodes for you that you can use with RDO-Manager. To
create nodes, repeat the following command as many times as needed::

  $ raviron node-create

By default, a node with 2 processors, 8GB of RAM and a 60GB disk is created.
You can override these defaults on the command line. The nodes are enabled for
PXE booting by inserting the PXE boot ISO that you specified in the
configuration file.

The nodes are created with the same number of NICs as the RDO-Manager VM, and
they are connected to the same networks.

After you have created all nodes, issue the following command::

  $ raviron node-sync
  Wrote 4 nodes to `~/nodes.json`.

The ``nodes.json`` file contain the hardware details for all the nodes. This
file can be imported into RDO-Manager::

  $ openstack baremetal import --json nodes.json

You are now ready to deploy start installing RDO!

Testing Raviron
---------------

You can test raviron in two ways.

**Testing through ssh**

You can access the control functions provided by raviron through the SSH
proxy::

  $ ssh-add -i ~/.ssh/id_raviron
  $ ssh localhost virsh list --all
  under
  node1
  node2
  node3
  $ ssh localhost virsh start node1
  $ ssh localhost virsh list --all running
  "node1"

Note that the "virsh" commands here are not real virsh commands. These commands
correspond to the specific subset of commands used by the Ironic ssh/virsh
power driver. They are recognized by the raviron proxy and translated to
Ravello API calls.

**Testing through ironic**

You can also test raviron through Ironic::

  $ . ~/stackrc
  $ ironic node-list
  $ ironic node-set-power-state node1 on

Installing RDO
--------------

Once you have tested that power control works for your nodes, you can follow
the `Basic Deployment`_ section from the RDO-Manager manual to create an
OpenStack installation.

Comments
--------

Feel free to report issues on github or mail me at geertj@gmail.com.

.. _Ravello Systems: http://www.ravellosystems.com/
.. _OpenStack Ironic: https://wiki.openstack.org/wiki/Ironic
.. _RDO: https://www.rdoproject.org/
.. _RDO-Manager: https://www.rdoproject.org/RDO-Manager
.. _EPEL: https://fedoraproject.org/wiki/EPEL
.. _Ravello Repo: http://www.ravellosystems.com/repo/profile/public/manageiq
.. _cloud image: http://cloud.centos.org/centos/7/images
.. _installation instructions: https://repos.fedorapeople.org/repos/openstack-m/docs/master/
.. _Basic Deployment: https://repos.fedorapeople.org/repos/openstack-m/docs/master/basic_deployment/basic_deployment.html
