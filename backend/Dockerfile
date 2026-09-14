# Alya-FIIT backend image. Single stage: the image is small enough and the
# build stays easy to follow. Pinned to the interpreter we develop against.
FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Dependencies first so code edits do not invalidate the install layer.
# requirements.lock holds exact versions, including the dev and test tools so
# the suite can run inside the container; pyproject.toml keeps the looser
# ranges used by the cross-platform `task.py setup` path.
COPY requirements.lock pyproject.toml ./
RUN pip install --upgrade pip && pip install -r requirements.lock

COPY app ./app
COPY scripts ./scripts

# `app` is importable from WORKDIR, so the package itself needs no install.
# Database files live on a named volume mounted here (see docker-compose.yml).
RUN mkdir -p /app/data
ENV ALYA_DATABASE_URL=sqlite:////app/data/dev.db

EXPOSE 8000

# One worker: SQLite serialises writes, so extra workers buy nothing.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
