"""
ESP32 Music Visualizer & Hardware Media Controller - PC Host Transmitter
========================================================================

This script runs on the host Windows PC to bridge your music playback with the ESP32.

How It Works:
-------------
1. Audio Loopback Capture:
   Uses the `soundcard` library (WASAPI backend) to capture desktop audio directly 
   from the default output device (speakers/headphones) without needing virtual audio cables.

2. Audio Analysis (Volume & Bass Beat Detection):
   - RMS (Root Mean Square) is calculated to determine overall volume (0-100 scale).
   - Real Fast Fourier Transform (RFFT) with a Hanning window isolates bass frequencies
     between 20 Hz and 140 Hz (kick drum / bassline).
   - An adaptive rolling average detects sudden bass energy spikes above a threshold,
     triggering a beat event.

3. Media Metadata & Album Art Extraction:
   - Uses the Windows Runtime (WinRT) `GlobalSystemMediaTransportControlsSessionManager`
     to fetch current song title, artist, and album thumbnail from Spotify, YouTube, 
     Chrome/Edge, Apple Music, VLC, etc.
   - Converts the thumbnail into a 128x128 16-bit RGB565 raw byte array (Big Endian) 
     for direct SPI LCD rendering on the ESP32.

4. Network Communication:
   - UDP (Port 12345): Streams real-time telemetry (volume, beat flag, song title, cover ID) 
     to the ESP32 at ~40 FPS with minimal latency. Also receives button commands from the ESP32.
   - HTTP (Port 8080): Serves the 32 KB raw RGB565 cover image (`/cover.raw`) to the ESP32 
     over TCP to ensure reliable, lossless image downloads without UDP packet fragmentation.

5. Hardware Media Controls:
   - When the ESP32 sends a UDP button command ("playpause", "next", "prev"), this script
     triggers the action via WinRT or falls back to simulating Windows media keyboard events.
"""

import asyncio
import ctypes
from http.server import BaseHTTPRequestHandler, HTTPServer
import hashlib
import io
import json
import socket
import sys
import threading
import time

import numpy as np
from PIL import Image
import soundcard as sc

# WinRT is used to interact with Windows 10/11 Media Transport Controls.
# If unavailable (e.g. non-Windows platform), the script falls back gracefully.
try:
    from winrt.windows.media.control import (
        GlobalSystemMediaTransportControlsSessionManager as MediaManager,
    )
    from winrt.windows.storage.streams import DataReader
    WINRT_AVAILABLE = True
except Exception:
    WINRT_AVAILABLE = False


# ==============================================================================
# NETWORK & PORT CONFIGURATION
# ==============================================================================
UDP_PORT = 12345   # Port used for low-latency audio telemetry and ESP32 button events
HTTP_PORT = 8080   # Port used to serve raw 32 KB RGB565 album cover images


# ==============================================================================
# SHARED APPLICATION STATE
# ==============================================================================
current_song_title = "No Song Playing"
cover_id = 0
current_cover_bytes = b'\x00' * 32768  # 128x128 pixels * 2 bytes per pixel = 32,768 bytes


# ==============================================================================
# HTTP IMAGE SERVER (PORT 8080)
# ==============================================================================
class CoverHTTPRequestHandler(BaseHTTPRequestHandler):
    """
    Lightweight HTTP handler serving the current album artwork in raw RGB565 format.
    
    Why HTTP instead of UDP for images?
    - A 128x128 16-bit image is 32,768 bytes.
    - UDP packets have a standard MTU of ~1500 bytes. Splitting 32 KB across UDP
      requires custom chunking, sequence numbering, and retransmission logic.
    - HTTP over TCP handles flow control, retransmission, and packet assembly natively,
      allowing the ESP32 to download the complete 32 KB image in ~50-100 ms.
    """

    def do_GET(self):
        if self.path == '/cover.raw':
            self.send_response(200)
            self.send_header('Content-Type', 'application/octet-stream')
            self.send_header('Content-Length', str(len(current_cover_bytes)))
            self.send_header('Cache-Control', 'no-cache')
            self.end_headers()
            self.wfile.write(current_cover_bytes)
        else:
            self.send_error(404, "File Not Found")

    def log_message(self, format, *args):
        # Suppress routine HTTP request logs to keep terminal output clean
        pass


def start_http_server():
    """Starts the HTTP server daemon on all local network interfaces."""
    server = HTTPServer(('0.0.0.0', HTTP_PORT), CoverHTTPRequestHandler)
    server.serve_forever()


