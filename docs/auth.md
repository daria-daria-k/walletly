# Walletly — авторизация

## Принятые решения

| Вопрос | Решение |
|--------|---------|
| Схема токенов | Access (JWT, 15 мин) + refresh (случайная строка, 30 дней) с ротацией |
| Хранение refresh на сервере | Таблица `refresh_tokens`, хранится **SHA-256 хеш**, не сам токен |
| Хеширование паролей | Argon2id через `pwdlib` |
| Библиотека JWT | `PyJWT`, алгоритм HS256, секрет в `.env` (`JWT_SECRET`) |
| Хранение на фронтенде | Access — в памяти JS, заголовок `Authorization: Bearer ...`; refresh — httpOnly cookie |
| Подтверждение email | Пока нет (нет почтового сервера), вернёмся на этапе 3 |

## Потоки

**Регистрация** `POST /auth/register` — создаёт пользователя, личный ledger (owner), подписку free и шаблон категорий. Одна транзакция БД: либо всё, либо ничего.

**Вход** `POST /auth/login` — проверка пароля → access в теле ответа + refresh в cookie.

**Обновление** `POST /auth/refresh` — refresh из cookie → старый помечается отозванным, выдаётся новая пара (ротация).
Если пришёл **уже отозванный** refresh — это признак кражи: отзываются все refresh-токены пользователя.

**Выход** `POST /auth/logout` — отзыв текущего refresh, удаление cookie.

**Текущий пользователь** — зависимость `get_current_user`: проверяет подпись и срок access, загружает пользователя из БД и проверяет `is_active`. Поэтому блокировка срабатывает сразу, а не через 15 минут.

## Таблица refresh_tokens

| Поле | Тип | Примечание |
|------|-----|-----------|
| id | bigint PK | |
| user_id | FK → users ON DELETE CASCADE | индекс |
| token_hash | char(64) UNIQUE | SHA-256 от токена |
| expires_at | timestamptz | |
| revoked_at | timestamptz NULL | NULL — действует |
| created_at | timestamptz | |
