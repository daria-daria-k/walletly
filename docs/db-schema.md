# Walletly — схема базы данных

PostgreSQL. Все `id` — `BIGINT GENERATED ALWAYS AS IDENTITY`, все даты-время — `TIMESTAMPTZ`, деньги — `NUMERIC(12, 2)`.

## Принятые решения

| # | Вопрос | Решение | Почему |
|---|--------|---------|--------|
| 1 | Кому принадлежат данные | **Пространства (ledgers).** Счета, категории, транзакции принадлежат ledger. У каждого пользователя есть личный ledger, семья — это общий ledger | Один код для личного и семейного режима, общие счета возможны |
| 2 | Остаток счёта | **Вычисляется**: `initial_balance` + движения по транзакциям | Остаток не может разойтись с историей; кэш в Redis — позже, если понадобится |
| 3 | Переводы | **`type = transfer`** + `to_account_id` | Переводы не искажают доходы/расходы в аналитике |
| 4 | Группы категорий | **Отдельная таблица `category_groups`** | Пользователь сможет переименовывать группы и создавать свои |
| 5 | Шаблон категорий | Копируется в ledger при его создании | Пользователь свободно редактирует свою копию |
| 6 | Удаление | Счета/категории не удаляются, если на них есть транзакции (`ON DELETE RESTRICT`), вместо этого `is_active = false`. Транзакции — мягкое удаление `is_deleted` | История не теряется |

## Связи

```
users ─1:N─ subscriptions
users ─N:M─ ledgers            (через ledger_members, роль внутри ledger)
ledgers ─1:N─ invitations
ledgers ─1:N─ accounts
ledgers ─1:N─ category_groups ─1:N─ categories
ledgers ─1:N─ transactions
transactions ─N:1─ users (автор), accounts, accounts (to_account), categories
```

## Таблицы (9)

### users — пользователи
| Поле | Тип | Примечание |
|------|-----|-----------|
| id | bigint PK | |
| email | varchar(255) UNIQUE NOT NULL | хранить в нижнем регистре |
| password_hash | varchar(255) NOT NULL | bcrypt/argon2, не пароль |
| name | varchar(100) NOT NULL | |
| role | enum `user_role` (user, admin) | роль **в системе** |
| is_active | bool default true | блокировка админом |
| created_at | timestamptz default now() | |

### subscriptions — подписки
| Поле | Тип | Примечание |
|------|-----|-----------|
| id | bigint PK | |
| user_id | FK → users ON DELETE CASCADE | |
| plan | enum `plan` (free, premium) | |
| starts_at | timestamptz NOT NULL | |
| expires_at | timestamptz NULL | NULL — бессрочно (free) |

### ledgers — пространства (личные и семейные)
| Поле | Тип | Примечание |
|------|-----|-----------|
| id | bigint PK | |
| name | varchar(100) NOT NULL | «Личное», «Семья» |
| type | enum `ledger_type` (personal, shared) | |
| owner_id | FK → users | |
| created_at | timestamptz | |

Ограничение: у пользователя ровно один personal ledger — частичный уникальный индекс `UNIQUE (owner_id) WHERE type = 'personal'`.

### ledger_members — участники пространства
| Поле | Тип | Примечание |
|------|-----|-----------|
| id | bigint PK | |
| ledger_id | FK → ledgers ON DELETE CASCADE | |
| user_id | FK → users ON DELETE CASCADE | |
| role | enum `member_role` (owner, admin, member) | роль **внутри ledger** |
| joined_at | timestamptz | |

`UNIQUE (ledger_id, user_id)`.

### invitations — приглашения
| Поле | Тип | Примечание |
|------|-----|-----------|
| id | bigint PK | |
| ledger_id | FK → ledgers ON DELETE CASCADE | |
| email | varchar(255) NOT NULL | кого пригласили |
| invited_by | FK → users | |
| token | varchar(64) UNIQUE NOT NULL | случайный, для ссылки |
| status | enum (pending, accepted, declined, expired) | |
| expires_at | timestamptz NOT NULL | |
| created_at | timestamptz | |

### category_groups — группы категорий
| Поле | Тип | Примечание |
|------|-----|-----------|
| id | bigint PK | |
| ledger_id | FK → ledgers ON DELETE CASCADE | |
| name | varchar(50) NOT NULL | «Базовые», «Текущие», «Крупные», «Доходы» |
| type | enum `category_type` (income, expense) | тип наследуют все категории группы |
| sort_order | int | |

Шаблон при создании ledger: Доходы (income), Базовые / Текущие / Крупные (expense).

### categories — категории
| Поле | Тип | Примечание |
|------|-----|-----------|
| id | bigint PK | |
| ledger_id | FK → ledgers ON DELETE CASCADE | |
| category_group_id | FK → category_groups ON DELETE RESTRICT | |
| name | varchar(50) NOT NULL | |
| is_active | bool default true | |
| sort_order | int | |

`UNIQUE (category_group_id, name)`.

### accounts — счета
| Поле | Тип | Примечание |
|------|-----|-----------|
| id | bigint PK | |
| ledger_id | FK → ledgers ON DELETE CASCADE | |
| name | varchar(50) NOT NULL | Сбер, ВТБ, Хлынов, вклад, наличные |
| currency | char(3) default 'RUB' | |
| initial_balance | numeric(12,2) default 0 | остаток на момент начала учёта |
| is_active | bool default true | |
| sort_order | int | |

### transactions — транзакции
| Поле | Тип | Примечание |
|------|-----|-----------|
| id | bigint PK | |
| ledger_id | FK → ledgers ON DELETE CASCADE | |
| user_id | FK → users | **автор** записи |
| type | enum `tx_type` (income, expense, transfer) | |
| amount | numeric(12,2) NOT NULL | всегда > 0, знак определяет `type` |
| account_id | FK → accounts ON DELETE RESTRICT | откуда / куда (для income) |
| to_account_id | FK → accounts NULL | только для transfer |
| category_id | FK → categories NULL | только для income/expense |
| description | varchar(500) | пригодится для ML-категоризации |
| tx_date | date NOT NULL | дата операции |
| is_deleted | bool default false | |
| created_at | timestamptz | дата создания записи |

CHECK-ограничения:
- `amount > 0`
- `type = 'transfer'` ⇒ `to_account_id IS NOT NULL AND category_id IS NULL AND to_account_id <> account_id`
- `type IN ('income','expense')` ⇒ `category_id IS NOT NULL AND to_account_id IS NULL`

Проверяется в коде (сервисный слой): счёт и категория принадлежат тому же ledger, тип категории совпадает с типом транзакции.

Индексы: `(ledger_id, tx_date)` — история и аналитика, `(account_id)` и `(to_account_id)` — остатки.

## Формула остатка

```
balance(account) = initial_balance
                 + Σ income   где account_id = account
                 − Σ expense  где account_id = account
                 − Σ transfer где account_id = account
                 + Σ transfer где to_account_id = account
(только is_deleted = false)
```
