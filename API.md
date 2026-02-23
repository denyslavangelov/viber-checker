# API – CMD one-line curl commands

Set your agent URL once (same CMD window):
```cmd
set AGENT_URL=http://188.137.227.236:5050
```

Then run:

**Health**
```cmd
curl %AGENT_URL%/health
```

**Lookup**
```cmd
curl -X POST %AGENT_URL%/check-number-base64 -H "Content-Type: application/json" -d "{\"number\": \"0877315132\", \"only_panel\": true}"
```

**Send message**
```cmd
curl -X POST %AGENT_URL%/send-message -H "Content-Type: application/json" -d "{\"number\": \"0877315132\", \"message\": \"Hello\"}"
```

**Lookup with API key**
```cmd
curl -X POST %AGENT_URL%/check-number-base64 -H "Content-Type: application/json" -H "X-API-Key: YOUR_KEY" -d "{\"number\": \"0877315132\", \"only_panel\": true}"
```

**Send message with API key**
```cmd
curl -X POST %AGENT_URL%/send-message -H "Content-Type: application/json" -H "X-API-Key: YOUR_KEY" -d "{\"number\": \"0877315132\", \"message\": \"Hello\"}"
```

---

## Direct URL (no variable)

Replace `http://188.137.227.236:5050` with your agent URL and copy-paste:

```cmd
curl http://188.137.227.236:5050/health
```

```cmd
curl -X POST http://188.137.227.236:5050/check-number-base64 -H "Content-Type: application/json" -d "{\"number\": \"0877315132\", \"only_panel\": true}"
```

```cmd
curl -X POST http://188.137.227.236:5050/send-message -H "Content-Type: application/json" -d "{\"number\": \"0877315132\", \"message\": \"Hello\"}"
```
