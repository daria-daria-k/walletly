# Запуск на сервере

Всё нужное уже есть в репозитории. Настоящий выкат ещё не выполнялся: сервера и домена пока нет.

## Что понадобится

| Что | Где взять | Зачем |
|---|---|---|
| VPS: Ubuntu, от 2 ГБ памяти, 30 ГБ диска | любой хостинг | PyTorch занимает много памяти, 1 ГБ не хватит |
| Домен | регистратор | для HTTPS |
| SMTP-доступ | почтовый сервис | сброс пароля и подтверждение email |
| Ключи ЮKassa | личный кабинет | оплата Premium, сначала тестовый магазин |
| Токен бота | @BotFather | Telegram-бот |

Почта, ЮKassa и Telegram необязательны для старта: без них приложение работает, а соответствующие функции выключены. Без почты пользователи не смогут сбросить пароль: на сервере письма не пишутся в лог, потому что в них секретные ссылки.

## Защита сервера

Выполните до установки приложения. Сначала проверьте вход по ключу в отдельном окне, иначе можно потерять доступ.

1. Создайте пользователя с `sudo` и добавьте ему SSH-ключ.
2. В `/etc/ssh/sshd_config` задайте `PasswordAuthentication no` и `PermitRootLogin no`, затем `sudo systemctl restart ssh`.
3. Включите файрвол и защиту от подбора:

   ```bash
   sudo ufw allow 22,80,443/tcp
   sudo ufw enable
   sudo apt install -y fail2ban unattended-upgrades
   sudo dpkg-reconfigure -plow unattended-upgrades
   ```

Docker обходит правила ufw. Базу, API и веб закрывает привязка портов к `127.0.0.1` в Compose: не убирайте её.

## Шаги

1. Направьте A-запись домена на IP сервера. Откройте порты 22, 80 и 443, остальные закройте.
2. Установите Docker и клонируйте репозиторий.
3. Создайте `.env` по образцу `.env.example`:

   ```bash
   cp .env.example .env
   openssl rand -hex 32   # значение для JWT_SECRET
   openssl rand -hex 24   # значение для POSTGRES_PASSWORD
   ```

   Добавьте `DOMAIN=ваш-домен.ru` и `BACKUP_PASSPHRASE` (тоже `openssl rand -hex 32`), заполните SMTP, ЮKassa и Telegram. `JWT_SECRET` короче 32 символов приложение не примет. Закройте файл от других пользователей: `chmod 600 .env`.
4. Запустите:

   ```bash
   docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
   ```

   Миграции применятся сами, сертификат HTTPS Caddy получит сам.
5. Зарегистрируйтесь на сайте и выдайте себе роль администратора:

   ```bash
   docker exec walletly-api python -m app.cli make-admin ваш@email.ru
   ```

6. В кабинете ЮKassa укажите адрес уведомлений `https://ваш-домен.ru/api/billing/yookassa/webhook` и событие `payment.succeeded`.

## Бэкапы

Контейнер `backup` раз в сутки кладёт зашифрованную копию базы в `backups/` и хранит 14 дней (`BACKUP_KEEP_DAYS`).

**Сохраните `BACKUP_PASSPHRASE` вне сервера**, например в менеджере паролей. Без него копии не расшифровать.

**Копии на том же сервере не спасут при его потере.** Задайте в `.env` параметры `BACKUP_S3_*` любого хранилища с протоколом S3, и каждая копия будет выгружаться туда. Пока они не заданы, в логе контейнера при каждом запуске будет предупреждение.

Проверка копии без риска для рабочих данных:

```bash
./deploy/restore.sh backups/имя-файла.dump.gpg
```

Восстановление рабочей базы: остановите `api`, `worker`, `bot` и передайте вторым аргументом имя рабочей базы.

## Мониторинг

Необязательный профиль, Grafana доступна только на самом сервере:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml --profile monitoring up -d
ssh -L 3000:localhost:3000 пользователь@сервер   # затем http://localhost:3000
```

Пароль администратора Grafana задаётся в `GRAFANA_PASSWORD`.

## Эксперименты с моделями

```bash
docker compose --profile ml up -d mlflow
```

В `.env` добавьте `MLFLOW_TRACKING_URI=http://mlflow:5000` и пересоздайте `worker`. Интерфейс: http://localhost:5001.

Обучить модели вручную, не дожидаясь ночи:

```bash
docker exec walletly-worker python -m app.ml.train
```

## CI/CD

- `.github/workflows/ci.yml` запускает тесты и сборку при каждом пуше.
- `.github/workflows/deploy.yml` запускается вручную и обновляет сервер. Нужны секреты `DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_SSH_KEY`, `DEPLOY_PATH`.

В исходном плане был GitLab CI, но репозиторий находится на GitHub, поэтому использованы GitHub Actions.
