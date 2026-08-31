FROM python:3.13.7-slim-bookworm@sha256:REPLACE_WITH_REVIEWED_IMAGE_DIGEST

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt requirements.lock /app/
RUN grep -q '^flask==' /app/requirements.lock \
    && pip install --require-hashes -r /app/requirements.lock
COPY app /app/app
COPY wsgi.py gunicorn.conf.py /app/

RUN addgroup --system --gid 10001 support-api \
    && adduser --system --uid 10001 --ingroup support-api --home /nonexistent \
        --no-create-home support-api \
    && install -d -o support-api -g support-api -m 0700 /data

USER 10001:10001

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD ["python", "-c", "import json,urllib.request; p=json.load(urllib.request.urlopen('http://127.0.0.1:8080/api/v1/health',timeout=3)); raise SystemExit(0 if p.get('status') == 'ok' else 1)"]

CMD ["gunicorn", "--config", "/app/gunicorn.conf.py", "wsgi:app"]
