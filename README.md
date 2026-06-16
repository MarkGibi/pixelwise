# PixelWise – API-Performance-Erweiterung

PixelWise ist eine kleine Fullstack-Anwendung zur Klassifikation handgezeichneter Ziffern. Das System besteht aus einem Browser-Frontend, einer FastAPI-Schnittstelle, einem Machine-Learning-Modell, PostgreSQL zur Speicherung der Ergebnisse und einem Deployment auf einer separaten Produktions-VM.

Im Rahmen der Projekterweiterung wurde die bestehende API um einen Batch-Endpoint ergänzt und anschließend mit Benchmark- und Stress-Tests ausgewertet.

## Ziel der Erweiterung

Der ursprüngliche Endpoint `/classify` verarbeitet pro HTTP-Request genau ein Bild. Dadurch entstehen bei vielen Bildern entsprechend viele einzelne Requests und Datenbankzugriffe.

Ziel der Erweiterung war es, zu untersuchen, ob ein zusätzlicher Batch-Endpoint den Durchsatz der API verbessert. Dafür wurde der Endpoint `/classify/batch` implementiert. Dieser nimmt mehrere Bilder in einem Request entgegen, klassifiziert sie gesammelt und speichert die Ergebnisse anschließend in der Datenbank.

Zentrale Fragestellung:

Wie stark verbessert ein Batch-Endpoint den Bilddurchsatz der PixelWise-API im Vergleich zu einzelnen Klassifikationsrequests?

## Architektur

Die Anwendung besteht aus folgenden Komponenten:

- `frontend/` – statisches Browser-Frontend mit Zeichenfläche
- `app/main.py` – FastAPI-Anwendung mit API-Endpunkten
- `app/classifier.py` – Einbindung des trainierten Klassifikationsmodells
- `app/models.py` – Datenbankmodell für gespeicherte Vorhersagen
- `deploy/` – systemd- und Nginx-Konfiguration
- `scripts/benchmark_api.py` – Benchmark- und Stress-Test-Skript
- `results/` – gemessene Benchmark-Ergebnisse

Testarchitektur:

```text
dev VM -> prod VM -> Nginx -> FastAPI -> ML-Modell -> PostgreSQL
```

## API-Endpunkte

### Health Check

    GET /health

Gibt den Status der API zurück.

### Einzelklassifikation

    POST /classify

Der Endpoint verarbeitet ein einzelnes 28x28-Bild und speichert die Vorhersage in PostgreSQL.

### Batch-Klassifikation

    POST /classify/batch

Der Endpoint verarbeitet mehrere 28x28-Bilder in einem Request. Für jedes Bild wird eine Vorhersage erzeugt. Die Ergebnisse werden gesammelt in PostgreSQL gespeichert.

## Setup

Repository klonen:

    git clone https://github.com/MarkGibi/pixelwise.git
    cd pixelwise

Umgebung vorbereiten:

    bash setup-server.sh
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt

`.env` anlegen:

    cp .env.example .env
    nano .env

Beispielwerte:

    PIXELWISE_ENV=development
    MODEL_REPO=https://github.com/schutera/pixelwise-model.git
    MODEL_VERSION=v1.0
    MODEL_PATH=models/digit_classifier_v1.pkl

    SECRET_API_KEY=dev-secret-key
    DB_PASSWORD=database

    CLASSIFY_RATE_LIMIT=1000/minute
    BATCH_RATE_LIMIT=1000/minute

Datenbank initialisieren:

    python3 init_db.py

API lokal starten:

    python3 -m uvicorn app.main:app --reload --port 8000

Health Check:

    curl -s http://localhost:8000/health

## Tests

Die automatisierten Tests können mit folgendem Befehl gestartet werden:

    python3 -m pytest tests/

Die Tests prüfen unter anderem:

- Grundfunktion der Klassifikation
- Zugriffsschutz durch API-Key
- Batch-Endpoint mit mehreren Bildern
- Ablehnung leerer Batch-Anfragen

## Benchmark und Stress-Test

Für die Messung wurde das Skript `scripts/benchmark_api.py` erstellt.

Benchmark gegen die Produktions-VM über Nginx:

    python3 scripts/benchmark_api.py \
      --base-url http://192.168.56.11/api \
      --api-key dev-secret-key \
      --total-images 100 \
      --concurrency-levels 1,5,10 \
      --batch-sizes 5,10,25,50 \
      --output results/benchmark_prod.csv

Stress-Test gegen die Produktions-VM:

    python3 scripts/benchmark_api.py \
      --base-url http://192.168.56.11/api \
      --api-key dev-secret-key \
      --total-images 300 \
      --concurrency-levels 20,30 \
      --batch-sizes 10,25,50 \
      --timeout 60 \
      --output results/stress_prod.csv

Gemessen werden unter anderem:

- Gesamtzeit
- Requests pro Sekunde
- Bilder pro Sekunde
- durchschnittliche Latenz
- p50-, p95- und p99-Latenz
- maximale Latenz
- erfolgreiche und fehlgeschlagene Requests
- HTTP-Statuscodes

## Ergebnisse

Die Messungen zeigen, dass der Batch-Endpoint den Bilddurchsatz deutlich erhöht.

Auszug aus dem Benchmark gegen die Produktions-VM:

| Szenario | Bilder | Concurrency | Batchgröße | Bilder/s | Fehler |
|---|---:|---:|---:|---:|---:|
| Einzelrequests | 100 | 1 | 1 | 7,64 | 0 |
| Batch | 100 | 1 | 50 | 152,14 | 0 |
| Einzelrequests | 100 | 10 | 1 | 5,58 | 0 |
| Batch | 100 | 10 | 50 | 230,28 | 0 |

Im Stress-Test mit 300 Bildern und 30 parallelen Worker-Threads blieb die Fehlerrate bei 0 %. Der Einzelrequest-Endpoint erreichte ca. 11,22 Bilder/s. Der Batch-Endpoint mit Batchgröße 50 erreichte ca. 231,61 Bilder/s.

Die Ergebnisse zeigen, dass die API innerhalb der getesteten Lastgrenzen stabil blieb. Die Belastung zeigte sich vor allem durch steigende Antwortzeiten. Gleichzeitig konnte der Batch-Endpoint die Anzahl notwendiger HTTP-Requests deutlich reduzieren und den Bilddurchsatz stark erhöhen.

## Fazit

Die Erweiterung zeigt, dass Batch-Verarbeitung für die PixelWise-API einen deutlichen Performance-Vorteil bringt. Besonders bei vielen zu klassifizierenden Bildern reduziert der neue Endpoint den Request-Overhead und erhöht den Durchsatz.

Für eine produktionsnähere Weiterentwicklung wären zusätzliche Messungen mit mehreren Uvicorn-Workern, Monitoring und größeren Datenmengen sinnvoll.
