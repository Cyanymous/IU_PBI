FROM apache/superset:6.1.0

# Das offizielle Image enthält seit 4.1 keine Datenbanktreiber mehr.
# psycopg2 wird für die Metadaten-DB und für die Verbindung zum DWH gebraucht.
USER root
RUN uv pip install --python /app/.venv/bin/python --no-cache psycopg2-binary==2.9.10
USER superset
