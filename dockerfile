FROM python:3.14.4-slim-trixie

USER root

RUN apt update \
    && apt upgrade -y --no-install-recommends

RUN pip install --upgrade pip

RUN pip install --no-cache-dir flask flask-login

WORKDIR /app

COPY app.py .
COPY srm_colors.json .
COPY templates ./templates
COPY static ./static
COPY mount ./mount

EXPOSE 80

CMD ["python", "app.py"]
