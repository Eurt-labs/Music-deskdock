/**
 * ESP32 Music Visualizer & Hardware Media Controller Firmware
 * ==========================================================
 * 
 * Hardware:
 * - ESP32 DevKit V1 (Xtensa Dual-Core 240 MHz)
 * - 1.8" ST7735 TFT LCD Display (160x128 resolution, SPI interface)
 * - 3x Tactile Push Buttons (Previous, Play/Pause, Next)
 * - 3x Status LEDs (Blue: Wi-Fi/Sync, Green: Beat Pulse, Red: Idle/Standby)
 * 
 * Architecture & Memory Design:
 * -----------------------------
 * 1. Double-Buffered Rendering (Zero Screen Flicker):
 *    - Direct-to-screen drawing on SPI displays can cause visible tearing and flashing.
 *    - We allocate an off-screen 16-bit framebuffer canvas (`GFXcanvas16`) in ESP32 RAM:
 *      160 x 128 pixels x 2 bytes = 40,960 bytes (~40 KB).
 *    - All UI components (cover art, borders, volume bar, marquee text) are rendered
 *      in memory first, then transferred to the display in a single block write.
 * 
 * 2. Dedicated Album Cover Buffer:
 *    - 128 x 128 pixels x 2 bytes = 32,768 bytes (~32 KB).
 *    - Stores the active raw RGB565 album artwork downloaded from the PC.
 *    - Total graphics RAM usage is ~73 KB, easily fitting within ESP32's 320 KB SRAM.
 * 
 * 3. Network Architecture:
 *    - UDP (Port 12345): Fast, low-latency audio telemetry reception (volume, beat, title)
 *      and bidirectional hardware button command transmission to the PC.
 *    - HTTP (Port 8080): Pulls the full 32 KB raw RGB565 bitmap from the PC host
 *      whenever the track / cover ID changes.
 */

#include <Arduino.h>
#include <WiFi.h>
#include <WiFiUdp.h>
#include <HTTPClient.h>
#include <Adafruit_GFX.h>
#include <Adafruit_ST7735.h>
#include <SPI.h>
#include <ArduinoJson.h>


// =============================================================================
// HARDWARE PIN DEFINITIONS (matches HARDWARE_PINOUT.md)
// =============================================================================

// ST7735 SPI Display Interface (ESP32 VSPI peripheral)
#define TFT_CS     5   // D5  (GPIO 5)  -> Chip Select
#define TFT_RST    4   // D4  (GPIO 4)  -> Hardware Reset
#define TFT_DC     2   // D2  (GPIO 2)  -> Data / Command Select (A0)
#define TFT_MOSI   23  // D23 (GPIO 23) -> SPI MOSI (Master Out Slave In)
#define TFT_SCLK   18  // D18 (GPIO 18) -> SPI Serial Clock

// Physical Navigation Push Buttons (Active Low with Internal Pull-Ups)
#define PIN_BTN_UP     25  // D25 (GPIO 25) -> PREVIOUS TRACK (Short to GND when pressed)
#define PIN_BTN_SELECT 26  // D26 (GPIO 26) -> PLAY / PAUSE   (Short to GND when pressed)
#define PIN_BTN_DOWN   33  // D33 (GPIO 33) -> NEXT TRACK     (Short to GND when pressed)

// Status Indicator LEDs (Active High)
#define PIN_LED_BLUE   12  // D12 (GPIO 12) -> Wi-Fi Connected & Streaming telemetry
#define PIN_LED_GREEN  14  // D14 (GPIO 14) -> Music Beat Pulse (PWM brightness modulated)
#define PIN_LED_RED    27  // D27 (GPIO 27) -> Idle / Disconnected / Paused


// =============================================================================
// WI-FI & NETWORK CONFIGURATION
// =============================================================================
const char* ssid     = "Airtel_Dhruv";
const char* password = "space1524";

WiFiUDP udp;
const uint16_t UDP_PORT = 12345;


// =============================================================================
// DISPLAY & GRAPHICS BUFFERS
// =============================================================================

