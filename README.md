# Capstone AVG: AI dispatcher for a factory line-follower car

A small automated guided vehicle (AGV) carries material boxes around a factory floor. Every station weighs its own bins, so the system always knows how much stock is left. When stations need material, an **AI running on the laptop** decides **which delivery goes first** and sends the car a route it can follow, junction by junction.

> Grade 12 Capstone 2026/2027, *Information Technology and Artificial Intelligence Applications*, industrial pathway (fully automated production lines).

## How it works

1. **Sensing:** load cells under each station's bins report the stock. The car has IR line sensors, an ultrasonic obstacle sensor and a servo fork.
2. **Forecasting:** the AI learns each station's usage rate from the readings.
3. **Automatic requests:** when a station will reach its safety stock before a delivery could arrive (plus a look-ahead), the AI creates the request itself. No operator is needed.
4. **Deciding what goes first:** a machine-learning ranker looks at:
   - time until each station runs out;
   - trip time to the rack and the station;
   - station criticality;
   - waiting time;
   - what would happen to the *other* requests.

   It picks the delivery that keeps production running. Hard safety rules come first: warehouse stock, room for a box, battery, and blocked lines.
5. **Routing:** the path planner turns the route into one command per junction (`STRAIGHT`, `LEFT`, `RIGHT`, `UTURN`, `STOP`), followed by `LIFT` or `LOWER` for the fork.
6. **Explaining:** every decision comes with reasons and a "what if the other one went first" comparison.

See [docs/architecture.md](docs/architecture.md) for the diagrams.

## Results (simulation, situations the model never saw)

| | ML ranker | Weighted rules (hand-made) | First come, first served | Exact optimizer |
|---|---|---|---|---|
| Picks the best delivery: our track (1000 situations) | **91.5 %** | 61.3 % | 26.2 % | 100 % |
| Picks the best delivery: 200 new factory layouts | **91.3 %** | 57.7 % | 27.3 % | 100 % |
| Extra cost vs the optimal plan (our track) | **1.1 %** | 16.8 % | 149.7 % | 0 % |
| Decision time | ~20 ms | < 0.1 ms | < 0.1 ms | grows with n! |

The ML ranker cuts production stop time by **42 %** compared with first come, first served. Its accuracy clears the capstone's **80 %** target, on our track and on factories it has never seen. Training mixes our track with 400 random factory layouts, so a new or changed track needs no retraining. Full report: [reports/evaluation.md](reports/evaluation.md).

![Accuracy by number of requests](reports/accuracy_by_requests.png)

## Quick start (Windows)

```bash
python -m venv .venv
```
```bash
.venv\Scripts\python -m pip install -r requirements.txt
```
```bash
.venv\Scripts\python scripts\demo.py
```

The trained model is in `models/ranker.joblib`, so the demo works right away. To rebuild everything from scratch:

```bash
.venv\Scripts\python scripts\generate_dataset.py
```
```bash
.venv\Scripts\python scripts\train_ranker.py
```
```bash
.venv\Scripts\python scripts\evaluate.py
```
```bash
.venv\Scripts\python -m pytest
```

## Demo

`python scripts/demo.py` reads the (simulated) station sensors and decides by itself:

```
=== Needs detected automatically ===
- A -> S1: S1 (Assembly line 1) has 10 A left, uses 3.0/min: safety level in 80 s, empty in 3.3 min; a delivery takes ~51 s.
- B -> S3: S3 (Packaging) has 2 B left, uses 2.0/min: safety level in 0 s, empty in 60 s; a delivery takes ~39 s.

=== AI decision (policy: ml) ===
1. B -> S3 (Packaging)   done in 39 s   score 1.00
2. A -> S1 (Assembly line 1)   done in 1.8 min   score 0.00

Why:
 * Go first: B -> S3 (Packaging). It has 2 units left and runs out in 60 s; the trip takes 39 s (criticality 2).
 * If A -> S1 (Assembly line 1) went first instead: S3 would stop 42 s longer (cost +92).
 * The exact optimizer agrees with this choice.

=== Commands sent to the car for task 1 (one per junction) ===
to rack W-B    path HOME > J1 > J2 > W-B
            commands STRAIGHT, RIGHT, LEFT, STOP, then LIFT (servo fork up)
to S3         path W-B > J2 > J5 > S3
            commands UTURN, STRAIGHT, STRAIGHT, STOP, then LOWER (servo fork down)
```

Other things to try:
- `--request A:S1 --request B:S3`: manual requests, "bring A and B at the same time"
- `--stock S3:B=8`: change a sensor reading and watch the decision change
- `--block J2-J5`: an obstacle blocks a line, so the car re-routes
- `--battery 15`: the car charges first
- `--policy fifo`: compare with a simple rule
- `python scripts/sensitivity.py` sweeps a stock level and shows where the decision flips (`reports/sensitivity.png`)

## Project layout

```
config/            factory track (nodes, lines) and materials/stations/car settings
agv_brain/         the AI: map, forecaster, need detector, safety, simulator,
                   random layouts, optimizer, features, ML ranker, explainer, dispatcher
scripts/           demo, dataset generation, training, evaluation, sensitivity
models/            trained ranker
data/sample/       sample of the training dataset (the full one is regenerated)
reports/           evaluation report and charts
docs/              architecture, project plan, protocol, requirements,
                   dataset, ML rubric, calibration
firmware/          car firmware notes (BW20-12F-Kit), to be written in Phase 3
tests/             pytest suite
```

## Hardware

| Part | Role |
|---|---|
| Ai-Thinker BW20-12F-Kit (dual-band Wi-Fi + BLE 5.0) | car controller |
| IR sensor array | line following and junction detection |
| HC-SR04 ultrasonic | obstacle detection |
| Servo | fork lift |
| Load cell + HX711 per bin, on Ai-Thinker boards | station stock sensing |
| Laptop | edge computer: MQTT broker + AI |
| HiveMQ Cloud (planned) | cloud data and dashboard |

## Documents
- [Project plan and roadmap](docs/project-plan.md)
- [Architecture](docs/architecture.md)
- [Communication protocol (MQTT)](docs/protocol.md)
- [Measurable design requirements](docs/design-requirements.md)
- [Dataset](docs/dataset.md) and [ML rubric](docs/ml-rubric.md)
- [Sensor calibration](docs/calibration.md)
- [Firmware notes](firmware/README.md)
