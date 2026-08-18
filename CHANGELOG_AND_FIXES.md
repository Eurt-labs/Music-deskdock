# Detailed Change Log & Fix Explanation

This document provides a complete, plain-English explanation of why the PC transmitter script (`audio_sender.py`) was failing to pass telemetry tokens or why the ESP32 (`src/main.cpp`) was unable to receive them, along with a detailed breakdown of every fix applied.

---

## 1. Executive Summary: What Went Wrong?

When you ran the system, three separate issues were working together to disrupt the connection between your computer and the ESP32:

1. **The Silent Crash on Windows (Error 10054)**:
   When your PC sent a UDP message to an IP address that wasn't immediately ready or listening, Windows marked the communication socket with an internal error. The very next time the Python script tried to listen for button presses, Windows threw a `ConnectionResetError (WinError 10054)`. Because the script didn't anticipate this specific Windows error, it crashed in the background and completely stopped sending audio data.

2. **The "Too Long" Song Title Buffer Overflow**:
   When playing songs with long titles, multiple artists, or special/Unicode characters (common on Spotify and YouTube), the message sent to the ESP32 grew larger than 384 characters. The ESP32's message buffer was limited to 384 bytes, so it cut the message in half. The ESP32's JSON reader could not parse half a message, so it threw it away silently. To the ESP32, it looked like no packets were arriving.

3. **HTTP Album Art Freezing the Audio Stream**:
   Whenever album art was being downloaded over HTTP, if the connection stalled or took too long, the ESP32 paused everything for up to 1.2 seconds. During that time, the ESP32 completely ignored incoming UDP audio packets. Even worse, if the album art failed to download on the first try, the ESP32 thought it had already downloaded it and never tried again.

4. **No Visibility / No Log File**:
   There was no logging system to record what the script was doing, making it impossible to see if data was being sent, what IP was being targeted, or why a failure occurred.

---

## 2. Detailed Breakdown of Changes

### A. Changes Made to `audio_sender.py` (PC Transmitter)

#### 1. Windows Socket Crash Fix (`WinError 10054`)
- **What was changed**: Wrapped the UDP socket reading loop with full protection against `ConnectionResetError`, `BlockingIOError`, `OSError`, and `socket.timeout`.
- **Why it matters**: Now, if the ESP32 takes a moment to connect or if an ICMP packet comes back from the router, the Python script will not crash. It simply ignores the temporary reset and keeps streaming audio telemetry without interruption.

#### 2. Automatic ESP32 Discovery (No Manual IP Typing Required)
- **What was changed**: Added listening logic that detects "heartbeat/ping" broadcast packets sent by the ESP32.
- **Why it matters**: You no longer have to manually check the screen and type the IP address every time. When you start the script, it listens for the ESP32 and binds to it automatically. Manual typing is still supported if you prefer it.

#### 3. Complete File Logging System (`music_deskdock.log`)
- **What was changed**: Built a rotating file logger using Python's `logging` system.
- **What it logs**:
  - Script startup, detected audio devices, and Windows Media (WinRT) session status.
  - Periodic telemetry tokens sent (`v` = volume, `b` = beat, `s` = song name, `cid` = cover ID, `ip` = host IP).
  - ESP32 hardware button presses received (`playpause`, `next`, `prev`).
  - HTTP requests made by the ESP32 to download album artwork.
  - Streaming rate (packets per second) and any network or audio errors.
- **File safety**: The log automatically rotates at 5 MB and keeps up to 3 backup files to prevent consuming disk space.

#### 4. Song Title Cleaning & Unicode Protection
- **What was changed**: Added `sanitize_title()` to clean non-printable characters and truncate overly long song titles to a maximum of 128 characters. Also safely encoded console output.
- **Why it matters**: Prevents huge packets that overwhelm the ESP32, and stops the Windows terminal from crashing with `UnicodeEncodeError` when playing songs in other languages (Japanese, Korean, Hindi, etc.).

#### 5. Command-Line Options
- **What was changed**: Added arguments `--esp-ip`, `--port`, `--http-port`, `--log-file`, and `--verbose`.
- **Why it matters**: You can run `python audio_sender.py --esp-ip 192.168.1.50` or `python audio_sender.py --verbose` for advanced control.

---

### B. Changes Made to `src/main.cpp` (ESP32 Firmware)

#### 1. Expanded UDP Receive Buffer (from 384B to 1024B)
- **What was changed**: Enlarged `buffer` from 384 bytes to 1024 bytes.
- **Why it matters**: Song titles of any reasonable length with full artist metadata can now be received and parsed completely without getting cut in half.

#### 2. Queue Draining & Instant Responsiveness
- **What was changed**: Updated `processUDP()` to process all incoming packets in a loop each frame.
- **Why it matters**: If packets pile up while the screen is rendering, the ESP32 drains the queue and always uses the newest audio volume and beat data. This eliminates audio visualizer lag.

#### 3. Automatic Broadcast Discovery Beacon
- **What was changed**: Added `sendDiscoveryPing()` to broadcast a message (`{"cmd": "ping", "dev": "ESP32_MusicDock", "ip": "..."}`) to the local network when waiting for audio.
- **Why it matters**: Lets the PC script find the ESP32 immediately without requiring manual configuration.

#### 4. Resilient Album Art Downloading
- **What was changed**: 
  - `loadedCoverID` is only marked as loaded if the full 32,768 bytes are downloaded with HTTP status `200 OK`.
  - Added a 3-second cooldown retry timer if an album art download fails.
- **Why it matters**: If a download gets interrupted or the server is busy, the ESP32 won't get stuck with a blank or broken image—it will smoothly retry after 3 seconds without freezing the display.

#### 5. Enhanced Serial Diagnostic Messages
- **What was changed**: Added clear Serial printouts for JSON deserialization errors, network connections, and HTTP status codes.
- **Why it matters**: Opening the PlatformIO Serial Monitor (`115200` baud) shows exactly what the ESP32 is doing in real-time.

---
