Ravello Trips and Tricks
========================

This document contains some tips and tricks for working with `Ravello Systems`_.

Uploading Images
----------------

The typical image types you might want to upload to Ravello are ISO
installation media and pre-installed cloud images. In order to do this you
need the Ravello image uploader.

I prefer to use the command-line uploader, as I think that is easier to work
with. The uploader works well and is quite efficient (e.g. it detects sparse
images), but has a few quirks. This section explains how I work around these.
These instructions assume a Unix like system (Mac should work too). I believe
the CLI uploader also supports Windows but I have never tried it.

Download the image uploader from here:
http://import-tool.ravellosystems.com/linux/ravello_linux.tar.gz

The image uploader is written in Python, and brings in a bunch of dependencies.
It is therefore useful to install it into a virtualenv. Create it like this::

  $ virtualenv ravello-upload

And activate it::

  $ source ravello-upload/bin/activate

Extract the uploader::

  $ tar xvfz ravello_linux.tar.gz
  $ cd ravello
  $ tar xvfz ravello-2.0.tar.gz
  $ cd ravello-2.0

The uploader wants to install some files in ``/etc/ravello`` and
``/opt/ravello``. This is a pain given that we want to install it under our own
user id in the virtualenv. Download `this patch`_ and store it in a file called
``ravello-venv.diff``. Then apply it::

  $ patch -p1 < ravello-venv.diff

Now install the uploader into the virtualenv using the following command. This
will also download all dependencies::

  $ python setup.py install

While we are at it, you probably also want to install the Ravello SDK::

  $ pip install ravello-sdk

The uploader understands the environment variable ``$RAVELLO_PASSWORD``. Set it
to your Ravello password::

  $ export RAVELLO_PASSWORD="Passw0rd"

Now you can upload images using the following command::

  $ ravello import-disk -u user@example.com file.img


Installing CentOS
-----------------

To install CentOS from scratch into Ravello, use the following instructions.

First download the latest CentOS cloud image from here:
http://cloud.centos.org/centos/7/images/. You need to make sure you download
the RAW image (**not** the QCOW2 file).

A cloud image is a hard drive image with a pre-installed operating system, that
has the following properties:

* It doesn't do any mac address binding of its network adapters. So you can
  basically put in any virtual NIC, and it will identify it correct as the
  first network interface.
* DHCP is enabled.
* If the image detects that the hard drive size has increased, it will increase
  the partition and the file system, so that the extra space can be used. This
  happens automatically in the initrd. This is also the reason that you need
  to download the RAW disk image. Ravello is not able to resize QCOW2 images.
* The image contains CloudInit so that an SSH key and other configuration can
  be injected

After this, create a new application in the Ravello web UI, go to the canvas,
and drag the VM named "Empty Cloud Image" to it. Quickly review the system
settings. Then, go to the "Disks" tab, remove the first disk, and replace it
with the CentOS RAW cloud image that you uploaded. Also make sure you configure
an SSH key for the VM.

If you want to run a hypervisor in the VM, then at this point you need to
enable nested SVM. Do this using the utility ``ravello-set-svm`` from the
``ravello-sdk`` package::

  $ ravello-set-svm --vm <appname> <vmname>

Now you can publish the application, and boot the VM.

If you want to move the VM to a static networking configuration then you have
to do that *after* the first boot. Log on to the VM, and change the files in
``/etc/sysconfig`` to reflect the new static networking configuration. Then
configure the *same* networking settings on the Ravello VM. Publish updates,
and then reboot the VM. The VM should come back up using the correct networking
configuration.

Inbound Network Access
----------------------

The network in a Ravello application is completely separate from the outside
network. The network is L2-clean, which means that you can do things like
broadcasting and multicasting, which allows you to do DHCP and PXE for example.

Access to the outside world is provided via NAT. Outbound access works as
expected via a router that is provided by Ravello. Inbound access is more
complicated. There are two options. The first option is that you assign an
entire IP address to a VM. In the GUI this is called "Public IP" and "Elastic
IP". In both these options you get an entire public IP address for your VM. The
benefit of this option is that port numbers on the outside are equal to those
on the inside. If you want to allow e.g. inbound access to SSH on port 22, it
will also be port 22 on the public IP address. The drawback of this approach is
that you use an overlay routing network that is managed by Ravello. This
network is significantly slower than the cloud provider's own networks.

The second option is called "port mapping" in the web UI. In this method, you
are sharing the IP of the underlying hypervisor VM that runs in the public
cloud. The drawback is that the port numbers will be different between the
outside and the inside. The benefit however is that you directly use the cloud
provider's network, making this option much faster.

My recommendation would be to try to use port mapping if your application can
work with it. SSH access should never be a problem. A web server would
typically work as well. The only issue is when the web server constructs URLs
to other resources inside the application. In this case the web server might
return an URL with a private Ravello IP address in it, which will not work.
This happens for example with the VNC console in OpenStack Horizon. In this
specific case, there is a configuration option that you can use to change the
URL generation. Not all web applications will have such options though, and in
this case you may be forced to use the public IP option.

In any case, for a web server, you need to make sure you correctly configure
any name based virtual host.  For Apache you want to make sure your
``<VirtualHost>`` definition contains the following line::

  ServerAlias *.srv.ravcloud.com

PXE Booting
-----------

PXE booting is not directly supported by Ravello, but can be made to work. To
make it work you need to do the following:

* Make sure that all the VMs on the boot network have a static IP configured.
  This will tell Ravello not to provide a DHCP server on the network.
* Provide your own DHCP and TFTP server with a proper configuration. The
  relevant DCHP options are ``next-server`` and ``filename``.
* Upload the iPXE boot CD-ROM and insert it into the VM's CD-ROM drive.
* The "bootOrder" attribute in the Ravello API not respected by Ravello. A VM
  will always boot from its disk first, and then from CD-ROM. You can work
  around this by clearing and re-setting the "boot" flag on the disk. This will
  allow you to boot from the network even if the disk as a boot loader
  installed on it.

.. _Ravello Systems: http://www.ravellosystems.com/
.. _this patch: https://gist.github.com/geertj/7b134e24323e6990f804
