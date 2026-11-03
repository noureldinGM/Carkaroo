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

So far it has run with the simulated car, both inside one program and through a real Mosquitto broker (`run_factory_sim.py --mqtt localhost:1883`). The real car is the next step (Phase 3).

## The pages

The look follows the robot kit itself: a green chassis, yellow motors, a jumper-wire ribbon under the header, and the floor drawn as a white track mat with black lines, like the one the IR sensors follow. The materials keep one color everywhere: A steel blue, B plastic green, C copper. The letter is always on the chip, so color is never the only clue.

**Now** (the main page):
- the AI's choice in one sentence: *"Bring B to Packaging"*;
- why, in plain words: how much is left, when it runs out, how long the trip takes;
- **✓ Best possible choice** when the exact optimizer agrees, or **≈ Almost best** with how much more it costs;
- what the car is doing, and the next three requests;
- deliveries, how long production lines were stopped, and the battery;
- the factory floor: the robot car moving on the track. The yellow band is its route; dotted is the part after the pickup. A station with a yellow border is waiting for a delivery, red means it has stopped. The dot shows its stock: green OK, yellow low, red empty.

If requests are waiting but none can be served (for example the warehouse has less than one box left, or a line is blocked), the top says *"Can't serve the waiting requests"* and lists the reasons.

**Stations:** one card per station with a stock bar per material (the black tick is the safety level), "runs out in …", and tags for *on the way* and *stopped*. Below: the warehouse, in boxes per material. The warehouse has no sensor: the AI counts every box the car takes, so after restocking a rack, press its **Refilled** button (it goes back to the full stock in `config/materials.yaml`). This works the same for the simulation and the real factory.

**AI:** how often the AI made the best possible choice, and the ranking of the waiting requests:
- the AI score, from the ML ranker: how many of the other requests it should go before. *"3.8 of 4"* means it beats about 3.8 of the 4 others. The highest goes first, and the AI decides again after every delivery;
- runs out in, trip time, and the optimizer's "cost if first" (★ = lowest);
- the "what if another request went first" comparisons.

**History:** alerts and the latest events.

**Try it:** change the inputs and watch the AI react (the capstone asks to show outputs changing with inputs):
- **Ask for a delivery:** add a manual request and see where the AI puts it.
- **Change a stock reading:** for example, set Packaging / B to 1 and watch it jump to the top.
- **Low battery:** drain it to 15 %; the AI sends the car to charge first.
- **Obstacle:** click a line on the map on this page. The car stops there, and after 10 s the AI sends it another way.

With the real car, only "Ask for a delivery" is shown; the rest is simulation only.

## How it works
`agv_brain/dashboard/server.py` subscribes to `factory/ai/state` and `factory/ai/decision` on the message bus. The page (`agv_brain/dashboard/static/`) asks for a snapshot about 3 times a second.
