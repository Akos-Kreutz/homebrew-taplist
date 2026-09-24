FROM python:3.14-alpine AS builder

WORKDIR /app

COPY requirements.txt .

RUN python3 -m venv /app/venv \
    && /app/venv/bin/pip install --no-cache-dir --require-hashes -r requirements.txt \
    && /app/venv/bin/pip uninstall -y pip

COPY app.py srm_colors.json ./
COPY templates ./templates
COPY static ./static
COPY mount ./mount

RUN python3 -m compileall -q /app && chown -R 10001:10001 /app/mount && rm requirements.txt

## ----- ##

FROM python:3.14-alpine

WORKDIR /app

ENV PYTHONUNBUFFERED=1 PATH=/app/venv/bin:$PATH

COPY --from=builder /app /app

# Remove the package manager (keep /lib/apk/db so scanners still see packages) and pip
RUN apk --no-cache upgrade \
    && apk del --purge apk-tools \
    && rm -rf /usr/local/bin/pip* /usr/local/lib/python3.14/site-packages/pip* \
              /usr/local/lib/python3.14/ensurepip /usr/local/lib/python3.14/idlelib /var/cache/apk /etc/apk

# Remove busybox (shell + ~300 applets) last, running it directly because /bin/sh goes away
RUN ["/bin/busybox", "sh", "-c", "for l in $(/bin/busybox find / -xdev -type l); do [ \"$(/bin/busybox readlink $l)\" = /bin/busybox ] && /bin/busybox rm -f $l; done; /bin/busybox rm -f /bin/busybox"]

USER 10001:10001

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python3", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/', timeout=4)"]
    
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "1", "--threads", "4", "--worker-tmp-dir", "/dev/shm", \
     "--no-control-socket", "--access-logfile", "-", "app:app"]