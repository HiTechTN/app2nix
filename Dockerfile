FROM python:3.11-slim

LABEL maintainer="Azmi <azmi.hitech@gmail.com>"
LABEL description="Convert any Linux package to NixOS expressions"
LABEL version="1.0.0"

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    dpkg \
    patchelf \
    file \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONUNBUFFERED=1
ENV HOST=0.0.0.0
ENV PORT=8000

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/api || exit 1

CMD ["python", "server.py"]

ENTRYPOINT ["python", "server.py"]