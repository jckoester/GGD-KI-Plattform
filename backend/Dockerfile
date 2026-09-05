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

# Pandoc — Office-Export DOCX/ODT der Material-Werkstatt (Phase 19).
#
# ⚠️ Bewusst NICHT `apt-get install pandoc`. Der Debian-Bau bettet Pandocs
# Datendateien nicht in die Binärdatei ein, sondern legt sie unter
# /usr/share/pandoc/data/ ab. `--sandbox` (app/export/pandoc.py) verbietet genau
# solche Lesezugriffe — jede Konvertierung scheitert dann mit
# "Could not find data file docx/[Content_Types].xml". Aufgefallen 05.09.2026 im
# GitHub-Workflow (13 rote Tests); lokal blieb es verborgen, weil Homebrews Pandoc
# die Daten einbettet. Das offizielle .deb tut das ebenfalls.
#
# `--sandbox` ist kein Beiwerk: Der Export verarbeitet nutzereditierbares Markdown,
# die Sandbox verhindert \input-Ausbrüche. Sie zu streichen wäre der falsche Ausweg.
#
# Die letzten Zeilen sind eine Probe: Der Build konvertiert ein Testdokument mit
# --sandbox und bricht ab, wenn das nicht klappt. Lieber ein fehlgeschlagener Build
# als ein Image, dessen Office-Export erst im Betrieb versagt.
ARG PANDOC_VERSION=3.11
RUN arch="$(dpkg --print-architecture)" \
    && curl -fsSL -o /tmp/pandoc.deb \
        "https://github.com/jgm/pandoc/releases/download/${PANDOC_VERSION}/pandoc-${PANDOC_VERSION}-1-${arch}.deb" \
    && dpkg -i /tmp/pandoc.deb \
    && rm /tmp/pandoc.deb \
    && printf '# Titel\n\nText.\n' \
        | pandoc -f commonmark_x -t docx --sandbox -o /tmp/probe.docx \
    && test -s /tmp/probe.docx \
    && rm /tmp/probe.docx

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