// Initialize ST7735 display object on hardware SPI pins
Adafruit_ST7735 tft = Adafruit_ST7735(TFT_CS, TFT_DC, TFT_MOSI, TFT_SCLK, TFT_RST);

// Double-buffer canvas (160x128 pixels in 16-bit color = 40.9 KB in RAM)
GFXcanvas16 canvas(160, 128);

// Dedicated RAM buffer holding 128x128 raw RGB565 album cover pixels (32.7 KB in RAM)
uint16_t coverBuffer[128 * 128];
int loadedCoverID = -1;  // Tracks currently loaded cover version to avoid redundant HTTP downloads


// =============================================================================
// 16-BIT RGB565 COLOR THEME PALETTE
// =============================================================================
// Format: 5 bits Red (bits 11-15), 6 bits Green (bits 5-10), 5 bits Blue (bits 0-4)
#define COLOR_BG          0x0842  // Deep dark slate background
#define COLOR_CYAN        0x07FF  // Vibrant electric cyan
#define COLOR_MAGENTA     0xF81F  // Neon magenta
#define COLOR_YELLOW      0xFFE0  // Bright gold yellow
#define COLOR_WHITE       0xFFFF  // Crisp white
#define COLOR_DARK_GRAY   0x18C3  // Dark grey for side control panel and banner overlay


// =============================================================================
// APPLICATION STATE MANAGEMENT
// =============================================================================
struct AudioState {
  uint8_t volume = 0;              // Current volume level (0 - 100)
  bool beat = false;               // True when a bass kick beat is detected
  int coverID = -1;                // ID of current album cover on host PC
  String hostIP = "";              // Host PC IP address (reported by UDP packets)
  String song = "No Song Playing"; // Current song title and artist string
  unsigned long lastPacketTime = 0;// Millis timestamp of last received UDP packet
} audioState;

// Button debouncing & marquee animation state
unsigned long lastBtnTime = 0;
const unsigned long DEBOUNCE_DELAY = 220; // 220 ms debounce window to avoid false double triggers
int scrollPos = 0;
unsigned long lastScrollTime = 0;


// =============================================================================
// UDP BUTTON COMMAND TRANSMITTER
// =============================================================================
/**
 * Sends a JSON media control command back to the host PC over UDP.
 * 
 * Example payload: {"cmd": "playpause"}
 */
void sendUDPCommand(const char* cmd) {
  if (audioState.hostIP.length() == 0) return;
  
  JsonDocument doc;
  doc["cmd"] = cmd;
  
  char buffer[128];
  size_t len = serializeJson(doc, buffer);
  
  udp.beginPacket(audioState.hostIP.c_str(), UDP_PORT);
  udp.write((const uint8_t*)buffer, len);
  udp.endPacket();
  
  Serial.printf("[ESP32] Sent button command: %s to %s\n", cmd, audioState.hostIP.c_str());
}


/**
 * Polls the physical navigation buttons with software debouncing.
 * Sends 'prev', 'playpause', or 'next' commands to PC when buttons are pressed.
 */
void handleButtons() {
  if (millis() - lastBtnTime < DEBOUNCE_DELAY) return;

  if (digitalRead(PIN_BTN_UP) == LOW) {
    sendUDPCommand("prev");
    lastBtnTime = millis();
  } else if (digitalRead(PIN_BTN_SELECT) == LOW) {
    sendUDPCommand("playpause");
    lastBtnTime = millis();
  } else if (digitalRead(PIN_BTN_DOWN) == LOW) {
    sendUDPCommand("next");
    lastBtnTime = millis();
  }
}


// =============================================================================
// DEFAULT ALBUM ARTWORK GENERATOR
// =============================================================================
/**
 * Procedurally draws a retro vinyl record cover into `coverBuffer`.
 * Used on initial boot, when music is stopped, or when no online cover art is available.
 */
