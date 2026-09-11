# Pinned here rather than in build.yaml, which Supervisor now reports as
# deprecated ("move build parameters into the Dockerfile directly"). Its
# build_from validator also rejects official library images: the pattern wants
# at least an owner/name pair, so a bare "python:3.12-slim" fails it and
# Supervisor silently falls back to its own Alpine base, which has no pip.
# This image is multi-arch: amd64, arm64, armv7, 386.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY vestaboard_ha/ ./vestaboard_ha/

CMD ["python", "-m", "vestaboard_ha"]
