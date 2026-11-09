FROM python:3.13-slim

RUN pip install --no-cache-dir uv==0.9.5
WORKDIR /app

# Сначала только файлы зависимостей: при правке кода этот слой берётся из кэша
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY . .
ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*'"]
