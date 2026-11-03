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
- [x] Usage-rate forecaster (EWMA) from load-cell readings
- [x] Automatic need detection: no operator needed
- [x] Safety rules (warehouse stock, room for a box, reachability, battery)
- [x] Teacher optimizer and simple-rule baselines
- [x] ML ranker trained on 30,000 situations: 91.5 % top-1 accuracy on unseen data
- [x] Training on 400 random factory layouts: 91.3 % on factories it has never seen, so a new track needs no retraining
- [x] Explanations ("why" + "what if")
- [x] Demo, sensitivity sweep, evaluation report, tests

## Phase 2: Communication and cloud
- [ ] Install Mosquitto on the laptop; bridge `factory/#` to HiveMQ Cloud (free tier)
- [ ] `agv_brain/link.py`: an MQTT client that feeds stock readings to the forecaster, runs the dispatcher, sends tasks and handles car events (obstacle → wait → re-route)
- [ ] `SimulatedCar` and `SimulatedStation` that speak the same MQTT messages, so the whole system runs without hardware
- [ ] Log every reading, decision and car event to CSV (data for retraining and the logbook)
- [ ] Measure R8 (cloud delay and delivery rate)

## Phase 3: Hardware
- [ ] **Car firmware** on the BW20-12F-Kit (Ameba SDK): Wi-Fi + MQTT, IR line following with PID, junction counting, servo fork, ultrasonic stop, battery reading ([firmware/README.md](../firmware/README.md))
- [ ] **Station nodes:** load cell + HX711 on Ai-Thinker boards, publishing stock every 5 s
- [ ] **Calibration** of every sensor, documented ([calibration.md](calibration.md)); measure R4, R7, R9

## Phase 4: Integration on a real track
- [ ] Build the track mat to match `config/factory_layout.yaml`, or measure the real one and update the file
- [ ] Put the calibrated speed and turn times in `config/materials.yaml`
- [ ] End-to-end runs: low stock → automatic request → car delivers; measure R3 and R5
- [ ] Obstacle tests with re-routing

## Phase 5: Dashboard (car tracking)
- [ ] Web dashboard on the laptop, mirrored in the cloud:
  - live car position on the factory map, heading, battery, state (driving / lifting / blocked / charging)
  - the current task and route, highlighted on the map
  - stock bars per station with "empty in …" forecasts
  - the AI decision, its reasons and the "what if" comparison
  - alerts (warehouse low, obstacle, battery) and an event history
  - charts: line-stop time, deliveries per hour, model accuracy
- [ ] Optional manual request button, for when an operator wants to force a delivery

## Phase 6: Visual factory simulation
- [ ] Animated factory: stations consuming material, the car driving its routes, obstacles appearing. It is driven by the same `agv_brain` code, so it is useful for the exhibition when the real track is not available.
- [ ] Side-by-side mode: ML vs first come, first served on the same factory

## Phase 7: Improve and report
- [ ] Retrain on logged real runs; compare simulated vs real accuracy
- [ ] Training with sensor noise and with up to 7–8 requests (to improve the generalization score)
- [ ] Optional: a reinforcement-learning agent as a comparison
- [ ] Final report, poster and presentation; logbooks

## Ideas for later
- **Carry two boxes per trip** when two stations are close together.
- **More than one car**, with the AI assigning tasks between them.
