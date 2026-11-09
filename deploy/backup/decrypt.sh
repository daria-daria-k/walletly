#!/bin/sh
# Читает зашифрованную копию из stdin и отдаёт расшифрованную в stdout
set -eu
exec gpg --batch --quiet --pinentry-mode loopback --passphrase-fd 3 --decrypt 3<<PASS
$BACKUP_PASSPHRASE
PASS
