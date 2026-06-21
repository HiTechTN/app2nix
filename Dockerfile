# ---- Build stage ----
FROM python:3.11-slim AS builder

WORKDIR /build
COPY pyproject.toml README.md ./
COPY src/ ./src/
COPY templates/ ./templates/
RUN python -m venv /app/.venv \
    && /app/.venv/bin/python -m pip install --no-cache-dir --upgrade pip \
    && /app/.venv/bin/python -m pip install --no-cache-dir .

# ---- Runtime stage ----
FROM python:3.11-slim AS runtime

RUN apt-get update && apt-get install -y --no-install-recommends \
    dpkg \
    rpm2cpio \
    cpio \
    patchelf \
    file \
    tar \
    gzip \
    bzip2 \
    xz-utils \
    unzip \
    p7zip-full \
    squashfs-tools \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
COPY src/ /app/src/
COPY static/ /app/static/
COPY templates/ /app/templates/

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app/src"
ENV APP2NIX_DEBUG=false

RUN useradd -m -u 1000 app2nix
USER app2nix

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s \
  CMD python -c "import httpx; httpx.get('http://localhost:8000/api').raise_for_status()"

CMD ["python", "-m", "app2nix", "serve", "--host", "0.0.0.0", "--port", "8000"]
