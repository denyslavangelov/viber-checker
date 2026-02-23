# Security

## API key (recommended when the agent is reachable from the internet)

If the agent runs on a VPS or is exposed via a tunnel, anyone who knows the URL can call it. To restrict access:

1. **On the agent (VPS or PC):** In `.env` set:
   ```env
   AGENT_API_KEY=your-long-random-secret
   ```
   Use a long random string (e.g. 32+ characters). Generate one with: `python -c "import secrets; print(secrets.token_urlsafe(32))"`

2. **On Vercel (when using the proxy):** In Project → Settings → Environment Variables add:
   - **AGENT_API_KEY** = the **same** value as above (server-side only; do not use `NEXT_PUBLIC_`).

The proxy will send `X-API-Key: <value>` when calling the agent. The agent rejects any POST to `/check-number`, `/check-number-base64`, or `/send-message` that does not send a matching key (via `X-API-Key` header or `Authorization: Bearer <key>`). **GET /health** and **OPTIONS** do not require the key (so health checks and CORS preflight still work).

If **AGENT_API_KEY** is not set on the agent, no key is required (backward compatible).

## Other good practices

- **Secrets in .env only** – Do not commit real keys. Use `.env.example` as a template; `.env` is in `.gitignore`.
- **Agent behind firewall** – Prefer running the agent where only your app (or VPN) can reach it. Use the Vercel proxy so the browser talks to Vercel (HTTPS) and only Vercel talks to the agent.
- **Rotate keys** – If a key was ever committed or leaked, rotate it (new value in agent and Vercel).
