# MetaHarmonizer backend — dev image.
# Single image used for both the API (uvicorn) and the arq worker; the
# docker-compose `command` selects which one runs.
FROM python:3.12-slim@sha256:2c941e860699f878900b0edc2403613c234d4b32eda3cc9fa7036991a2a63c4a AS builder

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HOME=/home/app

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps first (better layer caching). The vendored engine wheel
# is referenced from requirements.txt, so copy it before installing.
COPY requirements.txt ./
COPY vendor/ ./vendor/
ARG TARGETARCH
ARG TORCH_VERSION=2.14.0
RUN set -eux; \
    tr -d '\r' < requirements.txt | grep -Fqx "torch>=${TORCH_VERSION}"; \
    case "$TARGETARCH" in \
      amd64) \
        torch_wheel="https://download-r2.pytorch.org/whl/cpu/torch-${TORCH_VERSION}%2Bcpu-cp312-cp312-manylinux_2_28_x86_64.whl#sha256=a09987c95ec4cffdb6df798d3d641558110a334cfccce22f2f046d83142bc260" \
        ;; \
      arm64) \
        torch_wheel="https://download-r2.pytorch.org/whl/cpu/torch-${TORCH_VERSION}%2Bcpu-cp312-cp312-manylinux_2_28_aarch64.whl#sha256=da8140c3d4a41500d29710e35bf8e66a4295ec31026487c69f54a3f583310f8d" \
        ;; \
      *) \
        echo "Unsupported Docker architecture for the pinned PyTorch wheel: $TARGETARCH" >&2; \
        exit 1 \
        ;; \
    esac; \
    python -m pip install pip==26.2.1; \
    pip install "$torch_wheel"; \
    pip install -r requirements.txt; \
    pip check

FROM python:3.12-slim@sha256:2c941e860699f878900b0edc2403613c234d4b32eda3cc9fa7036991a2a63c4a

ARG SOURCE_COMMIT=unknown
LABEL org.opencontainers.image.revision="${SOURCE_COMMIT}"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HOME=/home/app

WORKDIR /app

RUN apt-get update \
    && apt-get upgrade -y \
    && apt-get install -y --no-install-recommends curl postgresql-client \
    && rm -rf /var/lib/apt/lists/* /usr/local/lib/python3.12/site-packages

COPY --from=builder /usr/local /usr/local

# App code (bind-mounted over this in dev via compose, but copied so the
# image is runnable standalone too).
COPY . .
RUN groupadd --gid 1000 app \
    && useradd --uid 1000 --gid app --create-home app \
    && mkdir -p /home/app/.metaharmonizer /home/app/.cache/huggingface \
    && chown -R app:app /app /home/app

USER app:app

EXPOSE 8000

# Default command = API. The worker service overrides this in compose.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
