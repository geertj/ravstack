Raviron - Ironic Power Control for Ravello
==========================================

Raviron allows OpenStack Ironic to control power for VMs running in Ravello
Systems.  It is designed to be used with the ssh/virsh power driver that is
already in upstream Ironic.

The benefits of using the existing ssh driver is that no changes are required
to upstream Ironic. It also allows for finer grained access control. Ravello
does not currently allow security delegation for individual application, so a
set of Ravello API credentials always allow access to all applications running
in corresponding organization. This may not be suitable for all deployments
(e.g. virtual classrooms). By using ssh we can set up a constrained ssh key
that only allows access to a single application. The drawback is that you need
to run a separate ssh server somewhere.

Installing Raviron
------------------

Raviron needs to be installed in the following way:

 * You need to run raviron from a Linux system with a recent version of OpenSSH.
 * It needs to be run from a dedicated user account. We use the "raviron"
   account below but the name is not important.
 * It is highly recommended you run raviron from a vitualenv.


Setting up the environment::

  $ sudo useradd raviron
  $ sudo -u raviron bash
  [raviron] $ cd /home/raviron
  [raviron] $ virtualenv venv  # "pyvenv" for Python 3.x
  [raviron] $ . venv/bin/activate
  (venv) [raviron] $ pip install raviron


Creating Keys
-------------

Once Raviron is installed, you need to create ssh keys. Each ssh key will allow
controlling the VMs in a single Ravello application::

  (venv) [raviron] $ create-key user@example.com MyApp
  Private key created as: ~/.ssh/id_raviron_0001
  Using API proxy: ~/bin/raviron-proxy-0001.sh
  Key is constrained to application: MyApp

The output key needs to be copied to the machine running Ironic so that it may
access the SSH proxy machine.

Setting up Ironic
-----------------

To use Raviron from OpenStack Ironic, you need to use the "ssh" power driver.
Because Ravello supports PXE booting, you  will likely use this in together
with "pxe" deployments through "pxe_ssh" driver. This is not mandatory
however, and you could also use "fake_ssh" for example.

Whatever driver you choose, you need to make sure it is enabled in
ironic.conf::

  # Specify the list of drivers to load during service initialization.
  enabled_drivers=pxe_ssh

After that you can set up your Ironic nodes. Each node will correspond to a VM
in Ravello. The name in Ironic and Ravello needs to be the same.  Then run the
following commands from a system with the python-ironicclient installed::

  $ ironic node-create -d pxe_ssh -n node1
  +--------------+--------------------------------------+
  | Property     | Value                                |
  +--------------+--------------------------------------+
  | uuid         | 05eac71f-3886-4acd-b0bd-069288dd8897 |
  | driver_info  | {}                                   |
  | extra        | {}                                   |
  | driver       | pxe_ssh                              |
  | chassis_uuid |                                      |
  | properties   | {}                                   |
  | name         | node1                                |
  +--------------+--------------------------------------+

Now to copy the SSH key created before the host running the Ironic conductor,
and update the driver properties::

  $ ironic node-update node1 add \
            driver_info/ssh_address=address.of.server \
            driver_info/ssh_username=raviron \
            driver_info/ssh_virt_type=virsh \
            driver_info/ssh_key_filename=/path/to/keyfile

Ironic needs to know the Mac address of the node. This information can be
obtained from the Ravello web UI::

  $ ironic port-create -n $NODE_UUID -a 00:11:22:33:44:55

There are other properties that you may need to set up in relation to PXE. That
is outside the scope of this document.

Make sure the node validates::

  $ ironic node-validate node1
  +------------+--------+-------------------------------+
  | Interface  | Result | Reason                        |
  +------------+--------+-------------------------------+
  | console    | None   | not supported                 |
  | deploy     | True   |                               |
  | inspect    | None   | not supported                 |
  | management | True   |                               |
  | power      | True   |                               |
  +------------+--------+-------------------------------+

You should now be able to power control your nodes::

  $ ironic node-set-power-state node1 on
  $ ironic node-set-power-state node1 off

Comments
--------

Feel free to report issues on github or mail me at geertj@gmail.com.
