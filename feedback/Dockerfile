FROM python:3.12-slim

WORKDIR /app

RUN groupadd --gid 10001 app \
    && useradd --uid 10001 --gid app --home-dir /app --shell /usr/sbin/nologin --no-create-home app \
    && install -d -o app -g app /data \
    && chown app:app /app

# Copy dependencies first (layer-cached unless requirements change)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the shared Pretalx client from parent directory (copied by run.sh)
COPY --chown=app:app pretalx_client.py ./

# Copy fonts (copied by run.sh)
COPY --chown=app:app fonts/ static/fonts/

# Copy application code
COPY --chown=app:app app.py db.py auth.py pretalx_cache.py models.py data_loader.py ./
COPY --chown=app:app templates/ templates/
COPY --chown=app:app static/ static/

# Copy Alembic migration infrastructure
COPY --chown=app:app alembic.ini ./
COPY --chown=app:app migrations/ migrations/

# Data volume for the SQLite database
VOLUME ["/data"]

ENV PYTHONUNBUFFERED=1 \
    DB_PATH=/data/feedback.db \
    DATA_DIR=/data

EXPOSE 8091

USER app
RUN test -w /data

# Run Alembic migrations then start gunicorn.
CMD ["sh", "-c", "alembic upgrade head && exec gunicorn --bind 0.0.0.0:8091 --workers 1 --threads 4 --timeout 120 --log-level info --capture-output app:app"]
