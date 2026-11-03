FROM python:3.12-slim
WORKDIR /app
# Keine .pyc-Dateien schreiben (würden sonst per Bind-Mount root gehören)
ENV PYTHONDONTWRITEBYTECODE=1
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY *.py .
# Ordner wird beim Aufruf übergeben: docker compose run --rm etl data/source/2021-2024
ENTRYPOINT ["python", "main.py"]
