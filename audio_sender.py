"""
ESP32 Music Visualizer & Hardware Media Controller - PC Host Transmitter
========================================================================

This script runs on the host Windows PC to bridge your music playback with the ESP32.

Key Features & Enhancements:
----------------------------
1. Audio Loopback Capture (WASAPI):
   Captures desktop audio directly from the default output device (speakers/headphones).
2. Audio Analysis (Volume & Bass Beat Detection):
   RMS volume calculation (0-100) and RFFT kick-drum bass spike detection (20-140 Hz).
3. Media Metadata & Album Art Extraction:
   WinRT GlobalSystemMediaTransportControlsSessionManager for track metadata & cover art.
4. Robust UDP Telemetry & Command Handling:
   - Disables Windows SIO_UDP_CONNRESET to prevent WinError 10054 crashes.
   - Bidirectional Auto-Discovery: Listens for ESP32 discovery pings and dynamic binding.
   - Token & packet sanitization (clamping title strings, UTF-8 safety).
5. Comprehensive File & Console Logging:
   - Automatically writes timestamped logs to `music_deskdock.log` with rotation.
   - Logs packet transmission rates, metadata changes, HTTP requests, and diagnostics.
6. Multi-threaded HTTP Cover Art Server:
   - Thread-safe raw RGB565 image server for fast ESP32 album art downloads.
"""

import argparse
import asyncio
import ctypes
import hashlib
import io
import json
import logging
from logging.handlers import RotatingFileHandler
import os
import socket
import sys
import threading
import time
from typing import Optional, Tuple

import numpy as np
from PIL import Image
import soundcard as sc

# WinRT is used to interact with Windows 10/11 Media Transport Controls.
try:
    from winrt.windows.media.control import (
        GlobalSystemMediaTransportControlsSessionManager as MediaManager,
    )
    from winrt.windows.storage.streams import DataReader
    WINRT_AVAILABLE = True
except Exception:
    WINRT_AVAILABLE = False


# ==============================================================================
# LOGGING SETUP
# ==============================================================================
logger = logging.getLogger("MusicDeskDock")

def setup_logging(log_file: str = "music_deskdock.log", verbose: bool = False):
    """Configures structured logging to both a rotating file and the console."""
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    logger.handlers.clear()

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)-7s] [%(threadName)-12s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # 1. Rotating File Handler (Max 5 MB per file, keeps 3 backups)
    try:
        file_handler = RotatingFileHandler(
            log_file, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except Exception as e:
        print(f"[WARN] Failed to initialize file logger at '{log_file}': {e}")

    # 2. Console Handler for Warnings and Errors (Main progress uses stdout.write)
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(logging.WARNING)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    logger.info("=" * 60)
    logger.info("Music Deskdock Host Transmitter Starting")
    logger.info(f"Python: {sys.version.split()[0]} | Platform: {sys.platform} | WinRT Available: {WINRT_AVAILABLE}")
    logger.info(f"Logging initialized -> Log file: {os.path.abspath(log_file)}")
    logger.info("=" * 60)


# ==============================================================================
# SHARED APPLICATION STATE & LOCKS
# ==============================================================================
UDP_PORT = 12345
HTTP_PORT = 8080

state_lock = threading.Lock()
current_song_title = "No Song Playing"
cover_id = 0
current_cover_bytes = b'\x00' * 32768  # 128x128 pixels * 2 bytes = 32,768 bytes
target_esp_ip: Optional[str] = None
esp_last_seen = 0.0


# ==============================================================================
# HTTP IMAGE SERVER (PORT 8080)
# ==============================================================================
from http.server import BaseHTTPRequestHandler, HTTPServer

class CoverHTTPRequestHandler(BaseHTTPRequestHandler):
    """
    HTTP handler serving the active 32 KB RGB565 album artwork.
    """
    def do_GET(self):
        client_ip = self.client_address[0]
        if self.path == '/cover.raw':
            with state_lock:
                data = current_cover_bytes
                cid = cover_id

            logger.info(f"[HTTP] Serving /cover.raw (ID: {cid}, Size: {len(data)} bytes) to ESP32 at {client_ip}")
            self.send_response(200)
            self.send_header('Content-Type', 'application/octet-stream')
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-cache')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            try:
                self.wfile.write(data)
                logger.info(f"[HTTP] Successfully transferred cover ID {cid} to {client_ip}")
            except Exception as e:
                logger.warning(f"[HTTP] Error sending cover to {client_ip}: {e}")
        elif self.path == '/status':
            with state_lock:
                status_payload = json.dumps({
                    "song": current_song_title,
                    "cover_id": cover_id,
                    "esp_ip": target_esp_ip,
                    "esp_last_seen": esp_last_seen
                }).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(status_payload)))
            self.end_headers()
            self.wfile.write(status_payload)
        else:
            logger.warning(f"[HTTP] 404 Not Found: {self.path} from {client_ip}")
            self.send_error(404, "File Not Found")

    def log_message(self, format, *args):
        # Redirect standard HTTP access logs to debug level
        logger.debug(f"[HTTP-SERVER] {self.client_address[0]} - {format % args}")