void drawDefaultCover() {
  for (int y = 0; y < 128; y++) {
    for (int x = 0; x < 128; x++) {
      int dx = x - 64;
      int dy = y - 64;
      int distSq = dx * dx + dy * dy;
      
      if (distSq <= 12 * 12) {
        // Gold center spindle label
        coverBuffer[y * 128 + x] = COLOR_YELLOW;
      } else if (distSq <= 50 * 50 && distSq >= 16 * 16) {
        // Alternating concentric vinyl record grooves
        if ((int)(sqrt(distSq)) % 4 == 0) {
          coverBuffer[y * 128 + x] = 0x1082;
        } else {
          coverBuffer[y * 128 + x] = 0x0000;
        }
      } else {
        // Outer dark background fill
        coverBuffer[y * 128 + x] = COLOR_BG;
      }
    }
  }
}


// =============================================================================
// HTTP ALBUM ARTWORK DOWNLOADER
// =============================================================================
/**
 * Downloads the 32 KB raw RGB565 image from the PC HTTP server on port 8080.
 * 
 * Streams the incoming bytes directly into `coverBuffer` without intermediate
 * file system (LittleFS/SPIFFS) writes, minimizing flash wear and latency.
 */
void fetchAlbumCover(const String& ip, int cid) {
  if (ip.length() == 0 || cid < 0) return;
  loadedCoverID = cid;

  HTTPClient http;
  String url = "http://" + ip + ":8080/cover.raw";
  
  http.begin(url);
  http.setTimeout(1200);  // 1.2s timeout to avoid blocking frame render loops
  int httpCode = http.GET();

  if (httpCode == HTTP_CODE_OK) {
    WiFiClient* stream = http.getStreamPtr();
    size_t bytesRead = 0;
    uint8_t* buf = (uint8_t*)coverBuffer;

    // Read 32,768 bytes in chunks from the TCP stream
    while (http.connected() && bytesRead < 32768) {
      size_t avail = stream->available();
      if (avail > 0) {
        size_t readNow = stream->readBytes(buf + bytesRead, min(avail, (size_t)(32768 - bytesRead)));
        bytesRead += readNow;
      }
    }
    if (bytesRead == 32768) {
      Serial.println("[ESP32] Album cover art downloaded successfully.");
    }
  }
  http.end();
}


// =============================================================================
// BOOT & DIAGNOSTIC SCREEN
// =============================================================================
/**
 * Renders connection status and debug info directly to the display during startup.
 */
void drawBootScreen(const char* statusMsg) {
  tft.fillScreen(COLOR_BG);
  tft.setTextColor(COLOR_CYAN);
  tft.setTextSize(1);
  
  tft.setCursor(10, 15);
  tft.println("ESP32 MUSIC SYSTEM");
  tft.drawFastHLine(10, 26, 140, COLOR_MAGENTA);
  
  tft.setTextColor(COLOR_WHITE);
  tft.setCursor(10, 40);
  tft.print("SSID: ");
  tft.println(ssid);

  tft.setCursor(10, 60);
  tft.println("Status:");
  tft.setTextColor(COLOR_YELLOW);
  tft.setCursor(10, 75);
  tft.println(statusMsg);
}


