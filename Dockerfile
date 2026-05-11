# syntax=docker/dockerfile:1.7
FROM python:3.12-slim-bookworm

ARG MT_DOWNLOADER_VERSION=1.3.5

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN groupadd --system --gid 1000 app \
 && useradd  --system --uid 1000 --gid app --home /home/app --create-home app \
 && mkdir -p /maps \
 && chown app:app /maps

RUN pip install --no-cache-dir "mt-downloader==${MT_DOWNLOADER_VERSION}"

USER app
WORKDIR /maps
VOLUME ["/maps"]

ENTRYPOINT ["mt-downloader"]
