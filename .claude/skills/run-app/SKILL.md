---
description: Launch the risk-assessment-tool Flask app locally
---

# Run the App

## Launch

```bash
cd "c:/Users/fahad/AI-Risk-Auditor-Gen-1"
python app.py &
```

Wait ~3 seconds, then verify it's up:

```bash
curl -s -o /dev/null -w "%{http_code}" http://localhost:5000/
```

Expected response: `200`

## Open in browser

```bash
start http://localhost:5000
```

## Notes

- App runs on **http://localhost:5000**
- Requires `.env` in the project root with `ANTHROPIC_API_KEY`
- Flask server is stateless — all session state lives in the browser
- To stop: kill the background Python process (`taskkill /f /im python.exe` or Ctrl+C in the terminal where it was started)
