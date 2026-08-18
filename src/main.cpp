/**
 * ESP32 Music Visualizer & Hardware Media Controller Firmware
 * ==========================================================
 * 
 * Hardware:
 * - ESP32 DevKit V1 (Xtensa Dual-Core 240 MHz)
 * - 1.8" ST7735 TFT LCD Display (128x160 portrait resolution, SPI interface)
 * - 3x Tactile Push Buttons (Previous, Play/Pause, Next)
 * - 3x Status LEDs (Blue: Wi-Fi/Sync, Green: Beat Pulse, Red: Idle/Standby)
 * 
 * Architecture & Memory Design:
 * -----------------------------
 * 1. Double-Buffered Rendering (Zero Screen Flicker):
 *    - Off-screen 16-bit framebuffer canvas (`GFXcanvas16`) in RAM (128x160x2 = 40.9 KB).
 *    - All UI components rendered to canvas first, then transferred to display in one SPI burst.
 * 
 * 2. Dedicated Album Cover Buffer:
 *    - 128x128 pixels in RGB565 format (32.7 KB in RAM).
 *    - Direct TCP stream decoding from host HTTP server.
 * 
 * 3. Robust Network & Telemetry Handling:
 *    - Large 1024-byte UDP buffer to prevent JSON token truncation.
 *    - Bidirectional Auto-Discovery: Broadcasts discovery pings so PC binds automatically.
 *    - Safe HTTP Cover Art Fetching with failure backoff and verification.
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

// Double-buffer canvas (128x160 pixels in 16-bit color = 40.9 KB in RAM)
GFXcanvas16 canvas(128, 160);

// Dedicated RAM buffer holding 128x128 raw RGB565 album cover pixels (32.7 KB in RAM)
uint16_t coverBuffer[128 * 128];
int loadedCoverID = -1;  // Tracks currently loaded cover version to avoid redundant HTTP downloads
unsigned long lastCoverAttemptTime = 0;


// =============================================================================
// 16-BIT RGB565 COLOR THEME PALETTE
// =============================================================================
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
const unsigned long DEBOUNCE_DELAY = 220;
int scrollPos = 0;
unsigned long lastScrollTime = 0;

// Auto-discovery beacon timer
unsigned long lastPingTime = 0;


// =============================================================================
// UDP BROADCAST DISCOVERY & COMMAND TRANSMITTER
// =============================================================================
/**
 * Sends a JSON media control command back to the host PC over UDP.
 */
void sendUDPCommand(const char* cmd) {
  if (audioState.hostIP.length() == 0) {
    Serial.printf("[ESP32-WARN] Cannot send '%s': Host IP unknown.\n", cmd);
    return;
  }
  
  JsonDocument doc;
  doc["cmd"] = cmd;
  
  char buffer[128];
  size_t len = serializeJson(doc, buffer);
  
  udp.beginPacket(audioState.hostIP.c_str(), UDP_PORT);
  udp.write((const uint8_t*)buffer, len);
  udp.endPacket();
  
  Serial.printf("[ESP32] Sent button action '%s' to %s:%d\n", cmd, audioState.hostIP.c_str(), UDP_PORT);
}


/**
 * Broadcasts discovery heartbeat ping on local subnet so PC host transmitter
 * automatically detects and binds to this ESP32's IP address.
 */
void sendDiscoveryPing() {
  if (WiFi.status() != WL_CONNECTED) return;

  JsonDocument doc;
  doc["cmd"] = "ping";
  doc["dev"] = "ESP32_MusicDock";
  doc["ip"] = WiFi.localIP().toString();

  char buffer[160];
  size_t len = serializeJson(doc, buffer);

  // Broadcast to local subnet
  IPAddress broadcastIP = ~WiFi.subnetMask() | WiFi.gatewayIP();
  udp.beginPacket(broadcastIP, UDP_PORT);
  udp.write((const uint8_t*)buffer, len);
  udp.endPacket();

  Serial.printf("[ESP32-DISCOVERY] Broadcast ping sent -> %s:%d\n", broadcastIP.toString().c_str(), UDP_PORT);
}


