# Hardware Pathway (planned build)

This repository is the simulation + control stack. This file sketches the
physical build it is designed to drive. **Nothing here is medical advice;
a physical build for a diagnosed SIJ condition belongs under clinician
supervision and appropriate review.**

## Budget (from the simulated profile: 95 g, < 120 g hard limit)

| Part | Example | Mass |
|---|---|---|
| MCU | ESP32-C3 SuperMini / RP2040 Pico | 2–5 g |
| IMU | MPU-6050 or ICM-20948 (6-axis) | 2–10 g |
| Actuator | micro digital servo (3.7–9 g class) driving a ratchet/spool | ~10 g |
| Battery | 1S 300 mAh LiPo | ~17 g |
| Charging | TP4056 USB-C board | ~1 g |
| Override | single tactile button (loosen) + long-press (freeze) | ~1 g |
| Structure | 25 mm webbing, printed buckle shell, spool | ~45 g |
| **Total** | | **~95 g** |

## Fail-loose in hardware, not just software

- The actuator RELEASES webbing; a return spring takes up slack. Unpowered
  = loose. The electronics can only *tighten* by actively spending power.
- A mechanical slip clutch (or servo horn detent) enforces the tension
  ceiling even if the firmware misbehaves.
- The manual LOOSEN button is wired directly to the release path
  (hardware override of software).

## Power (numbers from `sibelt simulate`)

A simulated 3.3-hour day used ~1.95 mAh (0.5 mA sleepy system average +
8 actuator adjustments). A 300 mAh cell is roughly **150 days** of this
duty cycle; the battery is mass-dominated, not energy-dominated.

## Firmware

Port `sibelt` to MicroPython or CircuitPython — the control stack is
standard-library-only by design precisely so the identical modules can
run on-device. The IMU driver implements the `IMU` interface from
`sibelt/sensors.py`; the servo driver implements `Actuator` from
`sibelt/actuator.py`.

## Open hardware questions

1. Spool/ratchet vs. shape-memory-alloy contraction (quieter, slower).
2. Hygiene and webbing washability with electronics in the buckle.
3. Real-device validation of the waist-worn posture classifier — the
   known weak spot the software already treats cautiously.
