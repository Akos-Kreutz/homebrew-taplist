FROM python:3.11-slim

RUN pip install --no-cache-dir flask

WORKDIR /app

COPY app.py .
COPY srm_colors.json .
COPY templates ./templates
COPY static ./static
COPY mount ./mount

EXPOSE 80

CMD ["python", "app.py"]
