FROM python:3.13-slim

RUN pip install --no-cache-dir uv==0.9.5
# Процессы работают не от root: уязвимость в библиотеке не даст прав администратора
RUN useradd --create-home --uid 10001 walletly
WORKDIR /app
# Пользователь не может писать в /app, поэтому байт-код готовим при сборке
ENV UV_COMPILE_BYTECODE=1

# Сначала только файлы зависимостей: при правке кода этот слой берётся из кэша
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY . .
ENV PATH="/app/.venv/bin:$PATH"
RUN python -m compileall -q app
USER walletly

EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*'"]
