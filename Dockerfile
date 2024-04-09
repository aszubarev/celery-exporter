FROM python:3.10.2-slim

WORKDIR /usr/local/celery-exporter/

ENV PYTHONFAULTHANDLER=1 \
  PYTHONUNBUFFERED=1 \
  PYTHONHASHSEED=random \
  # pip:
  PIP_NO_CACHE_DIR=off \
  PIP_DISABLE_PIP_VERSION_CHECK=on \
  PIP_DEFAULT_TIMEOUT=100 \
  # poetry:
  POETRY_VERSION=1.1.15

# System deps:
RUN apt-get update \
  && apt-get install --no-install-recommends -y \
    bash \
  # Cleaning cache:
  && apt-get autoremove -y && apt-get clean -y && rm -rf /var/lib/apt/lists/* \
  # Installing `poetry` package manager:
  # https://github.com/python-poetry/poetry
  && pip install --upgrade pip \
  && pip install "poetry==$POETRY_VERSION" && poetry --version


COPY poetry.lock poetry.lock
COPY pyproject.toml pyproject.toml

RUN poetry config virtualenvs.create false  \
    && poetry config experimental.new-installer false \
    && poetry install --no-interaction --no-ansi --no-dev

COPY . .
