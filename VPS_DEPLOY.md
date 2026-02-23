# Running the agent on a VPS

## Important: the agent needs Windows + Viber desktop

The agent **automates the Viber desktop app** (opens chat, captures the window, types messages). It uses:

- Windows-only APIs (`os.startfile("viber://...")`, pywinauto, mss for screenshots)
- Viber installed at `%LOCALAPPDATA%\Viber\Viber.exe` (or `VIBER_EXE`)

So you need a **Windows VPS with a desktop (GUI)** and **Viber desktop installed and logged in**. A typical Linux VPS cannot run this agent.

If your VPS is **Linux**, you have two options:

1. **Keep the agent on your PC** and expose it with ngrok (as you do now). Use the Linux VPS for something else (e.g. reverse proxy, other services).
2. **Rent a Windows VPS** (e.g. Windows Server with Desktop Experience) and follow the steps below.

---

## Deploying on a Windows VPS

### 1. Windows VPS requirements

- Windows Server or Windows 10/11 **with a desktop** (RDP access).
- Outbound internet (for Viber, OpenAI if you use OCR).
- At least 2 GB RAM; 4 GB is safer if Viber + Python run at the same time.

### 2. On the VPS (via RDP)

**Install Python 3.10+**

- Download from [python.org](https://www.python.org/downloads/windows/) and run the installer.
- Check **“Add Python to PATH”**.
- Open a new **Command Prompt** or PowerShell and check: `python --version`.

**Install and log in to Viber**

- Download Viber for Windows from [viber.com](https://www.viber.com/en/download/windows/).
- Install and **log in with your phone number** (QR or code). The agent will use this account to open chats and send messages.
- Leave Viber running (or allow it to start when you open a chat link). You can minimize it.

**Copy the project to the VPS**

- Option A: Clone from GitHub (if the repo is pushed):
  ```cmd
  cd C:\
  git clone https://github.com/denyslavangelov/viber-checker.git
  cd viber-checker
  ```
- Option B: Copy the project folder from your PC (e.g. zip the repo, upload via RDP, then unzip in e.g. `C:\viber-checker`).

**Create virtualenv and install dependencies**

```cmd
cd C:\viber-checker
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

**Set environment variables (optional but recommended)**

- `OPENAI_API_KEY` – required for “Търси” (lookup) OCR. Set it so the agent can read contact names from the screenshot.
- `VIBER_EXE` – only if Viber is not in the default path (`%LOCALAPPDATA%\Viber\Viber.exe`).

You can set them for the current session:

```cmd
set OPENAI_API_KEY=sk-proj-your-key-here
```

Or set them permanently: **Settings → System → About → Advanced system settings → Environment Variables**, add User or System variables.

**Open the firewall for port 5050**

So the web app (or your phone) can call the agent:

- **Windows Defender Firewall → Advanced settings → Inbound Rules → New Rule**.
- Port → TCP → 5050 → Allow. Name e.g. “Viber agent”.

Or in PowerShell (run as Administrator):

```powershell
New-NetFirewallRule -DisplayName "Viber agent" -Direction Inbound -Protocol TCP -LocalPort 5050 -Action Allow
```

**Run the agent**

```cmd
cd C:\viber-checker
venv\Scripts\activate
python agent.py --host 0.0.0.0 --port 5050
```

Leave this window open. The agent is now reachable at `http://<VPS_PUBLIC_IP>:5050`.

### 3. Point the web app to the VPS

In **Vercel** (or wherever the Next.js app is hosted):

- **Environment variable:** `NEXT_PUBLIC_AGENT_URL` = `http://<VPS_PUBLIC_IP>:5050`  
  (replace with your VPS IP; no trailing slash.)
- Redeploy.

If you use a **domain** for the VPS (e.g. `agent.example.com`), you can put that in `NEXT_PUBLIC_AGENT_URL` and add a reverse proxy on the VPS (see below).

### 4. Keep the agent running (optional)

**Option A – Run in a console that stays open**

Use RDP and keep the command window open, or use a tool like **NSSM** or **pm2** (with a wrapper) to run `python agent.py` as a Windows service.

**Option B – Task Scheduler (restart after reboot)**

1. **Task Scheduler → Create Basic Task** (e.g. “Viber agent”).
2. Trigger: **When the computer starts**.
3. Action: **Start a program**.
4. Program: `C:\viber-checker\venv\Scripts\python.exe`
5. Arguments: `agent.py --host 0.0.0.0 --port 5050`
6. Start in: `C:\viber-checker`
7. Finish and ensure the user is logged in (or use “Run whether user is logged on or not” and set the account).

**Option C – NSSM (Windows service)**

1. Download [NSSM](https://nssm.cc/download).
2. Install the service, e.g.:
   ```cmd
   nssm install ViberAgent "C:\viber-checker\venv\Scripts\python.exe" "agent.py --host 0.0.0.0 --port 5050"
   nssm set ViberAgent AppDirectory "C:\viber-checker"
   nssm start ViberAgent
   ```

### 5. HTTPS with a domain (optional)

If you have a domain pointing to the VPS (e.g. `agent.yourdomain.com`):

1. Install **nginx** (or Caddy) on the VPS, or use a tunnel (e.g. Cloudflare Tunnel).
2. Configure a reverse proxy: forward `https://agent.yourdomain.com` → `http://127.0.0.1:5050`.
3. Set `NEXT_PUBLIC_AGENT_URL` to `https://agent.yourdomain.com` and redeploy the web app.

Browsers require HTTPS for production sites; using the VPS IP with `http://` works but may be blocked on some networks.

---

## Summary

| Where agent runs | What you need |
|------------------|----------------|
| **Windows VPS**  | Windows with desktop, Viber installed and logged in, Python, firewall open for 5050. Set `NEXT_PUBLIC_AGENT_URL` to `http://<VPS_IP>:5050` (or your HTTPS URL). |
| **Your PC**      | Agent + ngrok (or port forward). Set `NEXT_PUBLIC_AGENT_URL` to the ngrok URL. No VPS needed for the agent. |
| **Linux VPS**    | This agent **cannot** run there. Use Windows VPS for the agent, or keep the agent on your PC. |