/**
 * Polls physical navigation buttons with software debouncing.
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
void drawDefaultCover() {
  for (int y = 0; y < 128; y++) {
    for (int x = 0; x < 128; x++) {
      int dx = x - 64;
      int dy = y - 64;
      int distSq = dx * dx + dy * dy;
      
      if (distSq <= 12 * 12) {
        coverBuffer[y * 128 + x] = COLOR_YELLOW;
      } else if (distSq <= 50 * 50 && distSq >= 16 * 16) {
        if ((int)(sqrt(distSq)) % 4 == 0) {
          coverBuffer[y * 128 + x] = 0x1082;
        } else {
          coverBuffer[y * 128 + x] = 0x0000;
        }
      } else {
        coverBuffer[y * 128 + x] = COLOR_BG;
      }
    }
  }
}


// =============================================================================
// HTTP ALBUM ARTWORK DOWNLOADER
// =============================================================================
void fetchAlbumCover(const String& ip, int cid) {
  if (ip.length() == 0 || cid < 0) return;

  // Rate-limit retries if server was unreachable (cooldown 3s)
  if (millis() - lastCoverAttemptTime < 3000) return;
  lastCoverAttemptTime = millis();

  HTTPClient http;
  String url = "http://" + ip + ":8080/cover.raw";
  
  Serial.printf("[ESP32-HTTP] Fetching album cover ID %d from %s...\n", cid, url.c_str());

  http.begin(url);
  http.setTimeout(1000);  // 1.0s timeout
  int httpCode = http.GET();

  if (httpCode == HTTP_CODE_OK) {
    WiFiClient* stream = http.getStreamPtr();
    size_t bytesRead = 0;
    uint8_t* buf = (uint8_t*)coverBuffer;
    unsigned long fetchStart = millis();

    while (http.connected() && bytesRead < 32768 && (millis() - fetchStart < 1500)) {
      size_t avail = stream->available();
      if (avail > 0) {
        size_t readNow = stream->readBytes(buf + bytesRead, min(avail, (size_t)(32768 - bytesRead)));
        bytesRead += readNow;
      } else {
        delay(2);
      }
    }

    if (bytesRead == 32768) {
      loadedCoverID = cid;
      Serial.printf("[ESP32-HTTP] Cover ID %d successfully loaded (32,768 bytes in %lu ms).\n", cid, millis() - fetchStart);
    } else {
      Serial.printf("[ESP32-HTTP-WARN] Incomplete cover download: %u/32768 bytes.\n", bytesRead);
    }
  } else {
    Serial.printf("[ESP32-HTTP-ERR] HTTP GET failed (Code: %d, Err: %s)\n", httpCode, http.errorToString(httpCode).c_str());
  }
  http.end();
}


// =============================================================================
// BOOT & DIAGNOSTIC SCREEN
// =============================================================================
void drawBootScreen(const char* statusMsg) {
  tft.fillScreen(COLOR_BG);
  tft.setTextColor(COLOR_CYAN);
  tft.setTextSize(1);
  
  tft.setCursor(10, 15);
  tft.println("ESP32 MUSIC SYSTEM");
  tft.drawFastHLine(10, 26, 108, COLOR_MAGENTA);
  
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
  delay(200);
  Serial.println("\n==================================================");
  Serial.println("   ESP32 Music Visualizer & Controller Firmware   ");
  Serial.println("==================================================");

  // 1. Configure Navigation Push Buttons
  pinMode(PIN_BTN_UP, INPUT_PULLUP);
  pinMode(PIN_BTN_SELECT, INPUT_PULLUP);
  pinMode(PIN_BTN_DOWN, INPUT_PULLUP);

  // 2. Configure Status LEDs
  pinMode(PIN_LED_BLUE, OUTPUT);
  pinMode(PIN_LED_GREEN, OUTPUT);
  pinMode(PIN_LED_RED, OUTPUT);

  digitalWrite(PIN_LED_BLUE, LOW);
  digitalWrite(PIN_LED_GREEN, LOW);
  digitalWrite(PIN_LED_RED, HIGH);

  // 3. Initialize default cover art graphic
  drawDefaultCover();

  // 4. Initialize ST7735 Display (128x160 Portrait Mode)
  tft.initR(INITR_BLACKTAB); 
  tft.setRotation(0);
  tft.fillScreen(COLOR_BG);

  drawBootScreen("Connecting Wi-Fi...");

  // 5. Connect to Wi-Fi network
  WiFi.mode(WIFI_STA);
  WiFi.begin(ssid, password);

  int retries = 0;
  while (WiFi.status() != WL_CONNECTED && retries < 30) {
    delay(500);
    Serial.print(".");
    retries++;
  }
  Serial.println();

  if (WiFi.status() == WL_CONNECTED) {
    digitalWrite(PIN_LED_BLUE, HIGH);
    digitalWrite(PIN_LED_RED, LOW);

    // Start UDP listener
    udp.begin(UDP_PORT);
    Serial.printf("[ESP32] Wi-Fi Connected! IP: %s, Listening on UDP %d\n", WiFi.localIP().toString().c_str(), UDP_PORT);

    // Send initial broadcast discovery ping
    sendDiscoveryPing();

    // Show IP on TFT screen
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
    Serial.println("[ESP32-ERR] Wi-Fi Connection Failed!");
    drawBootScreen("Wi-Fi Failed!");
    delay(3000);
  }

  tft.fillScreen(COLOR_BG);
}


// =============================================================================
// UI FRAME RENDERING PIPELINE
// =============================================================================
void renderFrame(uint8_t volume, bool beat, const String& songTitle, bool isConnected) {
  canvas.fillScreen(COLOR_BG);

  // Watchdog: consider playback idle/disconnected if no packet for > 2.5s
  bool isIdle = !isConnected || (millis() - audioState.lastPacketTime > 2500);

  // --- LED Feedback Updates ---
  digitalWrite(PIN_LED_BLUE, isConnected ? HIGH : LOW);
  digitalWrite(PIN_LED_RED, isIdle ? HIGH : LOW);
  
  if (beat && !isIdle) {
    analogWrite(PIN_LED_GREEN, 50);
  } else {
    analogWrite(PIN_LED_GREEN, 0);
  }

  // --- 1. TOP 128x128 ALBUM COVER ART ---
  if (!isIdle) {
    canvas.drawRGBBitmap(0, 0, coverBuffer, 128, 128);
    if (beat) {
      canvas.drawRect(0, 0, 128, 128, COLOR_MAGENTA);
      canvas.drawRect(1, 1, 126, 126, COLOR_YELLOW);
    }
  } else {
    canvas.drawRGBBitmap(0, 0, coverBuffer, 128, 128);
    canvas.fillRect(15, 50, 98, 26, COLOR_BG);
    canvas.drawRect(15, 50, 98, 26, COLOR_CYAN);
    canvas.setTextColor(COLOR_YELLOW);
    canvas.setTextSize(1);
    canvas.setCursor(24, 59);
    canvas.print("~ WAITING ~");
  }

  // --- 2. BOTTOM 32-PIXEL CONTROL & INFO PANEL (Y = 128 to 159) ---
  canvas.fillRect(0, 128, 128, 32, COLOR_DARK_GRAY);
  canvas.drawFastHLine(0, 128, 128, COLOR_MAGENTA);

  String title = isIdle ? "No Song Playing" : songTitle;
  if (title.length() == 0) title = "Unknown Song";

  const int maxCharsVisible = 19;
  String dispText = title;

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

  canvas.setTextColor(COLOR_WHITE);
  canvas.setTextSize(1);
  canvas.setCursor(6, 133);
  canvas.print(dispText);

  canvas.drawFastHLine(4, 144, 120, COLOR_BG);

  canvas.setTextColor(isIdle ? COLOR_YELLOW : COLOR_CYAN);
  canvas.setTextSize(1);
  canvas.setCursor(6, 148);
  canvas.print((char)16);

  canvas.drawRect(18, 147, 104, 9, COLOR_WHITE);
  int barW = map(volume, 0, 100, 0, 100);
  if (barW > 0) {
    canvas.fillRect(20, 149, barW, 5, beat ? COLOR_YELLOW : COLOR_CYAN);
  }

  // --- 3. FLUSH FRAMEBUFFER TO TFT ---
  tft.drawRGBBitmap(0, 0, canvas.getBuffer(), 128, 160);
}


// =============================================================================
// UDP TELEMETRY PACKET PARSER
// =============================================================================
void processUDP() {
  // Drain all pending packets to always render the freshest telemetry
  while (true) {
    int packetSize = udp.parsePacket();
    if (packetSize <= 0) break;

    char buffer[1024];
    int len = udp.read(buffer, sizeof(buffer) - 1);
    if (len > 0) {
      buffer[len] = '\0';

      JsonDocument doc;
      DeserializationError err = deserializeJson(doc, buffer);
      if (err) {
        Serial.printf("[ESP32-ERR] JSON parse failed: %s (Len: %d, Raw: %s)\n", err.c_str(), len, buffer);
        continue;
      }

      // Check if this is an ACK handshake from PC
      if (doc["cmd"] && doc["cmd"].as<String>() == "ack") {
        if (doc["ip"]) {
          audioState.hostIP = doc["ip"].as<String>();
          Serial.printf("[ESP32-DISCOVERY] Handshake ACK received from PC at %s\n", audioState.hostIP.c_str());
        }
        continue;
      }

      // Extract telemetry tokens
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


// =============================================================================
// MAIN EXECUTION LOOP
// =============================================================================
void loop() {
  // 1. Process all incoming audio telemetry tokens over UDP
  processUDP();

  // 2. Poll navigation buttons and dispatch UDP actions if pressed
  handleButtons();

  // 3. Periodic Auto-Discovery Beacon when idle / searching for host
  bool isIdle = (millis() - audioState.lastPacketTime > 2500);
  if (isIdle && (millis() - lastPingTime > 2500)) {
    sendDiscoveryPing();
    lastPingTime = millis();
  }

  // 4. Check if PC reported a new album cover ID; if so, fetch over HTTP
  if (audioState.coverID != loadedCoverID && audioState.hostIP.length() > 0) {
    fetchAlbumCover(audioState.hostIP, audioState.coverID);
  }

  // 5. Render updated UI frame to the display
  bool isConnected = (WiFi.status() == WL_CONNECTED);
  renderFrame(audioState.volume, audioState.beat, audioState.song, isConnected);

  // 6. Yield delay to feed ESP32 RTOS watchdog timer
  delay(12);
}
