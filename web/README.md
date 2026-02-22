# Viber Screenshot – Web UI

Next.js + TypeScript + Tailwind frontend for the Viber agent. Enter a phone number and get the screenshot(s) back.

## Setup

```bash
cd web
npm install
```

## Run

```bash
npm run dev
```

Open [http://localhost:3000](http://localhost:3000). Enter the agent URL (e.g. `http://localhost:5050` if the agent runs on the same machine) and a phone number, choose screenshot type, then click **Get screenshot**.

Optional: copy `.env.local.example` to `.env.local` and set `NEXT_PUBLIC_AGENT_URL` to pre-fill the agent URL.

## Build

```bash
npm run build
npm start
```
