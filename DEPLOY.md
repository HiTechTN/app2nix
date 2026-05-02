# Deployment Guide

## Deploy Backend to Render (Free)

1. Go to [render.com](https://render.com) and sign up
2. Click **New +** → **Blueprint**
3. Connect your GitHub account and select the `app2nix` repository
4. Render will read `render.yaml` and auto-configure
5. Click **Apply** to deploy

Your API will be available at: `https://app2nix-xxxx.onrender.com`

## Connect Frontend to Backend

1. Open https://hitechtn.github.io/app2nix/
2. In the **API Server** field, enter your Render URL: `https://app2nix-xxxx.onrender.com`
3. Click **Connect**
4. Start converting packages!

## Deploy Backend to Fly.io (Alternative)

```bash
fly launch --dockerfile Dockerfile --name app2nix
fly deploy
fly scale count 1 --region cdg
```

## Local Development

```bash
docker run -p 8000:8000 ghcr.io/hitechtn/app2nix:master
```

Then set the frontend API URL to `http://localhost:8000`.
