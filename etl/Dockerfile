FROM python:3.12-slim
WORKDIR /app
# Keine .pyc-Dateien schreiben (würden sonst per Bind-Mount root gehören)
ENV PYTHONDONTWRITEBYTECODE=1
# psql stellt den Database Dump wieder her
RUN apt-get update && apt-get install -y --no-install-recommends postgresql-client && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY *.py .
# Dump wird beim Aufruf übergeben: docker compose run --rm etl data/dumps/biofood_oltp_2024-12-31.sql.gz
ENTRYPOINT ["python", "main.py"]
