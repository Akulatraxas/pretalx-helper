FROM python:3.12-slim

WORKDIR /app

# Copy dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the shared Pretalx client from parent directory (mounted at build time via run.sh)
COPY pretalx_client.py .

# Copy fonts from the sibling web/ app
COPY fonts/ static/fonts/

# Copy application code
COPY app.py db.py auth.py pretalx_cache.py .
COPY templates/ templates/
COPY static/ static/

# Data volume for the SQLite database
VOLUME ["/data"]

ENV PYTHONUNBUFFERED=1 \
    DB_PATH=/data/operations.db

EXPOSE 8090

CMD ["gunicorn", "--bind", "0.0.0.0:8090", "--workers", "1", "--threads", "1", "--timeout", "120", "app:app"]
