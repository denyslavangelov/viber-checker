# Viber Screenshot Agent

Run an agent on the **PC where Viber is installed** (e.g. another laptop). It opens Viber, searches for a given phone number, takes a full-screen screenshot, and returns it over HTTP. You can trigger it from your current PC with a simple HTTP request or the included client script.

## How it works

1. **On the laptop with Viber:** Run the agent (`agent.py`). It starts a small HTTP server.
2. **From your PC:** Send a POST request with a phone number (e.g. `{"number": "+1234567890"}`) to the agent.
3. The agent launches Viber (if needed), focuses it, sends **Ctrl+F** (search), types the number, waits, then captures the **entire screen** and returns the PNG.

So you “send a request” to that PC, and get back a screenshot of the whole screen after it has opened Viber and looked up the number.

## Setup on the PC that has Viber

1. Install Python 3.8+.
2. In this project folder, create a virtualenv and install dependencies:

   ```bash
   python -m venv venv
   venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. (Optional) If Viber is not in the default path, set:

   ```bash
   set VIBER_EXE=C:\Path\To\Viber.exe
   ```

4. Run the agent (listens on all interfaces so your other PC can reach it):

   ```bash
   python agent.py --host 0.0.0.0 --port 5050
   ```

5. Allow the agent’s port (e.g. **5050**) through the laptop’s firewall, or ensure both PCs are on the same LAN and the firewall allows incoming connections on that port.

## Testing on your own PC (same machine)

You can run both the agent and the client on the same computer:

1. **Terminal 1** – start the agent (bind to localhost only for testing):
   ```bash
   python agent.py --host 127.0.0.1 --port 5050
   ```

2. **Terminal 2** – call the client with `localhost`:
   ```bash
   python client.py http://127.0.0.1:5050 +1234567890 screenshot.png
   ```
   Replace `+1234567890` with a real number you want to look up in Viber.

3. Check `screenshot.png` in the current folder.

Make sure Viber is installed in the default location (or set `VIBER_EXE`). The agent will focus the Viber window and take a full-screen screenshot, so keep the PC unlocked.

## Sending a request from your PC (other machine)

**Option A – Client script (same repo)**

On your PC (where you develop), install `requests` and run:

```bash
python client.py http://<LAPTOP_IP>:5050 +1234567890 screenshot.png
```

Example: `python client.py http://192.168.1.100:5050 +380501234567 screenshot.png`

**Option B – curl**

```bash
curl -X POST http://<LAPTOP_IP>:5050/check-number -H "Content-Type: application/json" -d "{\"number\": \"+1234567890\"}" --output screenshot.png
```

**Option C – JSON response (base64 screenshot)**

If you prefer the screenshot as base64 inside JSON:

```bash
curl -X POST http://<LAPTOP_IP>:5050/check-number-base64 -H "Content-Type: application/json" -d "{\"number\": \"+1234567890\"}"
```

You can decode the `screenshot_base64` field and save as PNG.

## Endpoints

| Endpoint              | Method | Body              | Response                    |
|-----------------------|--------|-------------------|-----------------------------|
| `/health`             | GET    | —                 | JSON: status, viber_path    |
| `/check-number`       | POST   | `{"number": "…"}` | PNG image (full screen)     |
| `/check-number-base64`| POST   | `{"number": "…"}` | JSON: `screenshot_base64`, `number` |

## OCR (contact name)

The agent uses **GPT Vision** to read the contact name and text from the screenshot. Set **`OPENAI_API_KEY`** so the agent can call the API:

```bash
set OPENAI_API_KEY=sk-...
```

- Default model: `gpt-4o-mini`. Override with `OPENAI_OCR_MODEL=gpt-4o` if you want.
- The `/check-number-base64` response includes `contact_name` and `panel_text` when OCR runs.
- `GET /health` returns `"ocr": true` and `"ocr_backend": "gpt"` when the key is set.

## Important notes

- **Viber has no public desktop API.** The agent uses keyboard automation (Ctrl+F, type number, Enter). If Viber’s search shortcut or UI changes, you may need to adjust `agent.py` (e.g. different hotkey or more delay).
- **Full-screen screenshot:** The response is a screenshot of the **entire primary screen**, not only the Viber window. The agent does not crop to Viber.
- **Security:** The agent has no authentication. Use only on a trusted network (e.g. home LAN) or add your own auth (e.g. API key in header, reverse proxy with auth).
- **Focus:** For automation to work, the laptop should be unlocked and preferably have Viber in the foreground after the script focuses it (Alt+Tab). Running headless or with a locked session is not supported.

## Tuning delays

If the search or screenshot is too fast/slow, edit in `agent.py`:

- `LAUNCH_WAIT` – seconds to wait after starting Viber.
- `AFTER_SEARCH_WAIT` – seconds after typing the number before Enter and screenshot.
- `BEFORE_SCREENSHOT_WAIT` – seconds after Enter before capturing the screen.

Then restart the agent.
