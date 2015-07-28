#!/bin/sh

rm -f /root/.ssh/authorized_keys
rm -f /root/.bash_history

sed -i '/ironic-proxy/!d' ~stack/.ssh/authorized_keys
rm -f ~stack/.bash_history

rm -f /var/lib/cloud/instance
rm -rf /var/lib/cloud/instances/*
find /var/lib/cloud -type f | xargs rm -f

rm -f /var/lib/dhclient/*.lease

updatedb
