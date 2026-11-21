FROM python:3.12-slim-bookworm

WORKDIR /srv/datasleuth
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

COPY pyproject.toml ./
COPY app ./app
RUN python -m pip install --no-cache-dir . \
    && useradd --system --uid 10001 --create-home datasleuth
COPY alembic.ini ./
COPY alembic ./alembic
COPY start-render.sh ./start-render.sh

USER 10001
CMD ["python", "-m", "app.serve"]
