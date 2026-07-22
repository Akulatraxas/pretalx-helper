FROM python:3.12-slim

WORKDIR /app

# Copy dependencies first (layer-cached unless requirements change)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the shared Pretalx client from parent directory (copied by run.sh)
COPY pretalx_client.py .

# Copy fonts from the sibling web/ app (copied by run.sh)
COPY fonts/ static/fonts/

# Copy application code
COPY app.py db.py auth.py pretalx_cache.py models.py .
COPY templates/ templates/
COPY static/ static/

# Copy Alembic migration infrastructure
COPY alembic.ini .
COPY migrations/ migrations/

# Data volume for the SQLite database
VOLUME ["/data"]

ENV PYTHONUNBUFFERED=1 \
    DB_PATH=/data/operations.db

EXPOSE 8090

# Run Alembic migrations then start gunicorn.
# Using a single worker + threads because SQLite WAL handles concurrent reads
# well, but write serialisation happens at the DB level anyway.
CMD ["sh", "-c", "alembic upgrade head && gunicorn --bind 0.0.0.0:8090 --workers 2 --threads 4 --timeout 120 app:app"]
