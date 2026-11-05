# Live dashboard

The dashboard shows what the AI decides, live, in a web browser on the laptop. It is served by the AI program itself, so no internet is needed. Open **http://localhost:8050**.

## Start it

One command starts everything: the MQTT broker (with a key for every device), the AI and the website.
```bash
.venv\Scripts\python scripts\run_app.py
```
Then choose **Simulation**, **Real car** or **Real factory** on the **Setup** page. To also open the website on a phone or a second screen on the same Wi-Fi, add `--host 0.0.0.0` and browse to `http://<laptop IP>:8050`. Other devices see the pages, but only the laptop can change the setup or see the keys.

The real car needs the broker on port 1883 of the Wi-Fi network. The Mosquitto Windows service already holds that port but only listens on the laptop, so stop it once in an **administrator** PowerShell:
```powershell
Stop-Service mosquitto
```
```powershell
Set-Service mosquitto -StartupType Manual
```
Until then the app runs the simulation only, and the Setup page says why. (`--mqtt-port 1884` uses another port instead; the firmware must then use it too.) The first time, allow Mosquitto through the Windows firewall on private networks.

Simulation only, without any broker: `run_factory_sim.py` (`--speed 5`, `--policy fifo`, `--compare 40`).

The website refuses commands sent by other web pages and only accepts setup changes from the laptop itself; see [security.md](security.md).

## Does it work with the real car?

Yes. The website and the AI never talk to the car directly: they only read and send the MQTT messages in [protocol.md](protocol.md), and the simulated car sends exactly the same messages. Choose **Real car** on the Setup page, put the car's key in its firmware, and it appears on the map as soon as it sends its first status. This was checked with a program that logged in with the car's key: it showed online and received its first task.

## The pages

The look comes from the **Carkaroo design system** in [`design/`](../design/README.md) (style guide at http://localhost:8050/design/), theme **Night Race**: the monochrome racing look of the project poster and portfolio (asphalt, chrome, fog, checkered finish strip, slanted banners, thick outlines) with one signal color, the yellow of Roo's motors. The floor is a lit white track board with black tape, and the yellow band is Roo's route. The materials keep one color everywhere: A steel blue, B plastic teal, C copper. The letter is always on the chip, so color is never the only clue. The car is called **Roo** on the pages.

**Roo, everywhere:** the logo's eyes and Roo at the top of the Now page react to the live data (happy, driving, proud after a delivery, worried, sad when a line stops, shocked by an obstacle, sleepy, charging, asleep when offline) and Roo says one short line about it. Tap, hold or drag Roo to play with it. The moon/sun button in the header switches between light and dark; it starts with the computer's setting and remembers your choice. See [design/README.md](../design/README.md#roo-the-main-character).

The website has five tabs: **Now**, **Stations**, **AI**, **History** and **Setup**. The open tab is marked by one slanted black plate that slides from tab to tab. On a phone, all five tabs fit in one row.

**Now** (the main page):
- what Roo is doing right now, in one sentence: *"Carrying B to Packaging"* or *"Fetching C for Quality lab"*, with how much the station has left and when it runs out;
- while Roo is busy, a small **Next, when Roo is free** box: the AI's next choice (*"Bring A to Assembly line 2"*), when it runs out, the trip time, and **✓ Best possible choice** when the exact optimizer agrees, or **≈ Almost best** with how much more it costs;
- when Roo is free, the AI's choice is the big line instead, with why in plain words;
- the battery, and a link to the full order on the AI page;
- the factory floor: the robot car moving on the track. The yellow band is its route; dotted is the part after the pickup. A station with a yellow border is waiting for a delivery, red means it has stopped. The dot shows its stock: green OK, yellow low, red empty.

If requests are waiting but none can be served (for example the warehouse has less than one box left, or a line is blocked), the top says *"Can't serve the waiting requests"* and lists the reasons.

**Stations:** one card per station with a stock bar per material (the yellow tick is the safety level), "runs out in …", and tags for *on the way* and *stopped*. Below: the warehouse, in boxes per material. The warehouse has no sensor: the AI counts every box the car takes, so after restocking a rack, press its **Refilled** button (it goes back to the full stock in `config/materials.yaml`). This works the same for the simulation and the real factory.

**AI:** how often the AI made the best possible choice, and the waiting requests in the order the AI would serve them:
- the AI score, from the ML ranker: how many of the other requests it should go before. *"3.8 of 4"* means it beats about 3.8 of the 4 others. The highest goes first, and the AI decides again after every delivery;
- runs out in, for each request;
- **Details** (click to open): trip time, the optimizer's "cost if first" (★ = lowest), and the "what if another request went first" comparisons.

**History:** the totals so far (deliveries, how long production lines were stopped, battery), alerts, and what happened: one card per delivery (task, pickup, delivered), with the other events in between.

**Setup** (choose what the website runs):
- **Factory mode:** *Simulation* (with a speed slider from real time to x20), *Real car* (your car, simulated stations until the load cells are built) or *Real factory*, and which track. *Apply* restarts the AI in a few seconds; the website stays open. The pill next to the clock shows the mode on every page (yellow = simulation, green = real).
- **Devices:** the car and each station, with online / offline, real or simulated. *Connect* shows what goes in the firmware: the laptop's address and port, the username (the device ID), its **key** (*Show*, *Copy*, *New key*), its topics and a code line.
- **Track:** *Edit this track* or *Start an empty track* opens the editor. Draw on a 10 cm grid:
  - *Line* draws straight lines point by point;
  - *Junction*, *Rack*, *Station* and *Dock* place points (a point dropped on a line splits it);
  - *Move* drags points, and clicking a line there lets you give the real length of a curved line;
  - *Delete* removes points and lines; *Undo* (Ctrl+Z) goes back.

  The **Check** list explains every problem in plain words (for example *"J3 is a junction with 1 line"*, *"Rack W-C for C is missing"*, *"S4 cannot be reached from rack W-C"*). Saving is possible only when it says *Ready*. *Save and use it* switches the factory to the new track at once. Tracks are saved in `config/tracks/`.

**Try it** (the yellow button under the map on the Now page opens it): change the inputs and watch the AI's choice and the map react right above (the capstone asks to show outputs changing with inputs):
- **Ask for a delivery:** add a manual request and see where the AI puts it.
- **Change a stock reading:** for example, set Packaging / B to 1 and watch it jump to the top.
- **Low battery:** drain it to 15 %; the AI sends the car to charge first.
- **Obstacle:** while Try it is open, click a line on the map. The car stops there, and after 10 s the AI sends it another way.

The controls follow the mode: stock readings only while the stations are simulated, battery and obstacles only while the car is.

## How it works
`agv_brain/dashboard/server.py` subscribes to `factory/ai/state` and `factory/ai/decision` on the message bus. The page (`agv_brain/dashboard/static/`) asks for a snapshot about 3 times a second.
