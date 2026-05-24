# ---- Build stage ----
FROM python:3.12-slim AS builder

WORKDIR /build
COPY pyproject.toml uv.lock ./
RUN pip install uv && uv sync --no-dev --frozen

# ---- Runtime stage ----
FROM python:3.12-slim AS runtime

RUN apt-get update && apt-get install -y --no-install-recommends \
    dpkg \
    rpm2cpio \
    cpio \
    patchelf \
    file \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=builder /build/.venv /app/.venv
COPY src/ /app/src/
COPY static/ /app/static/
COPY templates/ /app/templates/
COPY lib/ /app/lib/

ENV PATH="/app/.venv/bin:$PATH"
ENV APP2NIX_SECRET_KEY=""
ENV APP2NIX_DEBUG=false

RUN useradd -m -u 1000 app2nix
USER app2nix

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s \
  CMD python -c "import httpx; httpx.get('http://localhost:8000/api').raise_for_status()"

CMD ["python", "-m", "app2nix", "serve", "--host", "0.0.0.0", "--port", "8000"]
