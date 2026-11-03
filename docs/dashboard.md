# Live dashboard

The dashboard shows what the AI decides, live, in a web browser on the laptop. It is served by the AI program itself, so no internet is needed. Open **http://localhost:8050**.

## Start it

With the simulated factory (no hardware needed):
```bash
.venv\Scripts\python scripts\run_factory_sim.py
```
Slower or faster: `--speed 5` or `--speed 30` (simulated seconds per real second). To watch a simple rule instead of the AI: `--policy fifo`.

With the real car and stations (after `python scripts/start_broker.py`):
```bash
.venv\Scripts\python scripts\run_controller.py
```
Add `--sim-stations` while the load cells are not built yet. To open it on a phone or a second screen on the same Wi-Fi, add `--host 0.0.0.0` and browse to `http://<laptop IP>:8050`.

## Does it work with the real car?

Yes, by design. The dashboard and the AI never talk to the car directly: they only read and send the MQTT messages in [protocol.md](protocol.md). The simulated car sends exactly the same messages the real car will. Once the BW20-12F firmware (Phase 3) sends its `status` and `node` / `done` events over Wi-Fi, the dashboard shows the real car, with no changes.

So far it has only been run with the simulated car. The real-network path (Mosquitto + `MqttBus`) is written but not tested yet.

## What is on the page

**At the top, the AI's choice in one sentence:** *"Bring B to S3 · Packaging"*, then:
- a badge: **✓ Best possible choice** when the exact optimizer agrees, or **≈ Almost best** with how much more it costs;
- **Why**, in plain words: how much is left, when it runs out, how long the trip takes;
- what the car is doing right now;
- the **queue**: every waiting request in the AI's order, with "runs out in …" (red when it is urgent).

**Show the AI's numbers** (click it) opens the details for the judges:
- the AI score of each request (from the ML ranker);
- slack (empty-in minus trip; red when negative);
- the optimizer's "cost if first", with ★ on the best;
- the "what if another request went first" comparisons.

**Factory floor:** the track, racks and stations, with the car moving on it. The car's color shows its state: blue driving, orange lifting or lowering, red blocked, green charging. A box on it means it is carrying material. Blue = going to the rack, orange = carrying to the station.

**Stations:** a stock bar per material (the black tick is the safety stock), "empty in", and tags for *on the way* and *stopped*.

**What happened:** the latest events and alerts.

**Header:** deliveries, total line-stop time, how often the AI made the best choice, battery.

## Showing "outputs change with inputs" (capstone requirement)

In the simulation, the **Try it** panel and the map let you change the inputs and watch the AI react:
- **Change a stock reading:** for example, set S3 / B to 1 and watch it jump to the top of the queue.
- **Click a line on the map** to put an obstacle on it. The car stops there, and after 10 s the AI sends it another way.
- **Drain the battery to 15 %:** the AI sends the car to charge first.
- **Ask for a delivery:** add a manual request and see where the AI puts it in the queue.

## How it works
`agv_brain/dashboard/server.py` subscribes to `factory/ai/state` and `factory/ai/decision` on the message bus. The page (`agv_brain/dashboard/static/`) asks for a snapshot about 3 times a second.
