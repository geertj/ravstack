RDO Manager Notes
=================

This document contains some notes related to the installation of the RDO
Manager image on the Ravello Repo.

Networking
----------

The RDO Manager uses an access network and a management network, as described
in the `RDO-Manager documentation`.

The network settings are:

==========  =========  ==============
Network     Interface  Subnet
==========  =========  ==============
Access      eth0       192.168.2.0/24
Management  eth1       192.168.4.0/24
==========  =========  ==============

dnsmasq
-------

I noticed that a DHCP server is needed on the access network. If it is not
there, eth0 cannot be initialized (obviously), but it also prevented the other
interfaces from initializing, thereby breaking the install.

The solution is to install a separate dnsmasq instance on the undercloud VM.
The trick is that this DHCP server should *not* provide an IP address to iPXE,
otherwise the discovery and deployment will fail. We fix that using a special
configuration that ignores requests coming from iPXE. For the full details see
the file dnsmasq.conf_ on Github.

iPXE
----

You need a custom iPXE ISO with RDO-Manager. The ISO differs in the following
way from the one http://boot.ipxe.org/ipxe.iso: using a `custom boot script`_,
the ISO will reboot the VM instead if it could not boot from the network,
rather than exiting. This behavior will prevent the VM from falling back to
booting from a local disk as long as the bootable CD-ROM is present.

This is needed for the Ironic PXE deployment to work. From a high level this is
what happens during image deployment:

1. Node boots into deployment initrd.
2. Initrd exposes root disk via iSCSI.
3. Ironic installs image to disk via iSCSI.
4. Ironic set boot device to "disk" (Ravello API call)
5. Initrd Install boot loader.
6. The VM reboots itself
7. Ironic cycles the VM (Ravello API call)

The issue with the approach above is that #6 I noticed that will boot into the
just installed OS before Ironic issues #7. The result is that the first boot
cycle is interrupted by #7 mid-cycle. This resulted in a partial CloudInit
configuration, which broke the subsequent post-configuration

A second issue, not related to Ironic, is that step #4 if executed directly
against the Ravello API will reboot the VM. This would interrupt the first boot
as well (it would typically make it past the boot loader). The solution there
is to store an "intent to change boot device" in the VM description, and then
at the next power cycle actually apply that change. For the gory details, see
the file nodes.py_ on Github.


.. _RDO-Manager documentation: https://repos.fedorapeople.org/repos/openstack-m/docs/master/environments/baremetal.html#networking
.. _custom boot script: https://github.com/geertj/ravstack/blob/master/share/script.ipxe
.. _dnsmasq.conf: https://github.com/geertj/ravstack/blob/master/share/dnsmasq.conf
.. _nodes.py: https://github.com/geertj/ravstack/blob/master/lib/ravstack/node.py#L363.
