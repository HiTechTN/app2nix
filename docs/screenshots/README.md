# Screenshots

This directory contains screenshots of the app2nix web interface.

## Contents

| File | Description |
|------|-------------|
| `01-homepage.png` | Main landing page |
| `02-features.png` | Features section |
| `03-formats.png` | Supported formats |
| `04-converter.png` | Package converter |
| `05-api-docs.png` | API documentation |
| `06-api-json.png` | API JSON response |

## Regenerating Screenshots

To regenerate screenshots:

```bash
cd docs/screenshots
python take_screenshots.py
```

Requirements:
- Firefox browser
- geckodriver
- selenium
- Pillow