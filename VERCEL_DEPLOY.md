# Deploying to Vercel

This repo contains:

- **`web/`** – Next.js app (deploy this to Vercel)
- **`agent.py`** – Python/Flask agent (runs locally on your PC with Viber, not deployed)

## Vercel setup

1. Import the repo in Vercel as usual.
2. In **Project Settings → General**, set **Root Directory** to **`web`** (click Edit and choose the `web` folder).
3. Leave Framework Preset as **Next.js** (or let Vercel detect it from `web/`).
4. Deploy.

If Root Directory is not set to `web`, Vercel will treat the repo as Flask (because of `requirements.txt` at root) and the build will fail. The Root Directory must be `web` so Vercel uses `web/package.json` and builds the Next.js app.
