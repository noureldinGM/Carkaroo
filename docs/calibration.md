# Sensor calibration

The capstone requires you to calibrate the sensors and document it. Do each procedure below, record the raw numbers in the tables (and in your logbook), and keep the final constants in the firmware or config.

## 1. Station load cells (stock sensing)
Each material bin sits on a load cell with an HX711 amplifier, read by an Ai-Thinker board.

**Procedure**
1. With the empty bin on the scale, read the raw HX711 value 20 times and average it. This is the **tare** offset.
2. Put known weights on it: 0, 100, 200, 500 and 1000 g, ideally lab calibration weights. Average 20 readings for each.
3. Fit a straight line, `weight_g = (raw - tare) / scale`, by least squares. Record the slope and R². R² should be ≥ 0.999.
4. Weigh 10 parts of the material one by one, and take the mean as the **unit weight**. Then `units = round(weight_g / unit_weight)`.
5. Check: put 1, 5, 10 and 20 parts on the scale and compare the counted units with the real count (requirement R4: error ≤ ±1 unit).

| Known weight (g) | Raw average | Computed (g) | Error (g) |
|---|---|---|---|
| 0 | | | |
| 100 | | | |
| 200 | | | |
| 500 | | | |
| 1000 | | | |

Slope: ____ R²: ____ Unit weight of A / B / C: ____ / ____ / ____ g

## 2. IR line sensors (line following and junction detection)
1. Place each sensor over the white floor and record its reading (min), then over the black line (max). Do this 10 times each.
2. Threshold per sensor = (min + max) / 2. Save the five thresholds in the firmware.
3. Junction test: drive slowly over each junction type (cross and T) 10 times. A junction counts when all sensors (or the outer two) see black. Record how many were detected; the goal is 10 out of 10.
4. Repeat under the exhibition lighting, because sunlight changes IR readings.

| Sensor | White (avg) | Black (avg) | Threshold |
|---|---|---|---|
| 1 (left) | | | |
| 2 | | | |
| 3 (middle) | | | |
| 4 | | | |
| 5 (right) | | | |

## 3. Ultrasonic sensor (HC-SR04, obstacle detection)
The BW20-12F runs at 3.3 V. Power the HC-SR04 from 5 V and put a voltage divider (for example 1 kΩ / 2 kΩ) on the ECHO pin.

1. Put a flat object at 5, 10, 15, 20, 30 and 50 cm, measured with a ruler. Take 10 readings each.
2. Fit `real = a × measured + b` and record a and b. Report the mean error and standard deviation.
3. Set the stop distance (default 15 cm). Test 20 times at full speed that the car stops with ≥ 5 cm to spare (requirement R7).

| Real distance (cm) | Measured avg | Std dev | Error |
|---|---|---|---|
| 5 | | | |
| 10 | | | |
| 15 | | | |
| 20 | | | |
| 30 | | | |
| 50 | | | |

## 4. Servo fork
1. Find the servo angle where the fork is fully down (slides under the box) and fully up (box clear of the floor). Record both.
2. Time a lift and a lower with the real box 10 times each. Put the mean into `pickup_s` and `drop_s` in `config/materials.yaml`, adding the time to drive into and out of the slot.
3. Test 20 lifts (requirement R9: ≥ 95 % success).

## 5. Car speed and turn times (for the AI's trip-time estimates)
1. Time the car over a 100 cm straight line 5 times → `speed_cm_s`.
2. Time 5 left turns, 5 right turns and 5 U-turns at a junction, then subtract the straight-line time → `turn_s`, `uturn_s`.
3. Put the numbers in `config/materials.yaml`. The ML model was trained on car speeds from 0.6× to 1.5× of 15 cm/s (9–22.5 cm/s), so it stays valid inside that range. Outside it, run `python scripts/generate_dataset.py` and `python scripts/train_ranker.py` again; it takes under a minute.
4. Measure the real line lengths. If a line is not straight, put its real length in `config/factory_layout.yaml` as a third value.

## 6. Battery
Measure the battery voltage with a voltage divider on an ADC pin. Record voltage vs. percentage at full charge, half, and the cut-off, and fit a curve. Drive a known distance and record the percentage used → `battery_pct_per_m`.
