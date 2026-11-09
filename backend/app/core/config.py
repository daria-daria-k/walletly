from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL


class Settings(BaseSettings):
    """Настройки приложения. Значения берутся из переменных окружения или файла .env."""

    # .env ищется в папке запуска (backend/), затем в корне проекта
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore")

    postgres_user: str
    postgres_password: str
    postgres_db: str
    postgres_host: str = "localhost"
    postgres_port: int = 5432

    # True — SQLAlchemy печатает каждый SQL-запрос в консоль
    db_echo: bool = False

    # Секрет подписи JWT: кто его знает, тот может выпустить токен от имени любого пользователя
    jwt_secret: str
    access_token_ttl_minutes: int = 15
    refresh_token_ttl_days: int = 30
    # Secure-cookie передаётся только по HTTPS. Локально HTTPS нет — на сервере включим
    cookie_secure: bool = False

    redis_url: str = "redis://localhost:6379/0"
    # Адрес приложения для ссылок в письмах
    app_url: str = "http://localhost:8080"
    # Без smtp_host письма печатаются в лог
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "Walletly <noreply@walletly.local>"
    smtp_tls: bool = True

    # Ключи ЮKassa: тестового магазина при разработке, боевого после договора
    yookassa_shop_id: str = ""
    yookassa_secret_key: str = ""
    premium_price_rub: int = 299

    # Пусто — обучение идёт без записи экспериментов
    mlflow_tracking_uri: str = ""

    @property
    def database_url(self) -> URL:
        # URL.create сам экранирует спецсимволы в пароле, в отличие от f-строки
        return URL.create(
            drivername="postgresql+asyncpg",
            username=self.postgres_user,
            password=self.postgres_password,
            host=self.postgres_host,
            port=self.postgres_port,
            database=self.postgres_db,
        )


settings = Settings()
