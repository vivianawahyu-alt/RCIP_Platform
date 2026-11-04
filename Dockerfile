FROM python:3.11-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app
# tesseract-ocr = mesin OCR (membaca tulisan dari gambar)
# tesseract-ocr-ind / -eng = kamus bahasa Indonesia & Inggris agar hasil baca lebih akurat (FR-RKM-004)
RUN apt-get update && apt-get install -y --no-install-recommends build-essential libpq-dev \
        tesseract-ocr tesseract-ocr-ind tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
