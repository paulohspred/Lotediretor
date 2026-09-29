# Python territorial engine (services/*.py) and data tooling (migrations,
# loaders, factory, legal ingestion). The repository is baked into the image
# at /srv/lotediretor/app, the path the engine expects.
FROM python:3.12-slim-bookworm
RUN apt-get update \
 && apt-get install -y --no-install-recommends gdal-bin postgresql-client poppler-utils curl \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /srv/lotediretor/app
COPY services/requirements.txt services/requirements.txt
RUN pip install --no-cache-dir -r services/requirements.txt
COPY services/ services/
COPY tools/ tools/
COPY database/ database/
COPY data/ data/
RUN useradd --system --uid 10001 engine && mkdir -p /var/cache/lotediretor && chown engine /var/cache/lotediretor
USER engine
WORKDIR /srv/lotediretor/app/services
EXPOSE 8765
CMD ["python3", "demo_parcel_api.py"]
