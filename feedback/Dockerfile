FROM python:3.12-slim

WORKDIR /app

# Copy dependencies first (layer-cached unless requirements change)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the shared Pretalx client from parent directory (copied by run.sh)
COPY pretalx_client.py .

# Copy fonts (copied by run.sh)
COPY fonts/ static/fonts/

# Copy application code
COPY app.py db.py auth.py pretalx_cache.py models.py data_loader.py .
COPY templates/ templates/
COPY static/ static/

# Copy Alembic migration infrastructure
COPY alembic.ini .
COPY migrations/ migrations/

# Data volume for the SQLite database
VOLUME ["/data"]

ENV PYTHONUNBUFFERED=1 \
    DB_PATH=/data/feedback.db \
    DATA_DIR=/data

EXPOSE 8091

# Run Alembic migrations then start gunicorn.
CMD ["sh", "-c", "alembic upgrade head && gunicorn --bind 0.0.0.0:8091 --workers 1 --threads 4 --timeout 120 --log-level info --capture-output app:app"]
