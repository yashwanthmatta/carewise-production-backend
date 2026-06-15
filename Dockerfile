FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=8000

WORKDIR /app

COPY pyproject.toml ./
RUN pip install --no-cache-dir .

COPY app ./app
COPY migrations ./migrations
COPY alembic.ini ./

EXPOSE 8000

CMD ["sh", "-c", "python -m app.db.migrate && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
