# Security

The website and the MQTT broker run on the laptop. This page lists what protects them, so whoever works on the project next keeps it that way.

## The website (`agv_brain/dashboard/server.py`)

| Threat | Protection |
|---|---|
| Another web page open in the browser sends commands to `localhost:8050` (CSRF) | Every POST must be `Content-Type: application/json` (a plain form or `no-cors` fetch cannot send that), and if the browser sends an `Origin` it must be this same site. |
| A web page whose domain points at 127.0.0.1 reads the device keys (DNS rebinding) | The `Host` header must be an IP address, `localhost` or the laptop's own name. Anything else gets `421`. |
| A phone or another laptop on the Wi-Fi changes the setup or reads the keys | Opening or making a factory, Start and Stop, and setup changes (`/api/login`, `/api/logout`, `/api/run`, `/api/stop`, `/api/mode`, `/api/device/…/key`, `/api/track/save`) and the keys are only for the laptop itself (`127.0.0.1`). By default the website only listens on the laptop (`--host 127.0.0.1`). |
| Script injection (XSS) | Every value shown on the page goes through `esc()` in `app.js`. A Content-Security-Policy allows only the site's own scripts, plus the one small inline theme script, by its hash. |
| The page shown inside another site's frame (clickjacking) | `frame-ancestors 'none'` and `X-Frame-Options: DENY`. |
| Wrong or huge values (a negative refill, a stock above the capacity, an obstacle on a line that does not exist) | `/api/request`, `/api/refill` and `/api/sim` check every value against the factory and refuse it with a reason (`check_request`, `check_refill`, `check_sim` in `server.py`). |
| Huge or slow requests | Bodies are capped at 1 MB, and a client that stops sending is dropped after 15 s. |
| Reading files that are not part of the website | Only web file types (`.html .js .css .svg .png .jpg .json .md`) are served, and only from `static/` and `design/`. Paths cannot leave those folders. |

Still open from another device on the Wi-Fi, on purpose: manual requests, the **Refilled** button and the simulation controls (handy on a phone at the rack). The login page has no password: it only names the factory, and only the laptop can open one. Only use `--host 0.0.0.0` on a network you trust.

## The broker and the devices (`agv_brain/broker.py`)

- No anonymous logins. Every device (car `AGV-1`, each station, the AI `brain`) has its own key, and the ACL lets each one use only its own topics.
- Keys are random (`secrets.token_urlsafe`), stored in `config/devices.local.yaml`. **Git ignores that file. Never commit it.** The broker only gets hashed copies.
- A new key (Setup → Devices) works at once, and the old one stops working.
- HiveMQ Cloud login comes from the environment variables `HIVEMQ_USERNAME` / `HIVEMQ_PASSWORD`, never from a file in git.

## Rules for new code

1. No passwords, keys or tokens in the repository. Secrets go in `config/*.local.yaml` or environment variables.
2. A new POST endpoint that changes the setup must check `self.local` (put it in `_setup_post`), and any value it passes on must be checked like `check_sim`.
3. Never put data from MQTT or the user into `innerHTML` without `esc()`.
4. New file types for the website must be added to `TYPES` in `server.py` on purpose.
5. `tests/test_phase2.py` checks the protections above. Keep it passing.
