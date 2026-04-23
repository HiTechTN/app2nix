# API Reference

REST API documentation for app2nix server.

## Base URL

```
http://localhost:8000
```

## Endpoints

### GET /

Returns the web UI.

**Response:** HTML page

### GET /api

API information endpoint.

**Response:**
```json
{
  "message": "app2nix API",
  "version": "1.0.0"
}
```

### POST /analyze

Analyze a package file.

**Request:**
- Content-Type: `multipart/form-data`
- Body: `file` - Package file

**Response:**
```json
{
  "name": "myapp",
  "version": "1.0.0",
  "architecture": "amd64",
  "libraries": ["libgtk-3", "libdrm"],
  "nix_dependencies": ["gtk3", "libdrm"]
}
```

**Example:**
```bash
curl -X POST -F "file=@package.deb" http://localhost:8000/analyze
```

### POST /generate

Generate Nix expression from package.

**Request:**
- Content-Type: `multipart/form-data`
- Body: `file` - Package file

**Response:**
```json
{
  "name": "myapp",
  "version": "1.0.0",
  "content": "{ pkgs ? import <nixpkgs> {} }:\n\npkgs.stdenv.mkDerivation {...}"
}
```

**Example:**
```bash
curl -X POST -F "file=@package.deb" http://localhost:8000/generate > default.nix
```

### POST /download

Download and analyze package from URL.

**Request:**
- Content-Type: `application/json`
- Body: `{"url": "https://example.com/package.deb"}`

**Response:**
```json
{
  "name": "myapp",
  "version": "1.0.0",
  "nix_dependencies": ["gtk3", "libdrm"]
}
```

**Example:**
```bash
curl -X POST -H "Content-Type: application/json" \
  -d '{"url":"https://download.example.com/app.deb"}' \
  http://localhost:8000/download
```

## Error Responses

| Status | Description |
|--------|-------------|
| 400 | Invalid file format |
| 422 | Missing file |
| 500 | Internal server error |

**Error Example:**
```json
{
  "detail": "File must be .deb"
}
```

## Python Client

```python
import requests

class App2nixClient:
    def __init__(self, base_url="http://localhost:8000"):
        self.base_url = base_url
    
    def analyze(self, file_path):
        with open(file_path, "rb") as f:
            files = {"file": f}
            response = requests.post(f"{self.base_url}/analyze", files=files)
        return response.json()
    
    def generate(self, file_path):
        with open(file_path, "rb") as f:
            files = {"file": f}
            response = requests.post(f"{self.base_url}/generate", files=files)
        return response.json()
    
    def download(self, url):
        response = requests.post(
            f"{self.base_url}/download",
            json={"url": url}
        )
        return response.json()

# Usage
client = App2nixClient()
info = client.analyze("package.deb")
nix = client.generate("package.deb")
```

## JavaScript Client

```javascript
const API_URL = 'http://localhost:8000';

async function analyze(file) {
    const formData = new FormData();
    formData.append('file', file);
    
    const response = await fetch(`${API_URL}/analyze`, {
        method: 'POST',
        body: formData
    });
    return response.json();
}

async function generate(file) {
    const formData = new FormData();
    formData.append('file', file);
    
    const response = await fetch(`${API_URL}/generate`, {
        method: 'POST',
        body: formData
    });
    return response.json();
}

// Usage
const fileInput = document.getElementById('file');
fileInput.addEventListener('change', async () => {
    const info = await analyze(fileInput.files[0]);
    console.log(info);
});
```

## Rate Limits

No rate limits by default. For production, consider adding rate limiting:

```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter

@app.post("/analyze")
@limiter.limit("10/minute")
async def analyze_package(file: UploadFile = File(...)):
    ...
```