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

**Screenshots only when the session is “visible” (RDP)**

- When you **disconnect** from RDP or **minimize** the RDP window so you’re not viewing the VPS desktop, Windows often **stops drawing** the remote session. The agent can still “see” the Viber window (pywinauto finds it), but the screen capture (mss) may get a black or empty frame because nothing is being rendered.
- **Workaround:** Keep an RDP connection **open** to the VPS while you need lookups/screenshots (you can minimize the RDP window on your side—what matters is that the session is still active and, ideally, the desktop is being composed). Avoid **logging off** or **disconnecting** RDP if you want screenshots to work.
- If you must disconnect, you may need a **virtual display** or “session keep-alive” so Windows keeps rendering the desktop; that’s more advanced and not covered here.

**Send message requires the session in the foreground (RDP)**

- **"Send message"** uses Windows keyboard injection (SendInput). When RDP is **disconnected** or you are **not viewing** the VPS desktop, the session does not accept keyboard input, so the agent may report "SendInput() inserted only 0 out of N events" and the message is not typed.
- **Workaround:** For "Send message" to work, you must **have RDP connected and be viewing the VPS** (the Viber window in the foreground or the session at least visible). There is no programmatic workaround for sending keys to a disconnected RDP session.

**Screenshots with nobody viewing: virtual display**

If you will **never** have RDP open while the agent runs, Windows does not draw the desktop and mss captures a black frame. Install a **virtual display driver** so Windows always has a fake monitor and keeps rendering. Steps for **IddSampleDriver**:

1. **Download**  
   Go to [https://github.com/roshkins/IddSampleDriver/releases](https://github.com/roshkins/IddSampleDriver/releases), download the latest release (e.g. **0.1.1** or **0.0.1**) as a **ZIP**, and extract it to a folder on the VPS (e.g. `C:\IddSampleDriver`).  
   The **.inf** file is named **IddSampleDriver.inf**. It may be in the **root** of the extracted folder or inside an **IddSampleDriver** subfolder (e.g. `C:\IddSampleDriver\IddSampleDriver.inf` or `C:\IddSampleDriver\IddSampleDriver\IddSampleDriver.inf`). Use **Have Disk → Browse** to that file.

2. **Install the certificate (run as Administrator)**  
   Open **Command Prompt** or **PowerShell as Administrator**, `cd` into the extracted folder, then run the included **.bat** file.  
   If the .bat fails, run these instead (replace with the real certificate filename if different):
   ```cmd
   certutil -addstore -f root IddSampleDriver.cer
   certutil -addstore -f TrustedPublisher IddSampleDriver.cer
   ```

3. **Add the driver via Device Manager**  
   - Press **Win + X** → **Device Manager**.
   - **Important:** Click the **computer name** at the very top of the tree (e.g. "DESKTOP-XXX" or your PC name). The "Add legacy hardware" option only appears when this root is selected.
   - Menu **Action** → **Add legacy hardware**.
   - **Next** → **Install the hardware that I manually select (Advanced)** → **Next**.
   - Select **Display adapters** → **Next**.
   - Click **Have Disk...** → **Browse...** and select the **.inf** file in the extracted folder (e.g. `IddSampleDriver.inf`) → **OK** → **Next**.
   - Complete the wizard (Next → Finish). Windows may install one or more virtual display adapters.

   **If "Add legacy hardware" is not in the Action menu at all** (e.g. on some Windows 11 builds), try installing from an **elevated Command Prompt** (Run as administrator) from the extracted folder:
   ```cmd
   pnputil /add-driver IddSampleDriver.inf /install
   ```
   Then reboot. If that fails, check the driver’s GitHub issues for your Windows version.

4. **Reboot** the VPS.

5. **Display settings**  
   After reboot, open **Settings → System → Display**. You should see extra virtual monitor(s). You can set resolution and set “Extend” or “Duplicate” so the session keeps drawing to them. Once the virtual display is active, the agent’s mss capture will get real pixels even when no one is connected via RDP.

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