# ==============================================================================
# IMAGE PROCESSING & RGB565 CONVERSION
# ==============================================================================
def convert_img_to_rgb565(img: Image.Image) -> bytes:
    """
    Converts a PIL Image into a 128x128 16-bit RGB565 byte array in Big Endian order.
    
    RGB565 Bit Layout (16 bits per pixel):
    - Red:   5 bits  (bits 11..15) -> input 8-bit shifted right by 3
    - Green: 6 bits  (bits 5..10)  -> input 8-bit shifted right by 2
    - Blue:  5 bits  (bits 0..4)   -> input 8-bit shifted right by 3
    
    Big Endian byte order is required by the ST7735 TFT controller SPI interface.
    """
    img = img.convert('RGB').resize((128, 128))
    arr = np.array(img, dtype=np.uint16)
    
    # Quantize 8-bit color channels to 5-bit, 6-bit, 5-bit
    r5 = (arr[:, :, 0] >> 3).astype(np.uint16)
    g6 = (arr[:, :, 1] >> 2).astype(np.uint16)
    b5 = (arr[:, :, 2] >> 3).astype(np.uint16)
    
    # Combine channels into 16-bit integer
    rgb565 = (r5 << 11) | (g6 << 5) | b5
    
    # Swap high and low bytes for big-endian SPI transmission
    rgb565_be = ((rgb565 & 0xFF00) >> 8) | ((rgb565 & 0x00FF) << 8)
    return rgb565_be.astype('>u2').tobytes()


def make_default_cover() -> bytes:
    """
    Generates a default retro vinyl record graphic when no album art is available.
    Renders concentric circular grooved rings with a gold center hub.
    """
    img = Image.new('RGB', (128, 128), color=(15, 20, 35))
    arr = np.array(img)
    y, x = np.ogrid[:128, :128]
    dist_sq = (x - 64)**2 + (y - 64)**2
    
    # Outer vinyl disc body (magenta ring)
    outer_mask = (dist_sq <= 50**2) & (dist_sq >= 15**2)
    arr[outer_mask] = [240, 40, 140]
    
    # Inner center spindle hub (gold yellow)
    center_mask = (dist_sq < 15**2)
    arr[center_mask] = [255, 220, 40]
    
    return convert_img_to_rgb565(Image.fromarray(arr))


# Initialize cover buffer with default graphic
current_cover_bytes = make_default_cover()


# ==============================================================================
# HARDWARE MEDIA CONTROLS HANDLER
# ==============================================================================
def handle_media_control(cmd: str):
    """
    Executes playback actions received from ESP32 physical buttons.
    
    Tries the official Windows Media Transport Controls Session API first.
    If unavailable, falls back to Windows virtual media key events via user32.dll:
    - 0xB0: VK_MEDIA_NEXT_TRACK
    - 0xB1: VK_MEDIA_PREV_TRACK
    - 0xB3: VK_MEDIA_PLAY_PAUSE
    """
    async def _async_cmd():
        if WINRT_AVAILABLE:
            try:
                sessions = await MediaManager.request_async()
                session = sessions.get_current_session()
                if session:
                    if cmd == 'playpause':
                        await session.try_toggle_play_pause_async()
                    elif cmd == 'next':
                        await session.try_skip_next_async()
                    elif cmd == 'prev':
                        await session.try_skip_previous_async()
                    return
            except Exception:
                pass

        # Fallback using Windows API virtual key events
        key_map = {'next': 0xB0, 'prev': 0xB1, 'playpause': 0xB3}
        if cmd in key_map:
            vk = key_map[cmd]
            # Key down (0) followed by Key up (KEYEVENTF_KEYUP = 2)
            ctypes.windll.user32.keybd_event(vk, 0, 0, 0)
            ctypes.windll.user32.keybd_event(vk, 0, 2, 0)

    try:
        loop = asyncio.new_event_loop()
        loop.run_until_complete(_async_cmd())
    except Exception as e:
        print(f"Error handling media command '{cmd}': {e}")