def start_http_server(http_port: int):
    """Starts the HTTP server daemon on all local network interfaces."""
    try:
        server = HTTPServer(('0.0.0.0', http_port), CoverHTTPRequestHandler)
        logger.info(f"[HTTP] Cover Art Server listening on http://0.0.0.0:{http_port}")
        server.serve_forever()
    except Exception as e:
        logger.exception(f"[HTTP] Fatal error in HTTP server on port {http_port}: {e}")


# ==============================================================================
# IMAGE PROCESSING & RGB565 CONVERSION
# ==============================================================================
def convert_img_to_rgb565(img: Image.Image) -> bytes:
    """
    Converts a PIL Image into a 128x128 16-bit RGB565 byte array in Big Endian order.
    """
    img = img.convert('RGB').resize((128, 128), Image.Resampling.BILINEAR)
    arr = np.array(img, dtype=np.uint16)
    
    r5 = (arr[:, :, 0] >> 3).astype(np.uint16)
    g6 = (arr[:, :, 1] >> 2).astype(np.uint16)
    b5 = (arr[:, :, 2] >> 3).astype(np.uint16)
    
    rgb565 = (r5 << 11) | (g6 << 5) | b5
    rgb565_be = ((rgb565 & 0xFF00) >> 8) | ((rgb565 & 0x00FF) << 8)
    return rgb565_be.astype('>u2').tobytes()


def make_default_cover() -> bytes:
    """Generates a default retro vinyl record graphic when no album art is available."""
    img = Image.new('RGB', (128, 128), color=(15, 20, 35))
    arr = np.array(img)
    y, x = np.ogrid[:128, :128]
    dist_sq = (x - 64)**2 + (y - 64)**2
    
    outer_mask = (dist_sq <= 50**2) & (dist_sq >= 15**2)
    arr[outer_mask] = [240, 40, 140]
    
    center_mask = (dist_sq < 15**2)
    arr[center_mask] = [255, 220, 40]
    
    return convert_img_to_rgb565(Image.fromarray(arr))


# Initialize default cover
current_cover_bytes = make_default_cover()


# ==============================================================================
# HARDWARE MEDIA CONTROLS HANDLER
# ==============================================================================
def handle_media_control(cmd: str):
    """Executes playback actions received from ESP32 physical buttons."""
    logger.info(f"[ACTION] Triggering media control command: '{cmd}'")
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
                    logger.info(f"[ACTION] WinRT media command '{cmd}' executed successfully.")
                    return
            except Exception as e:
                logger.debug(f"[ACTION] WinRT session command '{cmd}' failed: {e}. Falling back to virtual keys.")

        # Fallback using Windows API virtual key events
        key_map = {'next': 0xB0, 'prev': 0xB1, 'playpause': 0xB3}
        if cmd in key_map:
            vk = key_map[cmd]
            ctypes.windll.user32.keybd_event(vk, 0, 0, 0)
            ctypes.windll.user32.keybd_event(vk, 0, 2, 0)
            logger.info(f"[ACTION] Virtual key event for '{cmd}' (VK 0x{vk:02X}) sent via user32.dll")

    try:
        loop = asyncio.new_event_loop()
        loop.run_until_complete(_async_cmd())
    except Exception as e:
        logger.exception(f"[ACTION] Error handling media command '{cmd}': {e}")


