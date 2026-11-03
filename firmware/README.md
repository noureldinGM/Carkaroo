# Car firmware (Phase 3, to be written together)

**Board:** Ai-Thinker BW20-12F-Kit. It is Realtek-based, with dual-band Wi-Fi (2.4 / 5 GHz), BLE 5.0, a dual-core MCU, 4 MB flash and 17 usable IO pins. It is not an Arduino board, which the capstone rules require.

**SDK:** Ameba-RTOS C SDK (Linux / Windows), linked from [docs.ai-thinker.com/en/bw20](https://docs.ai-thinker.com/en/bw20/). The board ships with Combo-AT firmware; we will replace it with our own program. Arduino IDE support for this exact board isn't confirmed, so plan on the Ameba SDK.

## What the car must do
1. Join Wi-Fi and connect to the MQTT broker on the laptop. Subscribe to `factory/car/AGV-1/cmd`; publish `status` and `event` (see [docs/protocol.md](../docs/protocol.md)).
2. **Line following** with the IR sensor array, using a PID controller on the line position to set the two motor speeds.
3. **Junction counting:** when all sensors see black (a junction) or the stop marker appears, run the next command (`STRAIGHT`, `LEFT`, `RIGHT`, `UTURN`, `STOP`) and publish a `node` event.
4. **Fork:** on `LIFT`/`LOWER`, drive the servo to the calibrated angles, then publish `done`.
5. **Obstacle:** check the ultrasonic distance about 20 times a second. Below the stop distance, brake, publish `obstacle`, and wait for `resume` or `reroute`.
6. **Battery:** read the voltage divider and publish the percentage in `status`.
7. **Failsafe:** with no command and no broker for 3 s while driving, stop the motors.

## Pin budget (17 IO available)
| Function | Pins | Type |
|---|---|---|
| IR line sensors (5) | 5 | digital in (or ADC for analog sensors) |
| Motor driver TB6612FNG: PWMA, PWMB | 2 | PWM out |
| Motor driver: AIN1, AIN2, BIN1, BIN2 | 4 | digital out (STBY tied high) |
| Ultrasonic HC-SR04: TRIG, ECHO (via divider) | 2 | digital out / in |
| Servo fork | 1 | PWM out (50 Hz) |
| Battery voltage divider | 1 | ADC |
| **Total** | **15** | 2 left (for example a status LED or button) |

Map the exact pin numbers from the BW20-12F datasheet when wiring, since not every pin supports PWM or ADC, and record the final pinout here.

## Suggested parts
- TB6612FNG motor driver: more efficient than an L298N and works with 3.3 V logic
- 2 × N20 or TT gear motors with wheels, plus a caster
- 5-channel IR sensor array (TCRT5000 type)
- HC-SR04 ultrasonic sensor, with a voltage divider on ECHO
- SG90 / MG90S servo for the fork
- 2S Li-ion pack (7.4 V) and a buck converter to 5 V (servo, sensors); the board's 3.3 V comes from its own regulator
