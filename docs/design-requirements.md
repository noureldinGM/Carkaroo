# Measurable design requirements

The capstone asks for at least four measurable requirements, including response time and system accuracy, plus two chosen for the application. These are the proposed targets. Fill in the "Measured" column as each one is tested, and keep the raw data in your logbook.

| # | Requirement | Target | How it is measured | Measured | Status |
|---|---|---|---|---|---|
| R1 | **Response time** of the AI decision | ≤ 100 ms per decision | `scripts/evaluate.py` (decision time, 1000 situations) | about 10–40 ms mean depending on how busy the laptop is: 20.5 ms mean, 28 ms p95 measured on its own; 38 ms mean, 81 ms p95 in the latest `evaluate.py` run on a busy laptop | Met (software) |
| R2 | **System accuracy**: AI picks the best delivery | ≥ 80 % top-1 accuracy vs the exact optimizer | `scripts/evaluate.py`: 1000 unseen situations, 1000 on 200 unseen factory layouts, and 40 one-hour live factory runs; `scripts/evaluate_real_layouts.py`: 1400 situations in 14 real factories (KIT data set) | 91.6 % / 91.1 % / 83.8 % live / 85.6 % real factories | Met (software) |
| R3 | **End-to-end response**: low stock → car receives its task | ≤ 2 s | timestamps of the stock reading and of the car's `task` message | – | Phase 4 |
| R4 | **Stock measurement accuracy** (load cell) | ≤ ±1 unit (≤ ±2 % of full scale) after calibration | known weights, see [calibration.md](calibration.md) | – | Phase 3 |
| R5 | **Navigation accuracy** (junction counting) | ≥ 95 % of runs stop at the right node | 20 runs on each of 5 test routes | – | Phase 4 |
| R6 | **Production uptime** (application): less line-stop time than first come, first served | ≥ 30 % less | `scripts/evaluate.py` (simulation), then real runs | 42 % less (simulation) | Met (simulation) |
| R7 | **Obstacle safety** (application): stops before an object | stops in 100 % of 20 trials, ≥ 5 cm before contact | object placed on the line at 3 speeds | – | Phase 3 |
| R8 | **Cloud data**: readings reach the cloud dashboard | ≤ 5 s delay, ≥ 99 % of messages delivered | `scripts/cloud_check.py` (numbered, time-stamped messages through the bridge) | – | Tool ready; needs Mosquitto + a HiveMQ Cloud account |
| R9 | **Fork lift**: lifts and lowers a box | ≥ 95 % success in 20 tries, ≤ 2 s per lift | servo test with the real box | – | Phase 3 |

R1, R2 and R6 come from the latest `reports/evaluation.md` (and `reports/real_layouts.md` for the real factories). Re-run `python scripts/evaluate.py` after retraining and update them here.

## Showing outputs change with inputs
The capstone asks you to show how the system's output changes as its inputs change. The easiest way is the **live dashboard** (`python scripts/run_factory_sim.py`, see [dashboard.md](dashboard.md)). Change a stock reading, block a line or drain the battery, and the AI's choice changes in front of you. Two more ways:
- `python scripts/sensitivity.py` sweeps the stock of B at S3 and shows where the decision flips from "B first" to "A first", along with the line-stop time for ML vs first come, first served (`reports/sensitivity.png`).
- `python scripts/demo.py --stock S3:B=8` (or any other reading, battery level or blocked line) shows the live decision and its reasons change.
