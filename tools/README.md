# Run ngrok from this project (no PATH needed)

1. **Download ngrok for Windows**  
   https://ngrok.com/download → choose Windows (64-bit), download the zip.

2. **Extract only `ngrok.exe`** into this folder (`tools/`). You should have:
   ```
   tools/
     ngrok.exe   ← here
     README.md   (this file)
   ```

3. **One-time: add your authtoken** (from https://dashboard.ngrok.com/get-started/your-authtoken):
   ```powershell
   .\tools\ngrok.exe config add-authtoken YOUR_TOKEN
   ```

4. **Start the tunnel** (with the agent running on port 5050):
   ```powershell
   .\tools\ngrok.exe http 5050
   ```
   Use the `https://….ngrok-free.app` URL as `NEXT_PUBLIC_AGENT_URL` in Vercel.
