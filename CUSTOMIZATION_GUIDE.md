# ESP32 Music Deskdock - Customization & Display Guide

This comprehensive guide explains how display orientation, screen layouts, on-screen text, colors, and visual animations work in this project, and provides step-by-step instructions on how to customize every element.

---

## Table of Contents
1. [How Display Orientation Works](#1-how-display-orientation-works)
2. [Display Orientation Modes (0, 1, 2, 3)](#2-display-orientation-modes-0-1-2-3)
3. [Customizing On-Screen Texts](#3-customizing-on-screen-texts)
4. [Customizing Colors & Color Themes (RGB565)](#4-customizing-colors--color-themes-rgb565)
5. [Customizing Visual Elements & Animations](#5-customizing-visual-elements--animations)
6. [Building & Uploading Firmware](#6-building--uploading-firmware)

---

## 1. How Display Orientation Works

The 1.8" ST7735 TFT display is controlled by two main objects in [`src/main.cpp`](file:///c:/Users/Dhruv%20Saraswat/Downloads/Music-deskdock/src/main.cpp):

1. **Physical Display Hardware (`Adafruit_ST7735 tft`)**:
   - Initialized in `setup()` using `tft.initR(INITR_BLACKTAB);`.
   - Orientation is set with `tft.setRotation(N);` where `N` is an integer from `0` to `3`.

2. **Off-Screen Double Buffer Canvas (`GFXcanvas16 canvas`)**:
   - To achieve zero screen tearing and flicker, all UI graphics are drawn to a RAM buffer first:
     ```cpp
     GFXcanvas16 canvas(WIDTH, HEIGHT);
     ```
   - In **Portrait mode** (Rotation `0` or `2`): Dimensions are `128` (Width) x `160` (Height).
   - In **Landscape mode** (Rotation `1` or `3`): Dimensions are `160` (Width) x `128` (Height).
   - Once all elements are drawn into `canvas`, it is pushed to the physical screen over SPI in one fast block transfer:
     ```cpp
     tft.drawRGBBitmap(0, 0, canvas.getBuffer(), WIDTH, HEIGHT);
     ```

> [!IMPORTANT]
> Whenever you switch between **Portrait** (128x160) and **Landscape** (160x128), you must update both the **canvas dimensions** and the **`renderFrame()` drawing coordinates**.

---

## 2. Display Orientation Modes (0, 1, 2, 3)

The ST7735 controller supports 4 hardware rotations:

| Rotation Value | Mode | Resolution (W x H) | Description |
| :---: | :---: | :---: | :--- |
| `0` | **Portrait** | 128 x 160 | Default portrait (header pins at top/bottom) |
| `1` | **Landscape** | 160 x 128 | 90° clockwise landscape (album art on left, panel on right) |
| `2` | **Portrait Inverted** | 128 x 160 | 180° portrait upside-down (flipped 180° from `0`) |
| `3` | **Landscape Inverted** | 160 x 128 | 270° clockwise landscape (flipped 180° from `1`) |

### How to Switch Orientations in Code

#### A. Setting Portrait Mode (`setRotation(0)` or `setRotation(2)`)
1. In [`src/main.cpp`](file:///c:/Users/Dhruv%20Saraswat/Downloads/Music-deskdock/src/main.cpp#L82), set canvas size:
   ```cpp
   GFXcanvas16 canvas(128, 160);
   ```
2. In [`setup()`](file:///c:/Users/Dhruv%20Saraswat/Downloads/Music-deskdock/src/main.cpp#L292):
   ```cpp
   tft.setRotation(0); // or 2 for inverted portrait
   ```
3. In [`renderFrame()`](file:///c:/Users/Dhruv%20Saraswat/Downloads/Music-deskdock/src/main.cpp#L435):
   ```cpp
   tft.drawRGBBitmap(0, 0, canvas.getBuffer(), 128, 160);
   ```

#### B. Setting Landscape Mode (`setRotation(1)` or `setRotation(3)`)
1. In [`src/main.cpp`](file:///c:/Users/Dhruv%20Saraswat/Downloads/Music-deskdock/src/main.cpp#L82), set canvas size:
   ```cpp
   GFXcanvas16 canvas(160, 128);
   ```
2. In [`setup()`](file:///c:/Users/Dhruv%20Saraswat/Downloads/Music-deskdock/src/main.cpp#L292):
   ```cpp
   tft.setRotation(1); // or 3 for inverted landscape
   ```
3. In [`renderFrame()`](file:///c:/Users/Dhruv%20Saraswat/Downloads/Music-deskdock/src/main.cpp#L435):
   ```cpp
   tft.drawRGBBitmap(0, 0, canvas.getBuffer(), 160, 128);
   ```

---

## 3. Customizing On-Screen Texts

All text strings rendered across the application lifecycle can be modified directly in [`src/main.cpp`](file:///c:/Users/Dhruv%20Saraswat/Downloads/Music-deskdock/src/main.cpp):

### 1. Boot Screen & Diagnostic Text
Located in `drawBootScreen()` (around lines 245–264):
```cpp
void drawBootScreen(const char* statusMsg) {
  tft.fillScreen(COLOR_BG);
  tft.setTextColor(COLOR_CYAN);
  tft.setTextSize(1);
  
  tft.setCursor(10, 15);
  tft.println("ESP32 MUSIC SYSTEM");          // <--- Change Main Header Title
  tft.drawFastHLine(10, 26, 108, COLOR_MAGENTA); // <--- Separator Line
  
  tft.setTextColor(COLOR_WHITE);
  tft.setCursor(10, 40);
  tft.print("SSID: ");                         // <--- Wi-Fi Label
  tft.println(ssid);

  tft.setCursor(10, 60);
  tft.println("Status:");                      // <--- Status Label
  tft.setTextColor(COLOR_YELLOW);
  tft.setCursor(10, 75);
  tft.println(statusMsg);                      // <--- "Connecting Wi-Fi..." / "Wi-Fi Connection Failed!"
}
```

### 2. Wi-Fi Connected & IP Address Screen
Located in `setup()` (around lines 315–335):
```cpp
// Show IP address on screen so the user knows what to enter in Python
tft.fillScreen(COLOR_BG);
tft.setTextColor(COLOR_CYAN);
tft.setTextSize(1);
tft.setCursor(15, 20);
tft.println("CONNECTED!");                     // <--- Change Connection Banner

tft.setTextColor(COLOR_YELLOW);
tft.setCursor(10, 45);
tft.println("IP Address:");                    // <--- IP Header
tft.setTextColor(COLOR_WHITE);
tft.setCursor(10, 60);
tft.println(WiFi.localIP());

tft.setCursor(10, 90);
tft.setTextColor(COLOR_MAGENTA);
tft.println("Waiting for audio...");           // <--- Subtitle / Ready prompt
```

### 3. Idle / Standby "WAITING" Badge
Located in `renderFrame()` (around lines 380–390):
```cpp
// Draw "WAITING" badge when idle
canvas.fillRect(15, 50, 98, 26, COLOR_BG);
canvas.drawRect(15, 50, 98, 26, COLOR_CYAN);
canvas.setTextColor(COLOR_YELLOW);
canvas.setTextSize(1);
canvas.setCursor(24, 59);
canvas.print("~ WAITING ~");                  // <--- Change Idle Badge Text (e.g., "STANDBY", "IDLE")
```

### 4. Default Fallback Song Titles
Located in `struct AudioState` and `renderFrame()` (around lines 109 and 395):
```cpp
// Default state when booted:
String song = "No Song Playing";              // <--- Default fallback string

// In renderFrame:
String title = isIdle ? "No Song Playing" : songTitle;
if (title.length() == 0) title = "Unknown Song";
```

### 5. Font Sizing and Placement Rules
- `tft.setTextSize(1)`: Default 5x7 pixel font (6x8 with spacing). Recommended for maximum readability and information density on small 1.8" displays.
- `tft.setTextSize(2)`: 10x14 pixel font (12x16 with spacing). Great for large headers.
- `tft.setCursor(X, Y)`: Sets the top-left starting coordinate for the next `print()` or `println()`.

---

## 4. Customizing Colors & Color Themes (RGB565)

The display uses **16-bit RGB565 format** (5 bits Red, 6 bits Green, 5 bits Blue).

Colors are defined at the top of [`src/main.cpp`](file:///c:/Users/Dhruv%20Saraswat/Downloads/Music-deskdock/src/main.cpp#L90-L100):

```cpp
#define COLOR_BG          0x0842  // Deep dark slate background
#define COLOR_CYAN        0x07FF  // Vibrant electric cyan
#define COLOR_MAGENTA     0xF81F  // Neon magenta
#define COLOR_YELLOW      0xFFE0  // Bright gold yellow
#define COLOR_WHITE       0xFFFF  // Crisp white
#define COLOR_DARK_GRAY   0x18C3  // Dark grey for bottom control panel
```

### Popular RGB565 Color Codes Reference

| Color Name | Hex Code | Visual Preview / Description |
| :--- | :---: | :--- |
| **Black** | `0x0000` | Pure Black |
| **Deep Dark Slate** | `0x0842` | Modern UI background dark tone |
| **Charcoal Gray** | `0x18C3` | Panel and card background |
| **Electric Cyan** | `0x07FF` | Vibrant accent color |
| **Neon Magenta / Pink** | `0xF81F` | Punchy beat border color |
| **Gold Yellow** | `0xFFE0` | High-visibility warning / beat flash |
| **Neon Lime Green** | `0x07E0` | Bright green for volume or beat pulse |
| **Vibrant Orange** | `0xFD20` | Warm accent |
| **Purple / Violet** | `0x780F` | Deep cyber purple |
| **Pure White** | `0xFFFF` | Crisp borders and text |

> [!TIP]
> You can convert standard Hex `#RRGGBB` colors to 16-bit RGB565 format using the formula:
> `((R & 0xF8) << 8) | ((G & 0xFC) << 3) | (B >> 3)`

---

## 5. Customizing Visual Elements & Animations

### 1. Song Title Marquee Scrolling Speed & Visibility
In `renderFrame()`:
```cpp
const int maxCharsVisible = 19; // Number of characters visible simultaneously
```
- Increase `maxCharsVisible` if using a smaller font or wider area.
- Scroll timing:
  ```cpp
  if (millis() - lastScrollTime > 260) { // <--- Scroll speed in milliseconds per step (lower = faster)
      scrollPos++;
      ...
  }
  ```

### 2. Volume Equalizer Bar
In portrait mode, the horizontal volume bar is located at the bottom:
```cpp
// Box Frame
canvas.drawRect(18, 147, 104, 9, COLOR_WHITE);

// Level Fill (maps 0-100% volume to 0-100 pixels width)
int barW = map(volume, 0, 100, 0, 100);
if (barW > 0) {
  canvas.fillRect(20, 149, barW, 5, beat ? COLOR_YELLOW : COLOR_CYAN);
}
```
- To change the bar thickness, adjust the height parameter (`9` for frame, `5` for fill).
- To change the color when music hits a beat, edit `beat ? COLOR_YELLOW : COLOR_CYAN`.

### 3. Pulsing Neon Beat Border
When a bass kick is detected in `renderFrame()`:
```cpp
if (beat) {
  canvas.drawRect(0, 0, 128, 128, COLOR_MAGENTA); // Outer 1px frame
  canvas.drawRect(1, 1, 126, 126, COLOR_YELLOW);  // Inner 1px frame
}
```
- You can add a third frame or change the colors to match your aesthetic theme.

### 4. Green Status LED Beat Brightness
Located in `renderFrame()`:
```cpp
if (beat && !isIdle) {
  analogWrite(PIN_LED_GREEN, 50); // PWM brightness (0 - 255). 50 is ~20% brightness to avoid blinding glare
} else {
  analogWrite(PIN_LED_GREEN, 0);
}
```
- Change `50` (up to `255`) to make the beat LED pulse dimmer or brighter.

---

## 6. Building & Uploading Firmware

To apply your changes to the physical ESP32:

1. Connect your ESP32 to your PC via USB.
2. Open terminal in the project directory:
   ```bash
   # Compile and verify with no errors
   pio run

   # Flash firmware directly to the ESP32
   pio run --target upload

   # View live debug messages via Serial Monitor
   pio device monitor
   ```
