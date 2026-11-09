#!/bin/sh
# Восстановление из копии: ./deploy/restore.sh backups/walletly-2026-11-09_0300.dump.gpg [имя_базы]
# Без имени базы восстанавливает в проверочную walletly_restore_check, рабочие данные не трогает.
set -eu

file="${1:?Укажите файл копии}"
target="${2:-walletly_restore_check}"
user="$(docker exec walletly-db printenv POSTGRES_USER)"

docker exec walletly-db psql -U "$user" -d postgres -v ON_ERROR_STOP=1 \
  -c "DROP DATABASE IF EXISTS \"$target\" WITH (FORCE)" \
  -c "CREATE DATABASE \"$target\""
# Расшифровка идёт в контейнере бэкапов: только там есть пароль и gpg
docker exec -i walletly-backup decrypt.sh < "$file" \
  | docker exec -i walletly-db pg_restore -U "$user" -d "$target" --no-owner --exit-on-error
docker exec walletly-db psql -U "$user" -d "$target" -c "SELECT count(*) AS users FROM users" -c "SELECT count(*) AS transactions FROM transactions"