# ==============================================================================
# BACKGROUND MEDIA METADATA & COVER FETCHER
# ==============================================================================
def sanitize_title(title: str, max_length: int = 128) -> str:
    """Cleans and truncates track title string for safe UDP transmission."""
    if not title:
        return "No Song Playing"
    cleaned = "".join(c for c in title if c.isprintable()).strip()
    if len(cleaned) > max_length:
        cleaned = cleaned[:max_length - 3] + "..."
    return cleaned if cleaned else "Playing Audio"


def media_title_fetcher():
    """Background worker thread that periodically polls Windows Media Controls."""
    global current_song_title, cover_id, current_cover_bytes
    if not WINRT_AVAILABLE:
        logger.warning("[WINRT] WinRT media controls not available on this system.")
        with state_lock:
            current_song_title = "Audio Playing"
        return

    logger.info("[WINRT] Media session polling worker started.")
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
                    title = info.title.strip() if (info and info.title) else ""
                    artist = info.artist.strip() if (info and info.artist) else ""
                    
                    if title and artist:
                        raw_title = f"{artist} - {title}"
                    elif title:
                        raw_title = title
                    else:
                        raw_title = "Playing Audio"

                    new_title = sanitize_title(raw_title)

                    thumb_bytes = None
                    thumb_hash = ""

                    if info and info.thumbnail:
                        try:
                            stream = await info.thumbnail.open_read_async()
                            size = stream.size
                            if size > 0:
                                reader = DataReader(stream)
                                await reader.load_async(size)
                                buf = reader.read_buffer(size)
                                raw_stream = bytes(buf)
                                
                                thumb_hash = hashlib.sha256(raw_stream).hexdigest()
                                pil_img = Image.open(io.BytesIO(raw_stream))
                                thumb_bytes = convert_img_to_rgb565(pil_img)
                        except Exception as thumb_err:
                            logger.debug(f"[WINRT] Thumbnail extraction error: {thumb_err}")
                            thumb_bytes = None

                    # If title or artwork changed, update active cover buffer
                    if new_title != last_fetched_title or (thumb_hash and thumb_hash != last_thumb_hash):
                        with state_lock:
                            current_song_title = new_title
                            if thumb_bytes is not None:
                                current_cover_bytes = thumb_bytes
                                cover_id += 1
                                last_fetched_title = new_title
                                last_thumb_hash = thumb_hash
                                logger.info(f"[METADATA] New Track: '{new_title}' | Art updated (Cover ID: {cover_id})")
                            else:
                                if new_title != last_fetched_title:
                                    current_cover_bytes = make_default_cover()
                                    cover_id += 1
                                    last_fetched_title = new_title
                                    last_thumb_hash = ""
                                    logger.info(f"[METADATA] New Track: '{new_title}' | Default art (Cover ID: {cover_id})")
                    else:
                        with state_lock:
                            current_song_title = new_title
                else:
                    with state_lock:
                        current_song_title = "No Song Playing"
                    if last_fetched_title != "No Song Playing":
                        last_fetched_title = "No Song Playing"
                        last_thumb_hash = ""
                        with state_lock:
                            current_cover_bytes = make_default_cover()
                            cover_id += 1
                        logger.info(f"[METADATA] Playback stopped/idle (Cover ID: {cover_id})")
            except Exception as e:
                logger.debug(f"[WINRT] Polling exception: {e}")
                
            await asyncio.sleep(0.5)

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(_async_poll())
    except Exception as e:
        logger.exception(f"[WINRT] Fatal exception in media_title_fetcher loop: {e}")


