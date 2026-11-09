#!/bin/sh
# Раз в сутки сохраняет базу и удаляет копии старше KEEP_DAYS дней.
set -eu

while true; do
  name="/backups/walletly-$(date +%Y-%m-%d_%H%M).dump"
  # Сначала во временный файл: оборванная копия не должна выглядеть как готовая
  if pg_dump --format=custom --file="$name.tmp"; then
    mv "$name.tmp" "$name"
    echo "Копия создана: $name"
  else
    rm -f "$name.tmp"
    echo "ОШИБКА: копия не создана" >&2
  fi
  find /backups -name 'walletly-*.dump' -mtime "+$KEEP_DAYS" -delete
  sleep 86400
done
