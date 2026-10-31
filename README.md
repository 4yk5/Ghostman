```
   ____ _               _                          
  / ___| |__   ___  ___| |_ _ __ ___   __ _ _ __   
 | |  _| '_ \ / _ \/ __| __| '_ ` _ \ / _` | '_ \  
 | |_| | | | | (_) \__ \ |_| | | | | | (_| | | | | 
  \____|_| |_|\___/|___/\__|_| |_| |_|\__,_|_| |_| 
                                                   
```

# Ghostman 👻

> **A fast, keyboard-driven terminal API client and webhook inspector.**  
> *No mandatory cloud accounts. No 1GB Electron bloat. 100% local-first.*

[![PyPI](https://img.shields.io/pypi/v/ghostman.svg?color=blue)](https://pypi.org/project/ghostman/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Python: 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![UI: Textual](https://img.shields.io/badge/UI-Textual-bd93f9.svg)](https://github.com/Textualize/textual)

<p align="center">
  <img src="assets/ghostman-main.svg" alt="Ghostman Terminal Studio" width="100%">
</p>

---

## 💡 Why Ghostman?

Modern API clients (Postman, Insomnia) started as simple developer utilities, but evolved into heavy enterprise platforms:

- ❌ **Bloated Memory:** Postman idles at **800MB – 1.5GB of RAM** just sitting in the background.  
  👉 **Ghostman runs on ~30MB of RAM.**
- ❌ **Mandatory Cloud Lock-in:** Forced account sign-ins, team workspaces, and cloud syncing for private test requests.  
  👉 **Ghostman is 100% local-first.** Your requests and collections stay as plain JSON/YAML on your disk (`~/.ghostman/`).
- ❌ **Sluggish Startup:** 5 to 10 seconds of splash screens and loading spinners.  
  👉 **Ghostman cold boots in ~150ms** directly inside your terminal.
- ❌ **External Webhook Tunnels:** Needing ngrok, webhook.site, or third-party accounts just to inspect a local webhook payload.  
  👉 **Ghostman has a built-in webhook listener** on port 9090 (`Ctrl + W`).
- ❌ **Mouse-Heavy Navigation:** Constant clicking between dropdowns, sidebars, and nested dialogs.  
  👉 **Keyboard-driven workflows.** Send with `Ctrl + S`, save with `Ctrl + K`, new request with `Ctrl + N`.

---

## 📸 Interface Tour

### 1. High-Speed Telemetry & Formatted Responses
Instant latency tracking in milliseconds, HTTP status badges, payload size metrics, and syntax-highlighted JSON rendering:

<p align="center">
  <img src="assets/ghostman-response.svg" alt="Response Telemetry" width="100%">
</p>

### 2. Live Webhook Stream
Catch incoming HTTP callbacks from Stripe, GitHub, Shopify, or local microservices in real-time without leaving your terminal:

<p align="center">
  <img src="assets/ghostman-webhook.svg" alt="Live Webhooks" width="100%">
</p>

---

## ⚡ Core Features

- **Full HTTP Method Suite:** Seamlessly compose `GET`, `POST`, `PUT`, `DELETE`, and `PATCH` requests.
- **Performance Telemetry:** DNS + TTFB latency in real-time to monitor endpoint bottlenecks.
- **Embedded Webhook Server:** Spin up a local server on port 9090 with one shortcut to catch incoming hooks.
- **Zero Cloud Dependency:** Save collections as plain files in `.ghostman/` and commit them to Git.
- **Auto-Formatting:** Automatically indents and formats JSON payloads with Rich syntax coloring.
- **Cyberpunk Dark Theme:** Designed for readability in terminal environments with solid borders.

---

## 🚀 Quick Start

### Installation

#### Option 1: Via pip (Recommended)
```bash
pip install ghostman
ghostman
```

#### Option 2: From Source
```bash
# 1. Clone the repository
git clone https://github.com/4yk5/Ghostman.git
cd Ghostman

# 2. Install dependencies
pip install -r requirements.txt

# 3. Launch Ghostman
python main.py
```

> **Windows tip:** You can also run Ghostman by double-clicking `run.bat` in the project root!

---

## ⌨️ Keyboard Shortcuts

| Keybinding | Action |
| :--- | :--- |
| `Ctrl + S` | **Send HTTP Request** (Executes call and switches to Response view) |
| `Ctrl + K` | **Save Request** (Saves current endpoint to collections) |
| `Ctrl + N` | **New Request** (Resets input fields) |
| `Ctrl + W` | **Toggle Webhook Server** (Starts / Stops listener on port 9090) |
| `Tab` / `Shift + Tab` | Navigate between inputs, method selector, and tabs |
| `Enter` | Select endpoint from sidebar / trigger button |
| `Ctrl + Q` | **Quit Ghostman** |

---

## 🛠️ Testing Webhooks Locally

1. Press `Ctrl + W` to start the listener on port `9090`.
2. Send a test webhook from another terminal:
   ```bash
   curl -X POST http://127.0.0.1:9090/webhook \
     -H "Content-Type: application/json" \
     -d '{"event": "payment_succeeded", "amount": 4200}'
   ```
3. Switch to the **Live Webhooks** tab to inspect headers, timestamp, and payload.
4. Click any captured webhook to load its payload directly into the editor.

---

## 🤝 Contributing

Contributions, feedback, and pull requests are very welcome! Feel free to open an issue for bug reports or feature requests.

## 📄 License

Released under the [MIT License](LICENSE).