# ==============================================================================
# BACKGROUND MEDIA METADATA & COVER FETCHER
# ==============================================================================
def media_title_fetcher():
    """
    Background worker thread that periodically polls Windows Media Controls.
    
    Checks for:
    - Changes in song title / artist.
    - Changes in album art thumbnail stream (detected via SHA-256 hash comparison).
    - Automatically updates global state and increments `cover_id` to notify the ESP32.
    """
    global current_song_title, cover_id, current_cover_bytes
    if not WINRT_AVAILABLE:
        current_song_title = "Audio Playing"
        return

    last_fetched_title = ""
    last_thumb_hash = ""

    async def _async_poll():
        nonlocal last_fetched_title, last_thumb_hash
        global current_song_title, cover_id, current_cover_bytes
        
        while True:
            try:
                sessions = await MediaManager.request_async()
                session = sessions.get_current_session()
                
                if session:
                    info = await session.try_get_media_properties_async()
                    title = info.title.strip() if info and info.title else ""
                    artist = info.artist.strip() if info and info.artist else ""
                    
                    if title and artist:
                        new_title = f"{artist} - {title}"
                    elif title:
                        new_title = title
                    else:
                        new_title = "Playing Audio"

                    current_song_title = new_title
                    
                    thumb_bytes = None
                    thumb_hash = ""

                    # Extract thumbnail image stream if provided by the active media player
                    if info.thumbnail:
                        try:
                            stream = await info.thumbnail.open_read_async()
                            size = stream.size
                            if size > 0:
                                reader = DataReader(stream)
                                await reader.load_async(size)
                                buf = reader.read_buffer(size)
                                raw_stream = bytes(buf)
                                
                                # Use SHA-256 hash to detect when artwork changes across tracks
                                thumb_hash = hashlib.sha256(raw_stream).hexdigest()
                                pil_img = Image.open(io.BytesIO(raw_stream))
                                thumb_bytes = convert_img_to_rgb565(pil_img)
                        except Exception:
                            thumb_bytes = None

                    # If title or artwork changed, update the active cover buffer
                    if new_title != last_fetched_title or (thumb_hash and thumb_hash != last_thumb_hash):
                        if thumb_bytes is not None:
                            current_cover_bytes = thumb_bytes
                            cover_id += 1
                            last_fetched_title = new_title
                            last_thumb_hash = thumb_hash
                            print(f"\n[METADATA] New Track: {new_title} (Cover ID: {cover_id})")
                        else:
                            if new_title != last_fetched_title:
                                current_cover_bytes = make_default_cover()
                                cover_id += 1
                                last_fetched_title = new_title
                else:
                    current_song_title = "No Song Playing"
                    if last_fetched_title != "No Song Playing":
                        last_fetched_title = "No Song Playing"
                        last_thumb_hash = ""
                        current_cover_bytes = make_default_cover()
                        cover_id += 1
            except Exception:
                pass
                
            await asyncio.sleep(0.6)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(_async_poll())


# ==============================================================================
# NETWORK & AUDIO DEVICE HELPERS
# ==============================================================================
def get_local_ip_to_target(target_ip: str) -> str:
    """
    Determines the local network IP address on the interface routing to `target_ip`.
    This ensures the ESP32 is given the correct IP to download `/cover.raw` from.
    """
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect((target_ip, UDP_PORT))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "192.168.1.100"


def get_loopback_microphone():
    """
    Finds and returns the WASAPI loopback audio input matching the default speaker.
    Allows capturing desktop audio in real time without external cables.
    """
    try:
        default_speaker = sc.default_speaker()
        loopback_mic = sc.get_microphone(id=str(default_speaker.id), include_loopback=True)
        return default_speaker.name, loopback_mic
    except Exception:
        mics = sc.all_microphones(include_loopback=True)
        for mic in mics:
            if mic.isloopback:
                return mic.name, mic
        raise RuntimeError("No loopback audio device found! Please ensure audio output is active.")


def prompt_esp32_ip() -> str:
    """Prompts the user for the ESP32 IP address displayed on its screen at boot."""
    print("\n=======================================================")
    print("   ESP32 Music Visualizer & Media Controller Host     ")
    print("=======================================================")
    esp_ip = input("Enter ESP32 IP Address (from TFT boot screen): ").strip()
    if not esp_ip:
        esp_ip = "192.168.1.51"
    return esp_ip


