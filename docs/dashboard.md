# Live dashboard

The dashboard shows what the AI decides, live, in a web browser on the laptop. It is served by the AI program itself, so no internet is needed. Open **http://localhost:8050**.

## Start it

One command starts everything: the MQTT broker (with a key for every device), the AI and the website.
```bash
.venv\Scripts\python scripts\run_app.py
```
The website opens on the **login page**: type the factory's name. Nothing runs until you press **Start**. The website never simulates anything: the car and the stations are devices that log in to the broker with their keys, either the real ones or the separate **Carkaroo Simulator** (see [Practise with the simulator](#practise-with-the-simulator)). To also open the website on a phone or a second screen on the same Wi-Fi, add `--host 0.0.0.0` and browse to `http://<laptop IP>:8050`. Other devices see the pages, but only the laptop can change the setup or see the keys.

The real car needs the broker on port 1883 of the Wi-Fi network. The Mosquitto Windows service already holds that port but only listens on the laptop, so stop it once in an **administrator** PowerShell:
```powershell
Stop-Service mosquitto
```
```powershell
Set-Service mosquitto -StartupType Manual
```
Until then the factory cannot start (the car and the stations have nothing to log in to), and the Setup page says why. (`--mqtt-port 1884` uses another port instead; the firmware must then use it too.) The first time, allow Mosquitto through the Windows firewall on private networks.

For developers, a quick simulation without any broker or login: `run_factory_sim.py` (`--speed 5`, `--policy fifo`, `--compare 40`). It is not the website.

The website refuses commands sent by other web pages and only accepts setup changes from the laptop itself; see [security.md](security.md).

## Does it work with the real car?

Yes. The website and the AI never talk to the car directly: they only read and send the MQTT messages in [protocol.md](protocol.md). Put the car's key in its firmware, and it appears on the map as soon as it sends its first status. The Carkaroo Simulator logs in the same way, with the same keys, so practising with it is a rehearsal for the real car.

## Practise with the simulator

The **Carkaroo Simulator** is a separate program with its own website. It pretends to be the car and the stations,
and each pretend device logs in to the broker with its own ID and key, exactly like the real hardware.

1. Start the Carkaroo website (`run_app.py`), log in, build the factory on Setup, and press **Start**. The Run card
   says *"Waiting for: Car AGV-1, S1, …"*.
2. Start the simulator in a second terminal and open **http://localhost:8060**:
   ```bash
   .venv\Scripts\python scripts\run_simulator.py
   ```
3. On the simulator, choose the factory. Then on the Carkaroo website, press **Setup → Devices → Copy all for the
   simulator**, paste it into the simulator's **Connect** box and press **Connect all**. You can also type each key
   by hand, like you will in the firmware. A wrong key is refused, like on the real car.
4. Each device turns green on the Carkaroo website, the Run card says *"Everything is online"*, and Roo starts to
   drive on the Map.
5. Play on the simulator: drain the car's battery, put an obstacle on a line (click the pretend floor), set a
   station's load cell, or **Disconnect** a device to pull its plug. Watch the Carkaroo website react.

You can mix: connect only the pretend stations and use the real car. The simulator runs in real time, like the real
devices. Its play controls change only the pretend world, through a bus inside the simulator; the real devices' keys
only allow their own topics, and the simulator needs nothing more.

## The pages

