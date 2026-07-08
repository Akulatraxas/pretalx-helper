FROM python:3.12-slim

WORKDIR /app

# Install dependencies first (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY app.py .
COPY pretalx_client.py .
COPY static/ static/

EXPOSE 8089

CMD ["python", "app.py"]
