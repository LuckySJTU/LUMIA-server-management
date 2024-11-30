#!/bin/bash

SOURCE="/home/"
DESTINATION="/data2/homebak/"

find $SOURCE -maxdepth 1 -mindepth 1 -type d | parallel -j 16 rsync -av --delete --exclude /home/shared_home {} $DESTINATION

echo "$(date '+%Y-%m-%d %H:%M:%S') - Backup completed" >> /var/log/backup_home.log
