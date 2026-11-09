#!/bin/sh
# Раз в сутки сохраняет зашифрованную копию базы и удаляет копии старше KEEP_DAYS дней.
# Без pipefail ошибка pg_dump потерялась бы: код конвейера берётся у последней команды, gpg
set -eu -o pipefail
: "${BACKUP_PASSPHRASE:?Задайте BACKUP_PASSPHRASE}"
# Копии содержат финансы всех пользователей: читать их может только владелец
umask 077

while true; do
  name="/backups/walletly-$(date +%Y-%m-%d_%H%M).dump.gpg"
  # Пароль через отдельный дескриптор, а не аргументом: аргументы видны в списке процессов.
  # Сначала во временный файл: оборванная копия не должна выглядеть готовой
  if pg_dump --format=custom | gpg --batch --yes --pinentry-mode loopback --symmetric \
    --cipher-algo AES256 --passphrase-fd 3 --output "$name.tmp" 3<<PASS
$BACKUP_PASSPHRASE
PASS
  then
    mv "$name.tmp" "$name"
    echo "Копия создана: $name"
    if [ -n "${BACKUP_S3_BUCKET:-}" ]; then
      # Копия на том же диске не спасёт при потере сервера
      if rclone copy "$name" "backups:$BACKUP_S3_BUCKET/"; then
        echo "Копия выгружена во внешнее хранилище"
        rclone delete --min-age "${KEEP_DAYS}d" "backups:$BACKUP_S3_BUCKET/" || true
      else
        echo "ОШИБКА: копия не выгружена во внешнее хранилище" >&2
      fi
    else
      echo "ВНИМАНИЕ: внешнее хранилище не настроено, копия только на этом сервере" >&2
    fi
  else
    rm -f "$name.tmp"
    echo "ОШИБКА: копия не создана" >&2
  fi
  find /backups -name 'walletly-*.dump*' -mtime "+$KEEP_DAYS" -delete
  sleep 86400
done
