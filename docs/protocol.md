# Communication protocol (MQTT)

All devices talk through **MQTT** over Wi-Fi, with JSON messages.

- A **local broker** (Mosquitto) runs on the laptop, which is the edge computer that runs the AI. The factory keeps working even if the internet goes down.
- The local broker is **bridged to a cloud broker** (HiveMQ Cloud free tier by default, over TLS port 8883). The cloud dashboard and data logging read from there, as the capstone's "wireless data transfer to the cloud" requires.

```
station nodes ──┐                          ┌──> cloud broker ──> cloud dashboard / logs
                ├──> Mosquitto (laptop) <──┤
car (BW20-12F) ─┘        │   ▲             └── (bridge, topics factory/#)
                         ▼   │
                    AI brain (agv_brain)
```

## Topics

| Topic | Direction | QoS | Retained | Payload |
|---|---|---|---|---|
| `factory/station/<station>/stock` | station node → | 0 | yes | stock reading |
| `factory/car/<car>/status` | car → | 0 | yes | car status (every 1 s and on change) |
| `factory/car/<car>/event` | car → | 1 | no | node reached, step done, obstacle |
| `factory/car/<car>/cmd` | → car | 1 | no | task, stop, resume, reroute |
| `factory/ai/decision` | AI → | 1 | yes | current plan and reasons (for the dashboard) |
| `factory/ai/alerts` | AI → | 1 | no | warehouse low, battery, unreachable station |

## Messages

### Station stock (load cell)
```json
{"material": "B", "stock": 2, "weight_g": 412.5, "ts": 1730620800.0}
```
The station node converts weight to units using its calibration (see [calibration.md](calibration.md)). The AI feeds every reading to the `ConsumptionForecaster`.

### Car status
```json
{"state": "DRIVING", "node": "J2", "heading": "E", "battery": 82, "task_id": 7, "fork": "UP"}
```
`state` is one of `IDLE`, `DRIVING`, `LIFTING`, `LOWERING`, `BLOCKED`, `CHARGING`, `ERROR`.

### Task (AI → car)
One task is one delivery: drive to the rack, lift, drive to the station, lower.
```json
{"type": "task", "task_id": 7,
 "legs": [
   {"to": "W-B", "commands": ["STRAIGHT", "RIGHT", "LEFT", "STOP"], "action": "LIFT"},
   {"to": "S3",  "commands": ["UTURN", "STRAIGHT", "STRAIGHT", "STOP"], "action": "LOWER"}
 ]}
```
How the car runs `commands` (junction counting):
1. It runs `commands[0]` right away: how to leave the place where it stands.
2. It follows the line with the IR sensors. Every time it detects a node (all sensors on black = a junction, or the stop marker at a line end), it runs the next command.
3. At `STOP` it runs the leg's `action`. `LIFT` raises the fork with the servo; `LOWER` puts the box down and backs out.

`LEFT` and `RIGHT` are relative to the direction the car is driving. `UTURN` turns it around on the spot.

### Events (car → AI)
```json
{"type": "node", "node_index": 2, "task_id": 7}
{"type": "done", "task_id": 7, "leg": 0}
{"type": "obstacle", "task_id": 7, "distance_cm": 12, "after_node_index": 1}
{"type": "clear", "task_id": 7}
```
`node_index` counts the nodes passed on the current leg. The AI knows the planned path, so it knows where the car is. If the count doesn't match the plan, the AI stops the car and raises an alert.

### Other commands (AI → car)
```json
{"type": "stop"}
{"type": "resume"}
{"type": "reroute", "task_id": 7, "leg": 1, "commands": ["UTURN", "RIGHT", "RIGHT", "RIGHT", "LEFT", "STOP"]}
{"type": "charge", "commands": ["UTURN", "LEFT", "STOP"]}
```

## Obstacle handling
1. The ultrasonic sensor sees something closer than the stop distance (15 cm by default). The car stops and sends `obstacle`.
2. The AI waits `obstacle_wait_s` (10 s, set in `config/materials.yaml`). If the car sends `clear`, the AI sends `resume`.
3. Otherwise the AI blocks that line and computes a new route with `FactoryMap.reroute_from_edge(last_node, next_node, goal)`. The car does a U-turn, goes back to the last junction and continues. The plan is re-ranked, because the delay may change which delivery should go first.
