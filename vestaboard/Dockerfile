ARG BUILD_FROM=python:3.12-slim
FROM ${BUILD_FROM}

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY vestaboard_ha/ ./vestaboard_ha/

CMD ["python", "-m", "vestaboard_ha"]
