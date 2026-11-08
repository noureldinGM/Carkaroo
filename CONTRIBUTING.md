# Working on Carkaroo

A short map for whoever picks the project up next. The [README](README.md) explains what the project is. This page explains where things are and how to change them safely.

## Status (November 2026)

- **Phase 0–2 done:** the AI (ML ranker), MQTT with a key per device, the website (login, Setup with the stations, track and device keys, Map, Stations, History, the AI explained under Extra) and the separate Carkaroo Simulator for practice.
- **The website is a working test version, not the final design.** Its look will still change.
- **Phase 3 next:** car firmware and station nodes ([firmware/README.md](firmware/README.md)), then calibration. See [docs/project-plan.md](docs/project-plan.md) for the checklist.
- The poster and portfolio are designed in Canva by the team. `design/print/` only holds drafts and helper scripts for them.

## Where to change what

| I want to… | Look in |
|---|---|
| change how the AI ranks deliveries | `agv_brain/features.py`, `agv_brain/ranker.py`, then `scripts/train_ranker.py` + `scripts/train_live.py` |
| change the safety rules (stock, battery, blocked lines) | `agv_brain/safety.py` |
| change the factory track, stations or materials | `config/factory_layout.yaml`, `config/materials.yaml`, or draw a track on the Setup page (saved in `config/tracks/`) |
| change MQTT topics or messages | `agv_brain/protocol.py` **and** [docs/protocol.md](docs/protocol.md) (the firmware follows it) |
| change the website | `agv_brain/dashboard/static/` (HTML/CSS/JS), API in `agv_brain/dashboard/server.py` |
| change the Carkaroo Simulator (practice website) | `agv_brain/practice.py`, `agv_brain/practice_server.py`, `agv_brain/practice_static/` |
| change colors, fonts, logo, Roo | `design/` (tokens.css is the source; see [design/README.md](design/README.md)) |
| run or extend the evaluation | `scripts/evaluate.py`, `scripts/evaluate_real_layouts.py` → `reports/` |

## Everyday commands (Windows)

```bash
.venv\Scripts\python scripts\run_app.py
```
```bash
.venv\Scripts\python scripts\run_simulator.py
```
```bash
.venv\Scripts\python -m pytest
```

The MQTT tests need port 1883 free or a running broker. If `run_app.py` is running, its locked broker refuses the tests: stop the app first.

## Git and GitHub

- `main` is always working. Do new work on a branch, open a pull request, and merge when the tests pass. GitHub runs the tests on every pull request (`.github/workflows/tests.yml`).
- Delete a branch once its pull request is merged.
- Never commit secrets: `config/*.local.yaml`, `.env`, keys or passwords. `.gitignore` already blocks the usual ones. See [docs/security.md](docs/security.md).
- Generated files stay out of git: `data/generated/` (rebuild with the scripts) and `logs/` (run logs).
- Big binary files: only add images that the website or the reports really use.
