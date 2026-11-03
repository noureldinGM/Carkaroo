# Communication protocol (MQTT)

All devices talk through **MQTT** over Wi-Fi, with JSON messages. This is the contract between the AI (`agv_brain/controller.py`), the car firmware, the station nodes and the dashboard. The simulated devices in `agv_brain/sim_devices.py` follow it exactly, so the simulation tests it.

- A **local broker** (Mosquitto) runs on the laptop, which is the edge computer that runs the AI. Start it with `python scripts/start_broker.py`. The factory keeps working even if the internet goes down.
- The local broker is **bridged to a cloud broker** (HiveMQ Cloud free tier, TLS port 8883), as the capstone's "wireless data transfer to the cloud" requires. See [`config/mqtt.yaml`](../config/mqtt.yaml).

```
station nodes ──┐                          ┌──> cloud broker (HiveMQ Cloud)
                ├──> Mosquitto (laptop) <──┤      (bridge: factory/# out,
car (BW20-12F) ─┘        │   ▲             │       factory/ai/request,
                         ▼   │             │       factory/warehouse/refill in)
          AI controller + dashboard (agv_brain)
```

## Topics

| Topic | From → to | QoS | Retained | Payload |
|---|---|---|---|---|
| `factory/station/<station>/stock` | station node → AI | 0 | no | stock reading, every 5 s and after a delivery |
| `factory/car/<car>/status` | car → AI | 0 | yes | car status, every 1 s |
| `factory/car/<car>/event` | car → AI | 1 | no | node reached, action done, obstacle, clear, error |
| `factory/car/<car>/cmd` | AI → car | 1 | no | task, reroute, resume, stop, charge |
| `factory/ai/state` | AI → dashboard | 0 | yes | everything the AI believes about the factory, every 0.5 s |
| `factory/ai/decision` | AI → dashboard | 1 | yes | the latest decision: ranking, factors, reasons, optimizer check |
| `factory/ai/alerts` | AI → dashboard | 1 | no | warehouse low, obstacle, battery, unreachable station |
| `factory/ai/request` | dashboard / cloud → AI | 1 | no | manual request `{"material": "B", "station": "S3"}` |
| `factory/warehouse/refill` | dashboard / cloud → AI | 1 | no | a person restocked a rack: `{"material": "A"}` (back to full) or `{"material": "A", "units": 300}`. The warehouse has no sensor; the AI counts every box the car takes |
| `factory/sim/control` | dashboard → simulation | 0 | no | simulation only: obstacles, stock changes, battery |

## Messages

### Station stock (load cell)
```json
{"material": "B", "stock": 2, "ts": 1234.5}
```
The station node converts weight to whole units using its calibration (see [calibration.md](calibration.md)). It can add `"weight_g"` for the logs. The AI feeds every reading to the `ConsumptionForecaster`.

### Car status
```json
{"state": "DRIVING", "battery": 82, "task_id": 7, "leg": 0, "node_index": 2, "fork": "UP"}
```
`state` is one of `IDLE`, `DRIVING`, `LIFTING`, `LOWERING`, `BLOCKED`, `CHARGING`, `ERROR`. The car does **not** know node names (it only counts junctions), so the AI works out the position from the planned path and `node` events. The AI only gives the car a new task when it reports `IDLE`, and treats it as offline after 5 s without a status.

### Task (AI → car)
One task is one delivery: drive to the rack, lift, drive to the station, lower.
```json
{"type": "task", "task_id": 7, "material": "B",
 "legs": [
   {"to": "W-B", "commands": ["STRAIGHT", "RIGHT", "LEFT", "STOP"], "action": "LIFT"},
   {"to": "S3",  "commands": ["UTURN", "STRAIGHT", "STRAIGHT", "STOP"], "action": "LOWER"}
 ]}
```
How the car runs `commands` (junction counting):
1. It runs `commands[0]` right away: how to leave the place where it stands.
2. It follows the line with the IR sensors. Every time it detects a node (all sensors on black = a junction, or the stop marker at a line end), it sends a `node` event and runs the next command.
3. At `STOP` it runs the leg's `action`. `LIFT` raises the fork with the servo; `LOWER` puts the box down and backs out. Then it sends `done`.

`LEFT` and `RIGHT` are relative to the direction the car is driving. `UTURN` turns it around on the spot.

### Events (car → AI)
```json
{"type": "node", "task_id": 7, "leg": 0, "node_index": 2}
{"type": "done", "task_id": 7, "leg": 0, "node": "W-B", "action": "LIFT", "material": "B"}
{"type": "done", "task_id": 7, "leg": 1, "node": "S3", "action": "LOWER", "material": "B"}
{"type": "obstacle", "task_id": 7, "leg": 1, "distance_cm": 12, "after_node_index": 1}
{"type": "clear", "task_id": 7}
{"type": "error", "task_id": 7, "reason": "no line to the E after RIGHT at node 2"}
```
- `node_index` counts the nodes passed on the current leg (1 = the first node after the start). If the count doesn't fit the plan, the AI stops the car and raises an alert.
- In `done`, `node` and `material` simply repeat what the car was told (the leg's `to` and the task's `material`). The station node uses them to recognize its own delivery.

### Other commands (AI → car)
```json
{"type": "reroute", "task_id": 7, "leg": 1, "commands": ["UTURN", "RIGHT", "RIGHT", "RIGHT", "LEFT", "STOP"]}
{"type": "resume", "task_id": 7}
{"type": "stop"}
{"type": "charge", "task_id": 8, "to": "HOME", "commands": ["UTURN", "LEFT", "STOP"]}
```
After a `charge` route the car sends `done` with `"action": "CHARGE"` and reports `CHARGING` until the battery is full, then `IDLE`.

## Obstacle handling
1. The ultrasonic sensor sees something closer than the stop distance (15 cm by default). The car stops and sends `obstacle`.
2. If the car sends `clear` (the obstacle is gone), the AI sends `resume` and the car continues.
3. After `obstacle_wait_s` (10 s, set in `config/materials.yaml`), the AI blocks that line and computes a new route with `FactoryMap.reroute_from_edge(last_node, next_node, goal)`. It sends `reroute`. The car does a U-turn, goes back to the last junction (a `node` event with `node_index` 1) and continues from there.
4. If there is no way around (for example, the only line into a rack), the AI raises "please clear the line" and keeps waiting.
5. A blocked line is tried again after `block_expiry_s` (300 s).
