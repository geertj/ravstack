#!/bin/sh

for home in /root /home/*; do
    sed -i '/ovirt\|ravstack/!d' $home/.ssh/authorized_keys
    rm -f $home/.bash_history
done

rm -f /var/lib/cloud/instance
rm -rf /var/lib/cloud/instances/*
find /var/lib/cloud -type f | xargs rm -f

rm -f /var/lib/dhclient/*.lease

cp -f /dev/null /var/run/utmp
cp -f /dev/null /var/log/btmp
cp -f /dev/null /var/log/wtmp

which updatedb >/dev/null 2>&1 && updatedb
sync
