FROM python:3.12-slim

WORKDIR /app

# System libs required by opencv-python-headless
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ app/
COPY static/ static/
COPY templates/ templates/

# data/ is mounted as a volume at runtime — create empty dirs so the
# app doesn't crash on first start before the volume is attached
RUN mkdir -p data/config data/db data/uploads/receipts

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips=*"]