# ==============================================================================
# MAIN APPLICATION LOOP
# ==============================================================================
def main():
    esp_ip = prompt_esp32_ip()
    local_ip = get_local_ip_to_target(esp_ip)
    print(f"Host PC IP: {local_ip}  -->  ESP32 Target: {esp_ip}:{UDP_PORT}")

    # 1. Start HTTP Server daemon thread for cover art delivery
    http_thread = threading.Thread(target=start_http_server, daemon=True)
    http_thread.start()

    # 2. Start Windows Media session polling daemon thread
    media_thread = threading.Thread(target=media_title_fetcher, daemon=True)
    media_thread.start()

    # 3. Initialize UDP socket for fast audio telemetry & incoming button events
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(('0.0.0.0', UDP_PORT))
    sock.settimeout(0.001)  # Non-blocking read timeout (1 ms)

    # 4. Initialize WASAPI desktop audio loopback
    try:
        spk_name, loopback_mic = get_loopback_microphone()
        print(f"Capturing loopback audio from: {spk_name}")
    except Exception as e:
        print(f"Error initializing audio device: {e}")
        return

    sample_rate = 44100
    block_size = 1024

    # Beat detection state variables
    bass_history = []
    beat_threshold_factor = 1.30  # Bass energy must exceed 130% of rolling average
    beat_cooldown = 0            # Cooldown frame counter to prevent double-triggering
    
    print("\n[ACTIVE] Streaming audio telemetry & listening for ESP32 hardware buttons...")
    print("Press Ctrl+C to stop.\n")

    try:
        with loopback_mic.recorder(samplerate=sample_rate, blocksize=block_size) as mic:
            while True:
                # -------------------------------------------------------------
                # Step A: Check for incoming button commands from ESP32
                # -------------------------------------------------------------
                try:
                    data, addr = sock.recvfrom(512)
                    if data:
                        msg = json.loads(data.decode('utf-8'))
                        if "cmd" in msg:
                            cmd = msg["cmd"]
                            print(f"\n[HARDWARE BUTTON] Action triggered: {cmd}")
                            handle_media_control(cmd)
                except (socket.timeout, BlockingIOError, json.JSONDecodeError):
                    pass

                # -------------------------------------------------------------
                # Step B: Record audio block & compute mono channel
                # -------------------------------------------------------------
                data = mic.record(numframes=block_size)
                audio_mono = np.mean(data, axis=1)

                # -------------------------------------------------------------
                # Step C: RMS Volume Calculation (mapped to 0-100 scale)
                # -------------------------------------------------------------
                rms = np.sqrt(np.mean(audio_mono ** 2))
                if rms > 1e-5:
                    db = 20 * np.log10(rms)
                    vol = int(np.clip((db + 50) * 2, 0, 100))
                else:
                    vol = 0

                # -------------------------------------------------------------
                # Step D: FFT Frequency Analysis & Bass Kick Beat Detection
                # -------------------------------------------------------------
                # Apply Hanning window to minimize spectral leakage before FFT
                windowed_audio = audio_mono * np.hanning(len(audio_mono))
                fft_vals = np.abs(np.fft.rfft(windowed_audio))
                freqs = np.fft.rfftfreq(len(audio_mono), 1.0 / sample_rate)

                # Sum spectral energy in the 20 Hz - 140 Hz kick drum range
                bass_mask = (freqs >= 20) & (freqs <= 140)
                bass_energy = np.sum(fft_vals[bass_mask])
                
                # Maintain rolling history of recent bass energy (last 25 frames ~0.58s)
                bass_history.append(bass_energy)
                if len(bass_history) > 25:
                    bass_history.pop(0)

                avg_bass = np.mean(bass_history) if len(bass_history) > 0 else 1.0
                
                # Check for beat spike
                is_beat = 0
                if beat_cooldown > 0:
                    beat_cooldown -= 1
                elif bass_energy > (avg_bass * beat_threshold_factor) and vol > 12:
                    is_beat = 1
                    beat_cooldown = 3  # Prevent re-triggering for next 3 frames

                # -------------------------------------------------------------
                # Step E: Send Telemetry Packet to ESP32 over UDP
                # -------------------------------------------------------------
                packet = {
                    "v": vol,                   # Volume level (0-100)
                    "b": is_beat,               # Beat trigger flag (0 or 1)
                    "s": current_song_title,    # Current track title and artist
                    "cid": cover_id,            # Cover version ID
                    "ip": local_ip              # Host PC local IP for HTTP cover downloads
                }

                json_payload = json.dumps(packet)
                sock.sendto(json_payload.encode('utf-8'), (esp_ip, UDP_PORT))

                # -------------------------------------------------------------
                # Step F: Terminal Status Display
                # -------------------------------------------------------------
                bar_len = int(vol / 5)
                meter = "█" * bar_len + "░" * (20 - bar_len)
                beat_str = " [ BEAT! ] " if is_beat else "           "
                song_disp = (current_song_title[:24] + '..') if len(current_song_title) > 24 else current_song_title
                sys.stdout.write(f"\rVol: [{meter}] {vol:3d}% {beat_str} Cover ID: {cover_id:<3} Song: {song_disp:<26}")
                sys.stdout.flush()

    except KeyboardInterrupt:
        print("\n\nTransmission stopped by user.")
    except Exception as e:
        print(f"\nError in audio transmission loop: {e}")


if __name__ == "__main__":
    main()