// =============================================================================
// ARDUINO SETUP
// =============================================================================
void setup() {
  Serial.begin(115200);

  // 1. Configure Navigation Push Buttons (Input with internal pull-up)
  pinMode(PIN_BTN_UP, INPUT_PULLUP);
  pinMode(PIN_BTN_SELECT, INPUT_PULLUP);
  pinMode(PIN_BTN_DOWN, INPUT_PULLUP);

  // 2. Configure Status LEDs
  pinMode(PIN_LED_BLUE, OUTPUT);
  pinMode(PIN_LED_GREEN, OUTPUT);
  pinMode(PIN_LED_RED, OUTPUT);

  digitalWrite(PIN_LED_BLUE, LOW);
  digitalWrite(PIN_LED_GREEN, LOW);
  digitalWrite(PIN_LED_RED, HIGH); // Red LED on during boot / unconnected state

  // 3. Initialize default cover art graphic
  drawDefaultCover();

  // 4. Initialize ST7735 Display (160x128 Landscape Mode)
  tft.initR(INITR_BLACKTAB); 
  tft.setRotation(1); // Rotation 1 = 160 width x 128 height
  tft.fillScreen(COLOR_BG);

  drawBootScreen("Connecting Wi-Fi...");

  // 5. Connect to local Wi-Fi network
  WiFi.mode(WIFI_STA);
  WiFi.begin(ssid, password);

  int retries = 0;
  while (WiFi.status() != WL_CONNECTED && retries < 30) {
    delay(500);
    Serial.print(".");
    retries++;
  }

  if (WiFi.status() == WL_CONNECTED) {
    digitalWrite(PIN_LED_BLUE, HIGH);
    digitalWrite(PIN_LED_RED, LOW);

    // Start UDP listener
    udp.begin(UDP_PORT);

    // Show IP address on screen so the user knows what to enter in Python
    tft.fillScreen(COLOR_BG);
    tft.setTextColor(COLOR_CYAN);
    tft.setTextSize(1);
    tft.setCursor(15, 20);
    tft.println("CONNECTED!");
    
    tft.setTextColor(COLOR_YELLOW);
    tft.setCursor(10, 45);
    tft.println("IP Address:");
    tft.setTextColor(COLOR_WHITE);
    tft.setCursor(10, 60);
    tft.println(WiFi.localIP());

    tft.setCursor(10, 90);
    tft.setTextColor(COLOR_MAGENTA);
    tft.println("Waiting for audio...");
    delay(1600);
  } else {
    drawBootScreen("Wi-Fi Connection Failed!");
    delay(3000);
  }

  tft.fillScreen(COLOR_BG);
}


// =============================================================================
// UI FRAME RENDERING PIPELINE
// =============================================================================
/**
 * Composes all visual UI elements into the `canvas` double-buffer in RAM:
 * 1. Left 128x128 pixels: Album cover bitmap + dynamic beat neon borders.
 * 2. Right 32 pixels: Side panel with volume level equalizer bar & play indicator.
 * 3. Bottom 18-pixel strip: Horizontal scrolling marquee showing song title & artist.
 * 4. LED outputs: Blue (Wi-Fi), Green (PWM Beat pulse), Red (Idle timeout).
 * 
 * Finally, transfers the complete 160x128 framebuffer to the display over SPI.
 */
void renderFrame(uint8_t volume, bool beat, const String& songTitle, bool isConnected) {
  canvas.fillScreen(COLOR_BG);

  // Watchdog: If no UDP packet arrived in >2.5s, consider playback idle/disconnected
  bool isIdle = !isConnected || (millis() - audioState.lastPacketTime > 2500);

  // --- LED Feedback Updates ---
  digitalWrite(PIN_LED_BLUE, isConnected ? HIGH : LOW);
  digitalWrite(PIN_LED_RED, isIdle ? HIGH : LOW);
  
  // Pulse Green LED on music beats using PWM analog write (~20% duty cycle to prevent glare)
  if (beat && !isIdle) {
    analogWrite(PIN_LED_GREEN, 50);
  } else {
    analogWrite(PIN_LED_GREEN, 0);
  }

  // --- 1. LEFT 128x128 ALBUM COVER ART ---
  if (!isIdle) {
    canvas.drawRGBBitmap(0, 0, coverBuffer, 128, 128);
    // Draw pulsing neon frame on detected beat kicks
    if (beat) {
      canvas.drawRect(0, 0, 128, 128, COLOR_MAGENTA);
      canvas.drawRect(1, 1, 126, 126, COLOR_YELLOW);
    }
  } else {
    canvas.drawRGBBitmap(0, 0, coverBuffer, 128, 128);
    // Draw "WAITING" badge when idle
    canvas.fillRect(15, 50, 98, 26, COLOR_BG);
    canvas.drawRect(15, 50, 98, 26, COLOR_CYAN);
    canvas.setTextColor(COLOR_YELLOW);
    canvas.setTextSize(1);
    canvas.setCursor(24, 59);
    canvas.print("~ WAITING ~");
  }

  // --- 2. RIGHT 32-PIXEL SIDE PANEL (X = 128 to 159) ---
  canvas.fillRect(128, 0, 32, 128, COLOR_DARK_GRAY);
  canvas.drawFastVLine(128, 0, 128, COLOR_MAGENTA);

  // Play / Status Indicator Symbol
  canvas.setTextColor(isIdle ? COLOR_YELLOW : COLOR_CYAN);
  canvas.setTextSize(1);
  canvas.setCursor(138, 8);
  canvas.print((char)16); // ASCII right-pointing triangle / play symbol

  // Vertical Audio Volume Equalizer Bar (Height maps 0-100% volume to 0-80 pixels)
  int barH = map(volume, 0, 100, 0, 80);
  canvas.fillRect(138, 110 - barH, 12, barH, beat ? COLOR_YELLOW : COLOR_CYAN);
  canvas.drawRect(138, 30, 12, 80, COLOR_WHITE);

  // --- 3. BOTTOM SCROLLING SONG MARQUEE ---
  String title = isIdle ? "No Song Playing" : songTitle;
  if (title.length() == 0) title = "Unknown Song";

  const int maxCharsVisible = 18;
  String dispText = title;

  // Scroll text horizontally if it exceeds visible character limit
  if (title.length() > maxCharsVisible) {
    if (millis() - lastScrollTime > 260) {
      scrollPos++;
      if (scrollPos > (int)title.length() + 3) {
        scrollPos = 0;
      }
      lastScrollTime = millis();
    }
    String extendedStr = title + "   " + title;
    dispText = extendedStr.substring(scrollPos, scrollPos + maxCharsVisible);
  } else {
    scrollPos = 0;
  }

  // Draw semi-opaque bottom banner across the bottom of the cover art
  canvas.fillRect(0, 110, 128, 18, COLOR_DARK_GRAY);
  canvas.drawFastHLine(0, 110, 128, COLOR_CYAN);
  canvas.setTextColor(COLOR_WHITE);
  canvas.setCursor(4, 115);
  canvas.print(dispText);

  // --- 4. FLUSH DOUBLE-BUFFER TO PHYSICAL TFT DISPLAY ---
  tft.drawRGBBitmap(0, 0, canvas.getBuffer(), 160, 128);
}


