FROM python:3.12-slim

# System-Abhängigkeiten:
#  - cron, curl: Basisbetrieb (Cronjobs, Healthchecks)
#  - Pango/Cairo/GDK-PixBuf + libffi: Laufzeitbibliotheken für weasyprint
#    (Curriculum-PDF-Export, KS-Phase-6 Schritt 5)
#  - shared-mime-info: MIME-Erkennung für eingebettete Bilder
#  - fonts-liberation: Schriften (PDF-Template nutzt "Liberation Sans")
RUN apt-get update && apt-get install -y --no-install-recommends \
        cron \
        curl \
        libpango-1.0-0 \
        libpangocairo-1.0-0 \
        libpangoft2-1.0-0 \
        libgdk-pixbuf-2.0-0 \
        libcairo2 \
        libffi8 \
        shared-mime-info \
        fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
