# MT5 Vision RAG Brain

Local vision RAG for MetaTrader 5. It memorizes playbooks and files as a trading brain, reads live candles plus chart screenshots, scores Fair Value Gaps and Inverse FVGs, then ACCEPT/DENY the EA through Ollama on Windows 11. A phone dashboard controls it from Android on the same Wi-Fi.

This is a decision filter, not a guaranteed money printer. Auto-execution is off by default.

## What it does

- Brain database: SQLite memory vault. PDFs, notes, and images are stored as reusable knowledge, not Q&A pairs.
- Vision: Ollama `llava` reads EA chart screenshots.
- Structure: deterministic FVG / IFVG detector on OHLC candles.
- Decision: rules and LLM must agree to ACCEPT.
- Phone PWA: boxed 3D dashboard, live EA connection light, P&L, session, open/close commands.
- Webhook: `POST /webhook/mt5` plus `/mt5/heartbeat` keep Ollama and the dashboard on the same live account feed.

## Windows 11 setup

1. Install Python 3.11+ and [Ollama](https://ollama.com/download).
2. Open PowerShell:

```powershell
cd C:\path\to\this\repo
powershell -ExecutionPolicy Bypass -File .\windows\Install-OllamaModels.ps1
powershell -ExecutionPolicy Bypass -File .\windows\Start-VisionBrain.ps1
```

3. Optional phone access on the same Wi-Fi (run PowerShell as Administrator):

```powershell
powershell -ExecutionPolicy Bypass -File .\windows\Allow-Firewall.ps1
```

4. On Android Chrome open the printed LAN URL (example `http://192.168.x.x:8080`), then menu -> Add to Home screen.

Copy `.env.example` to `.env` and set `MT5_SHARED_KEY` to a private string.

## MetaTrader 5

1. Copy `mt5/VisionBrainEA.mq5` into `MQL5/Experts`.
2. Compile in MetaEditor.
3. Tools -> Options -> Expert Advisors:
   - Allow WebRequest for listed URL
   - Add `http://127.0.0.1:8080`
4. Attach the EA. Set `SharedKey` to the same value as `MT5_SHARED_KEY`.
5. Leave `AutoExecute=false` until you trust the filter. With it false, the EA only comments ACCEPT/DENY.

The EA posts candles + a chart screenshot on each new bar to `/mt5/analyze`.

## Memorize files into the brain

Drop files into `data/knowledge/` and click Rescan on the dashboard, or upload from the phone. Supported: txt, md, pdf, docx, png, jpg, webp.

## API

- `POST /mt5/analyze` EA trade filter
- `POST /mt5/heartbeat` live P&L, price, wins/losses, and queued commands
- `POST /mt5/commands/ack` EA command result
- `POST /webhook/mt5` alternate live-account webhook
- `POST /api/commands` dashboard trade commands (`ping`, `open_trade`, `close_trade`, `close_all`, `pause`, `resume`)
- `POST /api/analyze` manual JSON candles
- `POST /api/demo/analyze` sample bullish FVG
- `POST /api/memories/upload` memorize a file

## Local test without MT5

```bash
python -m pip install -r requirements.txt
python -m pytest tests -q
python -m uvicorn app.main:app --host 0.0.0.0 --port 8080
```
