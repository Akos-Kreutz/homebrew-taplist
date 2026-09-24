# Pinned by digest so rebuilds use exactly this base image.
# Update the tag and digest together when moving to a newer Python release.
FROM python:3.14.7-slim-trixie@sha256:caaf356f40667c496d405780745b9ac25771c189a51dfcc42430d531ea09f8a2

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Apply OS security updates and create an unprivileged runtime user
RUN apt-get update \
    && apt-get upgrade -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --no-create-home --shell /usr/sbin/nologin app

WORKDIR /app

# Dependencies are pinned with hashes, see requirements.in
COPY requirements.txt .
RUN pip install --no-cache-dir --require-hashes -r requirements.txt

# Application code stays owned by root, so the app user can't modify it
COPY app.py srm_colors.json ./
COPY templates ./templates
COPY static ./static

# Only the mount folder (drinks.json and images) is writable by the app user
COPY --chown=app:app mount ./mount

USER app

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/', timeout=4)"]

# Single worker so the in-memory login rate limit is shared; threads handle concurrency.
# Heartbeat file in /dev/shm and no control socket, so the container runs with --read-only.
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "1", "--threads", "4", \
     "--worker-tmp-dir", "/dev/shm", "--no-control-socket", "--access-logfile", "-", "app:app"]