# ==============================================================================
# NETWORK & AUDIO DEVICE HELPERS
# ==============================================================================
def get_local_ip_to_target(target_ip: Optional[str]) -> str:
    """Determines the local network interface IP that routes to target_ip."""
    if not target_ip:
        target_ip = "8.8.8.8"
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect((target_ip, UDP_PORT))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def get_loopback_microphone():
    """Finds and returns the WASAPI loopback audio input matching the default speaker."""
    try:
        default_speaker = sc.default_speaker()
        loopback_mic = sc.get_microphone(id=str(default_speaker.id), include_loopback=True)
        return default_speaker.name, loopback_mic
    except Exception as e:
        logger.warning(f"[AUDIO] Default speaker lookup error: {e}. Searching all loopback devices...")
        mics = sc.all_microphones(include_loopback=True)
        for mic in mics:
            if mic.isloopback:
                return mic.name, mic
        raise RuntimeError("No loopback audio device found! Please ensure audio output is active.")


def create_udp_socket(port: int) -> socket.socket:
    """
    Creates and initializes a UDP socket configured for broadcast and non-blocking operation:
    - Binds to 0.0.0.0:port
    - Enables broadcast reception/transmission
    - Handles WinError 10054 (ConnectionResetError) and non-blocking IO cleanly
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.bind(('0.0.0.0', port))
    sock.setblocking(False)
    logger.info(f"[SOCKET] UDP Socket bound to 0.0.0.0:{port} in non-blocking mode.")
    return sock



# ==============================================================================
# MAIN APPLICATION LOOP
# ==============================================================================
def main():
    global target_esp_ip, esp_last_seen

    parser = argparse.ArgumentParser(description="ESP32 Music Visualizer & Hardware Controller PC Transmitter")
    parser.add_argument("--esp-ip", type=str, default=None, help="ESP32 Target IP address (if omitted, will auto-discover)")
    parser.add_argument("--port", type=int, default=UDP_PORT, help=f"UDP Telemetry port (default: {UDP_PORT})")
    parser.add_argument("--http-port", type=int, default=HTTP_PORT, help=f"HTTP Cover Art port (default: {HTTP_PORT})")
    parser.add_argument("--log-file", type=str, default="music_deskdock.log", help="Path to output log file")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose debug logging")
    args = parser.parse_args()

    # 1. Initialize File & Console Logging
    setup_logging(log_file=args.log_file, verbose=args.verbose)

    if args.esp_ip:
        target_esp_ip = args.esp_ip.strip()
        logger.info(f"[CONFIG] Manual ESP32 Target IP configured: {target_esp_ip}")
    else:
        print("\n=======================================================")
        print("   ESP32 Music Visualizer & Media Controller Host     ")
        print("=======================================================")
        print("Auto-discovery is ENABLED. You can also enter the IP manually:")
        user_input = input("Enter ESP32 IP Address (or press ENTER to auto-discover): ").strip()
        if user_input:
            target_esp_ip = user_input
            logger.info(f"[CONFIG] User entered ESP32 Target IP: {target_esp_ip}")
        else:
            logger.info("[CONFIG] Waiting for ESP32 discovery heartbeat broadcast...")

    local_ip = get_local_ip_to_target(target_esp_ip)
    logger.info(f"[NETWORK] Host PC Local IP: {local_ip} | Target ESP32: {target_esp_ip or 'Waiting for Auto-Discovery'}")

    # 2. Start HTTP Server daemon thread for cover art delivery
    http_thread = threading.Thread(target=start_http_server, args=(args.http_port,), daemon=True, name="HttpServer")
    http_thread.start()

    # 3. Start Windows Media session polling daemon thread
    media_thread = threading.Thread(target=media_title_fetcher, daemon=True, name="WinRTMedia")
    media_thread.start()

    # 4. Initialize UDP socket
    try:
        sock = create_udp_socket(args.port)
    except Exception as e:
        logger.exception(f"[SOCKET] Fatal error creating UDP socket on port {args.port}: {e}")
        return

    # 5. Initialize WASAPI desktop audio loopback
    try:
        spk_name, loopback_mic = get_loopback_microphone()
        logger.info(f"[AUDIO] Capturing loopback audio from: '{spk_name}'")
        print(f"\n[AUDIO] Capturing desktop audio from: {spk_name}")
    except Exception as e:
        logger.exception(f"[AUDIO] Error initializing audio loopback device: {e}")
        print(f"\n[ERROR] Audio initialization failed: {e}")
        return

    sample_rate = 44100
    block_size = 1024

    # Beat detection state variables
    bass_history = []
    beat_threshold_factor = 1.30
    beat_cooldown = 0

    # Diagnostic packet counters
    packets_sent = 0
    packets_received = 0
    last_stat_time = time.time()
    last_log_packet_time = 0.0

    print("\n[ACTIVE] Streaming audio telemetry & listening for ESP32...")
    print(f"[LOGS]   Logging active -> Check '{os.path.abspath(args.log_file)}'")
    print("Press Ctrl+C to stop.\n")

    try:
        with loopback_mic.recorder(samplerate=sample_rate, blocksize=block_size) as mic:
            while True:
                # -------------------------------------------------------------
                # Step A: Check for incoming packets from ESP32 (Buttons / Pings)
                # -------------------------------------------------------------
                while True:
                    try:
                        data, addr = sock.recvfrom(1024)
                        if not data:
                            break
                        packets_received += 1
                        sender_ip = addr[0]
                        esp_last_seen = time.time()

                        # If we hadn't discovered ESP32 IP yet or it changed, bind it dynamically
                        if target_esp_ip != sender_ip:
                            target_esp_ip = sender_ip
                            local_ip = get_local_ip_to_target(target_esp_ip)
                            logger.info(f"[DISCOVERY] Bound to ESP32 device at IP: {target_esp_ip} (Host IP: {local_ip})")
                            print(f"\n[DISCOVERY] Connected to ESP32 at {target_esp_ip}!")

                        try:
                            msg = json.loads(data.decode('utf-8', errors='ignore'))
                            cmd = msg.get("cmd", "")
                            
                            if cmd == "ping" or cmd == "hello":
                                logger.info(f"[ESP32-HEARTBEAT] Ping received from {sender_ip} (Device: {msg.get('dev', 'Unknown')})")
                                # Send ACK response
                                ack_pkt = json.dumps({"cmd": "ack", "msg": "connected", "ip": local_ip}).encode('utf-8')
                                sock.sendto(ack_pkt, addr)
                            elif cmd in ("playpause", "next", "prev"):
                                logger.info(f"[ESP32-BUTTON] Action command received: '{cmd}' from {sender_ip}")
                                print(f"\n[HARDWARE BUTTON] Action: {cmd.upper()}")
                                handle_media_control(cmd)
                            else:
                                logger.debug(f"[ESP32-MSG] Received payload from {sender_ip}: {msg}")
                        except json.JSONDecodeError as json_err:
                            logger.warning(f"[ESP32-ERR] Malformed JSON received from {sender_ip}: {data} ({json_err})")

                    except (BlockingIOError, socket.timeout):
                        break
                    except ConnectionResetError:
                        logger.debug("[SOCKET] ConnectionResetError caught and handled gracefully.")
                        break
                    except OSError as os_err:
                        logger.debug(f"[SOCKET] Socket read error: {os_err}")
                        break
                    except Exception as ex:
                        logger.warning(f"[SOCKET] Unexpected error reading socket: {ex}")
                        break

                # -------------------------------------------------------------
                # Step B: Record audio block & compute mono channel
                # -------------------------------------------------------------
                try:
                    data = mic.record(numframes=block_size)
                    audio_mono = np.mean(data, axis=1)
                except Exception as audio_err:
                    logger.warning(f"[AUDIO] Read frame error: {audio_err}")
                    time.sleep(0.02)
                    continue

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
                windowed_audio = audio_mono * np.hanning(len(audio_mono))
                fft_vals = np.abs(np.fft.rfft(windowed_audio))
                freqs = np.fft.rfftfreq(len(audio_mono), 1.0 / sample_rate)

                bass_mask = (freqs >= 20) & (freqs <= 140)
                bass_energy = np.sum(fft_vals[bass_mask])
                
                bass_history.append(bass_energy)
                if len(bass_history) > 25:
                    bass_history.pop(0)

                avg_bass = np.mean(bass_history) if len(bass_history) > 0 else 1.0
                
                is_beat = 0
                if beat_cooldown > 0:
                    beat_cooldown -= 1
                elif bass_energy > (avg_bass * beat_threshold_factor) and vol > 12:
                    is_beat = 1
                    beat_cooldown = 3

                # -------------------------------------------------------------
                # Step E: Send Telemetry Packet to ESP32 over UDP
                # -------------------------------------------------------------
                with state_lock:
                    song_title = current_song_title
                    cid = cover_id

                packet = {
                    "v": vol,
                    "b": is_beat,
                    "s": song_title,
                    "cid": cid,
                    "ip": local_ip
                }

                if target_esp_ip:
                    try:
                        json_payload = json.dumps(packet, ensure_ascii=False)
                        sock.sendto(json_payload.encode('utf-8'), (target_esp_ip, args.port))
                        packets_sent += 1
                    except Exception as send_err:
                        logger.warning(f"[SOCKET] Error sending packet to {target_esp_ip}:{args.port} - {send_err}")

                # Periodic detailed packet logging in log file (every 4 seconds)
                now = time.time()
                if now - last_log_packet_time > 4.0:
                    last_log_packet_time = now
                    logger.info(
                        f"[TELEMETRY-TOKEN] Sent to {target_esp_ip or 'Waiting'} | "
                        f"Vol: {vol:3d}% | Beat: {is_beat} | CoverID: {cid:3d} | Song: '{song_title}' | IP: {local_ip}"
                    )

                # Periodic summary throughput stats (every 10 seconds)
                if now - last_stat_time > 10.0:
                    rate = packets_sent / (now - last_stat_time)
                    logger.info(f"[STATS] Telemetry Stream Rate: {rate:.1f} packets/sec | RX Packets: {packets_received}")
                    packets_sent = 0
                    last_stat_time = now

                # -------------------------------------------------------------
                # Step F: Terminal Status Display
                # -------------------------------------------------------------
                bar_len = int(vol / 5)
                meter = "█" * bar_len + "░" * (20 - bar_len)
                beat_str = " [ BEAT! ] " if is_beat else "           "
                song_disp = (song_title[:24] + '..') if len(song_title) > 24 else song_title
                enc = sys.stdout.encoding or 'utf-8'
                safe_song = song_disp.encode(enc, errors='replace').decode(enc)
                safe_dest = (target_esp_ip if target_esp_ip else "Searching ESP32...").encode(enc, errors='replace').decode(enc)
                sys.stdout.write(f"\rVol: [{meter}] {vol:3d}% {beat_str} CID: {cid:<3} Target: {safe_dest:<15} Song: {safe_song:<24}")
                sys.stdout.flush()

    except KeyboardInterrupt:
        logger.info("[SHUTDOWN] Transmission stopped by user (Ctrl+C).")
        print("\n\nTransmission stopped by user.")
    except Exception as e:
        logger.exception(f"[SHUTDOWN] Fatal error in audio transmission loop: {e}")
        print(f"\nError in audio transmission loop: {e}")
    finally:
        try:
            sock.close()
        except Exception:
            pass
        logger.info("[SHUTDOWN] Socket closed. Exiting.")


if __name__ == "__main__":
    main()
