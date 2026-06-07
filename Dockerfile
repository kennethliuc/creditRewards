FROM python:3.13-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    CREDITREWARDS_DATA_DIR=/app/data \
    CREDITREWARDS_USE_LOCAL_API=false \
    CREDITREWARDS_FETCH_EVIDENCE=0 \
    CREDITREWARDS_NOMINATIM=1

COPY pyproject.toml README.md ./
COPY src ./src
COPY data ./data

RUN pip install --no-cache-dir . \
    && credit-rewards-db init \
    && credit-rewards-db seed \
    && credit-rewards-db import-reference

COPY scripts/start_web.sh ./scripts/start_web.sh
RUN chmod +x ./scripts/start_web.sh

EXPOSE 8000

CMD ["./scripts/start_web.sh"]
