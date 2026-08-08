# MetaHarmonizer backend — dev image.
# Single image used for both the API (uvicorn) and the arq worker; the
# docker-compose `command` selects which one runs.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# System deps: build tools for wheels, curl for healthchecks, and PostgreSQL
# client tools for encrypted backup/restore operations.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps first (better layer caching). The vendored engine wheel
# is referenced from requirements.txt, so copy it before installing.
COPY requirements.txt ./
COPY vendor/ ./vendor/
RUN python -m pip install pip==26.2.1 \
    && pip install -r requirements.txt

# App code (bind-mounted over this in dev via compose, but copied so the
# image is runnable standalone too).
COPY . .

EXPOSE 8000

# Default command = API. The worker service overrides this in compose.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