The look comes from the **Carkaroo design system** in [`design/`](../design/README.md) (style guide at http://localhost:8050/design/), theme **Night Race**: the monochrome racing look of the project poster and portfolio (asphalt, chrome, fog, checkered finish strip, slanted banners, thick outlines) with one signal color, the yellow of Roo's motors. The floor is a lit white track board with black tape, and the yellow band is Roo's route. The materials keep one color everywhere: A steel blue, B plastic teal, C copper. The letter is always on the chip, so color is never the only clue. The car is called **Roo** on the pages.

**Roo, everywhere:** Roo lives in the bottom-right corner of every page (the login page has a big Roo of its own) and rolls along when you change page. Press the checkered flag next to Roo, or *Extra → Roo's lap*, and Roo picks up a box of one of the factory's materials, drives off the right edge, comes back across the whole screen and says *"Special delivery!"* (with reduced motion it only says it). The logo's eyes and Roo react to the live data (happy, driving, proud after a delivery, worried, sad when a line stops, shocked by an obstacle, sleepy, charging, asleep when offline) and Roo says one short line about it. Tap, hold or drag Roo to play with it. The moon/sun button in the header switches between light and dark; it starts with the computer's setting and remembers your choice. See [design/README.md](../design/README.md#roo-the-main-character).

**Login:** one field, the factory's name. A new name makes a new factory (it starts as a copy of the sample
factory, so it can run at once); a name used before opens that factory again, and the factories made before are
listed as buttons. Each factory keeps its own track in `config/factories/<name>/` (this laptop only,
git ignores it). The header shows the factory's name and **Switch factory**, which goes back to the login page.

**Start** (right after login): two big choices, **Start my factory** (the AI starts and waits for the devices) or
**Set up my factory** (opens Setup), and a pointer to the Carkaroo Simulator for practice.

The tabs are **Setup** (home), **Map**, **Stations** and **History**. The **Extra** menu holds **The AI, explained**
and the design system. While nothing runs, the Map, Stations, History and AI pages say *"The factory is stopped"*
with a **Start** button, and the pill next to the clock says **Stopped** (or **Running**).

**Setup** (home):
- **Stations and materials:** build your factory. Each material (up to 5, letters A to E) has a name, how many units
  go in one box (one trip) and how many the warehouse holds when full; its rack is W-A, W-B… Each station (up to 8,
  S1 to S8) has a name, a priority (high, medium, low) and ticks the materials it uses, each with how much it holds,
  its safety level, its stock at the start and how many it uses per minute. *Save* checks everything (for example
  two stations with the same name, a stock above what the station holds, a material no station uses) and says what
  to fix. A running factory restarts with the change. If the track does not have the new rack or station yet, a red
  note at the top of Setup lists what is missing and Start waits until the track has it. Saved in
  `config/factories/<name>/materials.yaml`, the same format as `config/materials.yaml`. The AI works with any
  stations: the ML ranker only looks at times, stock and priority, never at names.
- **Run:** which track, **Start** and **Stop** (and *Use this track* while it runs). While it runs, it lists the
  devices the AI is still waiting for, until *"Everything is online"*.
- **Devices:** the car and each station, online or offline. *Connect* shows what goes in the firmware: the laptop's
  address and port, the username (the device ID), its **key** (*Show*, *Copy*, *New key*), its topics and a code
  line. **Copy all for the simulator** copies the address, the port and every key, for the Carkaroo Simulator.
- **Track:** *Edit this track* or *Start an empty track* opens the editor. Draw on a 10 cm grid:
  - *Line* draws straight lines point by point;
  - *Junction*, *Rack*, *Station* and *Dock* place points (a point dropped on a line splits it);
  - *Move* drags points, and clicking a line there lets you give the real length of a curved line;
  - *Delete* removes points and lines; *Undo* (Ctrl+Z) goes back.

  The **Check** list explains every problem in plain words (for example *"J3 is a junction with 1 line"*,
  *"Rack W-C for C is missing"*, *"S4 cannot be reached from rack W-C"*). Saving is possible only when it says
  *Ready*; saving under the name of a track that already exists asks first. *Save and use it* makes the factory use
  the new track (at once if it is running). Tracks are saved in `config/tracks/`.

**Map:**
- what Roo is doing right now, in one sentence: *"Carrying B to Packaging"* or *"Fetching C for Quality lab"*, with
  how much the station has left and when it runs out;
- while Roo is busy, a small **Next, when Roo is free** box: the AI's next choice, when it runs out, the trip time,
  and **✓ Best possible choice** when the examiner (the exact optimizer) agrees, or **≈ Almost best** with how much
  more it costs; when Roo is free, the AI's choice is the big line instead;
- if the real car is offline, a red note says nothing moves until it connects, and the battery shows "–";
- the factory floor: the robot car moving on the track. The yellow band is its route; dotted is the part after the
  pickup. A station with a yellow border is waiting for a delivery, red means it has stopped. The dot shows its
  stock: green OK, yellow low, red empty;
- obstacles come from the car's ultrasonic sensor (or the simulator's obstacle): the car stops, and after 10 s
  the AI sends it another way.

If requests are waiting but none can be served (for example the warehouse has less than one box left, or a line is
blocked), the top says *"Can't serve the waiting requests"* and lists the reasons.

**Stations:** one card per station with a stock bar per material (the yellow tick is the safety level), "runs out
in …", and tags for *on the way* and *stopped*. Below:
- **Play** (the capstone asks to show outputs changing with inputs): **Ask for a delivery** (a manual request: see
  where the AI puts it). The stock readings come from the stations' load cells, or from the simulator's
  *A station's load cell* (set Packaging / B to 1 there and watch it jump to the top here). A request the AI cannot take says why (*"Packaging does not use
  that material"*, *"already asked for"*).
- **Warehouse**, in boxes per material. The warehouse has no sensor: the AI counts every box the car takes, so after
  restocking a rack, press its **Refilled** button (it goes back to the full stock set on the Setup page).

**History:** the totals so far (deliveries, how long production lines were stopped, battery), alerts, and what
happened: one card per delivery (task, pickup, delivered), with the other events in between.

**The AI, explained** (under Extra): why there is an AI at all, in three boxes. The examiner (an exact optimizer)
tries every order of the deliveries, so it always finds the best one, but the number of orders explodes (7 requests:
5,040; 10: 3.6 million; 15: 1.3 trillion), so it only runs up to 7 requests. The AI (an ML ranker) learned from the
examiner's answers and decides in about 40 ms however many requests wait. A real factory runs only the AI; the
website lets the examiner check it live. Below: how often the AI made the best possible choice, and the waiting
requests in the AI's order with the AI score (*"3.8 of 4"* means it should go before about 3.8 of the 4 others),
runs out in, and **Details** (trip time, the examiner's "cost if first", ★ = lowest, and the "what if another
request went first" comparisons).

Everything the pages send is checked: a request needs a station that uses that material, a refill a material of the
factory. The simulator checks its play controls the same way (a real line, stock 0 to the station's capacity,
battery 0-100 %, an obstacle for at most 10 minutes). A refusal shows its reason.

## How it works
`agv_brain/dashboard/server.py` subscribes to `factory/ai/state` and `factory/ai/decision` on the message bus. The page (`agv_brain/dashboard/static/`) asks for a snapshot about 3 times a second.
