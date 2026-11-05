# Project plan

**Goal:** a fully automated factory delivery car. Stations measure their own stock, the AI decides what the car should bring first, and the car follows lines to deliver it with its fork.

Capstone requirements this plan covers (G12 2026/2027, "IT and AI Applications"):
- sensing (load cells, IR, ultrasonic);
- wireless transfer to the cloud (MQTT + cloud broker);
- an AI platform (the ML ranker);
- hardware (car + station nodes, no Arduino boards);
- ≥ 6 measurable requirements ([design-requirements.md](design-requirements.md));
- a dataset and rubric ([dataset.md](dataset.md), [ml-rubric.md](ml-rubric.md));
- AI accuracy ≥ 80 % ([reports/evaluation.md](../reports/evaluation.md));
- sensor calibration ([calibration.md](calibration.md));
- showing outputs change with inputs (`scripts/sensitivity.py`).

## Phase 0: Setup ✅
- [x] Git repo and GitHub (private `Capstone-AVG`)
- [x] Architecture ([architecture.md](architecture.md))
- [x] Protocol spec ([protocol.md](protocol.md))

## Phase 1: AI brain ✅ (simulation)
- [x] Factory track as a graph; routes as one command per junction; blocked lines and re-routing
- [x] Usage-rate forecaster from load-cell readings (sliding-window slope, robust to whole-unit readings)
- [x] Automatic need detection: no operator needed
- [x] Safety rules (warehouse stock, room for a box, reachability, battery)
- [x] Teacher optimizer and simple-rule baselines
- [x] ML ranker trained on 30,000 random situations + 18,000 live ones + 12,000 in large factories: 91.6 % top-1 accuracy on unseen data, 83.8 % in live operation
- [x] Training on 400 random factory layouts: 91.1 % on factories it has never seen, so a new track needs no retraining
- [x] Tested on 14 real factory layouts (KIT data set, test only): 85.6 %
- [x] Explanations ("why" + "what if")
- [x] Demo, sensitivity sweep, evaluation report, tests

## Phase 2: Communication and cloud (done on this laptop; Wi-Fi listener and cloud still to do)
- [x] Message bus with the MQTT topics of [protocol.md](protocol.md): in-memory for simulation, `MqttBus` for a real broker
- [x] `agv_brain/controller.py`: feeds stock readings to the forecaster, creates requests, runs the dispatcher, sends tasks, tracks the car, handles obstacles (wait → re-route) and charging
- [x] `SimulatedCar` and `SimulatedStation` that speak the same messages, so the whole system runs without hardware
- [x] Every reading, decision and car event logged to CSV in `logs/` (data for retraining and the logbook)
- [x] Live-operation training (DAgger): live accuracy 76 % → 84 %
- [x] Broker and cloud scripts: `start_broker.py` (with the HiveMQ Cloud bridge), `run_controller.py`, `cloud_check.py`
- [x] Mosquitto installed; the whole simulated factory runs through it (`run_factory_sim.py --mqtt localhost:1883`), checked with `mosquitto_sub` and `tests/test_mqtt.py`
- [x] Fixed: overlapping subscriptions made Mosquitto deliver every message twice; duplicate `done` events are now ignored (QoS 1 is "at least once")
- [x] One program for everything (`scripts/run_app.py`) and a **Setup page**: simulation / real car / real factory, a key per device (the broker refuses anyone else, and each device only gets its own topics), and a track editor with plain-word checks
- [ ] Let the car reach the broker over Wi-Fi: the Mosquitto Windows service only listens on the laptop. In an administrator PowerShell run `Stop-Service mosquitto` and `Set-Service mosquitto -StartupType Manual`, then use `python scripts/run_app.py` (allow Mosquitto through the Windows firewall on private networks)
- [ ] Create a free HiveMQ Cloud account, set it up in `config/mqtt.yaml`, and measure R8 with `cloud_check.py`

## Phase 3: Hardware
- [ ] **Car firmware** on the BW20-12F-Kit (Ameba SDK): Wi-Fi + MQTT, IR line following with PID, junction counting, servo fork, ultrasonic stop, battery reading ([firmware/README.md](../firmware/README.md))
- [ ] **Station nodes:** load cell + HX711 on Ai-Thinker boards, publishing stock every 5 s
- [ ] **Calibration** of every sensor, documented ([calibration.md](calibration.md)); measure R4, R7, R9

## Phase 4: Integration on a real track
- [ ] Build the track mat to match `config/factory_layout.yaml`, or measure the real one and update the file
- [ ] Put the calibrated speed and turn times in `config/materials.yaml`
- [ ] End-to-end runs: low stock → automatic request → car delivers; measure R3 and R5
- [ ] Obstacle tests with re-routing

## Phase 5: Dashboard (car tracking): mostly done early
- [x] Live web dashboard on the laptop ([dashboard.md](dashboard.md)), five simple pages (Now, Stations, AI, History, Try it) in a robot-kit look:
  - the AI's choice in one sentence, why, and whether it is the best possible choice
  - the queue in the AI's order, plus the detailed numbers on demand
  - live car position on the factory map, battery and state, with the route highlighted
  - stock bars per station with "empty in …" forecasts; alerts and an event history
- [x] Manual request button; simulation controls (stock, obstacles, battery)
- [ ] Cloud view of the same data (from the HiveMQ bridge)
- [ ] Charts over time: line-stop time, deliveries per hour, model accuracy

## Phase 6: Visual factory simulation: partly done
- [x] Simulated factory driven by the same `agv_brain` code, shown on the dashboard (`scripts/run_factory_sim.py`)
- [x] Headless comparison of policies (`run_factory_sim.py --compare 40`)
- [ ] Side-by-side view: ML vs first come, first served on the same factory

## Phase 7: Improve and report
- [ ] Retrain on logged real runs; compare simulated vs real accuracy
- [ ] Training with sensor noise and with up to 7–8 requests (to improve the generalization score)
- [ ] Optional: a reinforcement-learning agent as a comparison
- [ ] Final report, poster and presentation; logbooks

## Ideas for later
- **Carry two boxes per trip** when two stations are close together.
- **More than one car**, with the AI assigning tasks between them.
