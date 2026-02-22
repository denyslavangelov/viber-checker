# Deploying to Vercel

This repo contains:

- **`web/`** – Next.js app (deploy this to Vercel)
- **`agent.py`** – Python/Flask agent (runs locally on your PC with Viber, not deployed)

## Vercel setup

1. Import the repo in Vercel as usual.
2. **Project Settings → General**
   - Set **Root Directory** to **`web`** (click Edit, choose the `web` folder, Save).
   - Leave **Framework Preset** as **Next.js**.
3. **Project Settings → Build & Development Settings**
   - Find **Output Directory**.
   - If it shows `public` (or anything), **clear it completely** so the field is empty, then Save.
   - Next.js uses its own output (`.next`); Vercel must not be set to `public` or the build will fail with "No Output Directory named 'public' found".
4. Deploy (or redeploy).

If Root Directory is not set to `web`, Vercel will treat the repo as Flask and the build will fail. If Output Directory is set to `public`, the build will fail because this project has no `public` output—clear it.

## Using from your phone

The agent runs on your PC (where Viber is). To use the app from your phone:

1. **Run the agent so it accepts LAN connections**  
   On the PC: `python agent.py` (default host is `0.0.0.0`) or `python agent.py --host 0.0.0.0 --port 5050`. Do **not** use `--host 127.0.0.1` or the phone cannot reach it.

2. **Same Wi‑Fi**  
   Phone and PC must be on the same network.

3. **Open the app using the PC’s IP**  
   - On the PC run the Next.js app: `cd web && npm run dev`.
   - On the phone open **http://&lt;PC_IP&gt;:3000** (e.g. `http://192.168.1.100:3000`). The app will use the same host with port 5050 as the agent URL automatically.

4. **If you use the Vercel URL on the phone**  
   In the app, set **Agent URL (опционално)** to **http://&lt;PC_IP&gt;:5050** (your PC’s local IP and the agent port). Then the Viber check runs on your PC.

If the phone still can’t reach the agent, check the PC firewall allows inbound connections on port 5050.
