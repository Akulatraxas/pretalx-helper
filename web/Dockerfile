FROM python:3.12-slim

WORKDIR /app

# Install dependencies first (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY app.py .
COPY pretalx_client.py .
COPY pretalx_xml_exporter.py .
COPY static/ static/

EXPOSE 8089

CMD ["gunicorn", "--bind", "0.0.0.0:8089", "--workers", "2", "--timeout", "120", "app:app"]