// =============================================================================
// UDP TELEMETRY PACKET PARSER
// =============================================================================
/**
 * Receives and parses incoming JSON telemetry packets from the PC.
 * 
 * Expected JSON schema:
 * {
 *   "v": 64,                     // Volume (0-100)
 *   "b": 1,                      // Beat trigger flag (0 or 1)
 *   "s": "Artist - Song Name",   // Song metadata string
 *   "cid": 3,                    // Active cover art version ID
 *   "ip": "192.168.1.100"        // Host PC IP for HTTP downloads
 * }
 */
void processUDP() {
  int packetSize = udp.parsePacket();
  if (packetSize > 0) {
    char buffer[384];
    int len = udp.read(buffer, sizeof(buffer) - 1);
    if (len > 0) {
      buffer[len] = '\0';
      
      JsonDocument doc;
      DeserializationError err = deserializeJson(doc, buffer);
      if (!err) {
        audioState.volume  = doc["v"] | 0;
        audioState.beat    = (doc["b"] | 0) == 1;
        audioState.coverID = doc["cid"] | -1;
        
        if (doc["ip"]) {
          audioState.hostIP = doc["ip"].as<String>();
        }
        if (doc["s"]) {
          audioState.song = doc["s"].as<String>();
        }
        audioState.lastPacketTime = millis();
      }
    }
  }
}


// =============================================================================
// MAIN EXECUTION LOOP
// =============================================================================
void loop() {
  // 1. Process incoming audio telemetry over UDP
  processUDP();

  // 2. Poll navigation buttons and dispatch UDP actions if pressed
  handleButtons();

  // 3. Check if PC reported a new album cover ID; if so, fetch over HTTP
  if (audioState.coverID != loadedCoverID && audioState.hostIP.length() > 0) {
    fetchAlbumCover(audioState.hostIP, audioState.coverID);
  }

  // 4. Render updated UI frame to the display
  bool isConnected = (WiFi.status() == WL_CONNECTED);
  renderFrame(audioState.volume, audioState.beat, audioState.song, isConnected);

  // 5. Short yield delay to feed ESP32 RTOS watchdog timer
  delay(15);
}

