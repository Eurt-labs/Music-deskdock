# ESP32 DevKit V1 - Hardware Pin Layout & Wiring Guide

This document provides the exact pin connections, electrical requirements, and wiring notes for building the ESP32 Music Visualizer & Hardware Media Controller.

---

## 1. Overview & Board Specifications

- **Microcontroller**: ESP32 DevKit V1 (30-pin or 38-pin module)
- **Core Clock**: 240 MHz (Dual Core Xtensa LX6)
- **Display**: 1.8" ST7735 TFT LCD (160 x 128 resolution, SPI interface)
- **Framework**: Arduino / PlatformIO

---

## 2. Complete Pin Mapping Table

| Component | Module Pin | ESP32 Pin | GPIO | Pin Mode / Type | Purpose / Description |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **ST7735 TFT Screen** | VCC | 3.3V | — | Power | Display power (3.3V logic) |
| | GND | GND | — | Ground | Common system ground |
| | LED / BLK | 3.3V | — | Power | Backlight anode (connect to 3.3V) |
| | CS | D5 | GPIO 5 | Output (SPI CS) | Chip Select |
| | RESET / RST | D4 | GPIO 4 | Output (Digital) | Hardware Display Reset |
| | A0 / DC | D2 | GPIO 2 | Output (Digital) | Data / Command selector |
| | SDA / MOSI | D23 | GPIO 23 | Hardware SPI | VSPI MOSI (Master Out Slave In) |
| | SCK / SCL | D18 | GPIO 18 | Hardware SPI | VSPI Clock line |
| **Navigation Buttons** | UP Switch | D25 | GPIO 25 | `INPUT_PULLUP` | **Previous Track** (Short to GND when pressed) |
| | SELECT Switch | D26 | GPIO 26 | `INPUT_PULLUP` | **Play / Pause** (Short to GND when pressed) |
| | DOWN Switch | D33 | GPIO 33 | `INPUT_PULLUP` | **Next Track** (Short to GND when pressed) |
| **Status LEDs** | Blue LED | D12 | GPIO 12 | Output (Digital) | **Wi-Fi Connected & Streaming** |
| | Green LED | D14 | GPIO 14 | Output (PWM) | **Music Beat Pulse** (software dimmed) |
| | Red LED | D27 | GPIO 27 | Output (Digital) | **Idle / Disconnected / Paused** |

---

## 3. Wiring Details & Component Notes

### A. ST7735 1.8" TFT Display (SPI)
- **Controller IC**: ST7735 / ST7735R (Black Tab variant, `INITR_BLACKTAB`).
- **Screen Resolution**: 128 x 160 pixels in portrait orientation (`tft.setRotation(0)`).
- **SPI Bus**: Uses the ESP32 hardware VSPI peripheral (SCK on GPIO 18, MOSI on GPIO 23) for maximum frame transfer speeds.
- **Power**: Connect VCC and LED (Backlight) to the ESP32 3.3V rail. Do not connect logic pins to 5V.

### B. Navigation Push Buttons (Active Low)
- **Configuration**: Uses the ESP32 internal pull-up resistors (`INPUT_PULLUP`). No external pull-up resistors are required.
- **Wiring**: Connect one side of each tactile button to the designated GPIO (25, 26, 33) and the other side to a common Ground (`GND`).
- **Logic**: Reads `HIGH` (1) when idle, and drops to `LOW` (0) when pressed. Debouncing is handled in software with a 220ms cooldown.

### C. Status LEDs
- **Current Limiting**: Place a 220Ω to 330Ω resistor in series between each GPIO pin and the LED anode (+ leg), with the cathode (- leg) connected to GND.
- **Blue LED (GPIO 12)**: Illuminates steadily once the ESP32 establishes a Wi-Fi connection and is actively listening for incoming packets.
- **Green LED (GPIO 14)**: Flashes in sync with detected bass kicks and music beats. The firmware uses PWM analog control (~20% duty cycle) so it creates a punchy pulse without blinding glare.
- **Red LED (GPIO 27)**: Stays ON during initial boot, when disconnected from Wi-Fi, or when no audio packet has been received from the PC for more than 2.5 seconds (idle/standby mode).

---

## 4. Breadboard Assembly Checklist

1. Connect ESP32 `GND` rail to the breadboard common ground bus.
2. Connect ESP32 `3.3V` rail to the display `VCC` and `LED/BLK` pins.
3. Wire the 5 SPI control lines from the display to ESP32 pins D5, D4, D2, D23, and D18.
4. Wire 3 tactile buttons from D25, D26, D33 to GND.
5. Wire 3 LEDs from D12 (Blue), D14 (Green), and D27 (Red) through 220Ω resistors to GND.

