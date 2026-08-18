import math
import os
import numpy as np
from PIL import Image, ImageDraw, ImageFont

def create_animation():
    os.makedirs('assets', exist_ok=True)
    
    W, H = 840, 480
    NUM_FRAMES = 60
    FPS = 15
    DURATION = int(1000 / FPS)  # 66 ms per frame = 4.0 second relaxed, smooth loop
    
    # Fonts
    font_title = ImageFont.truetype('C:/Windows/Fonts/segoeuib.ttf', 16)
    font_sub = ImageFont.truetype('C:/Windows/Fonts/segoeui.ttf', 12)
    font_mono = ImageFont.truetype('C:/Windows/Fonts/consola.ttf', 11)
    font_mono_small = ImageFont.truetype('C:/Windows/Fonts/consola.ttf', 9)
    font_mono_bold = ImageFont.truetype('C:/Windows/Fonts/consolab.ttf', 12)
    font_badge = ImageFont.truetype('C:/Windows/Fonts/segoeuib.ttf', 11)
    font_btn = ImageFont.truetype('C:/Windows/Fonts/segoeuib.ttf', 10)
    font_lcd = ImageFont.truetype('C:/Windows/Fonts/consola.ttf', 10)

    # Natural & Neutral Palette matching main.cpp exact theme
    PALETTE = {
        'bg': (19, 21, 25),              # Deep matte charcoal
        'card': (26, 29, 36),            # Subtle card slate
        'card_border': (44, 49, 58),     # Refined border
        'device_body': (33, 37, 45),     # Deskdock chassis
        'device_border': (52, 58, 70),   # Bezel accent
        'screen_bg': (16, 20, 28),       # COLOR_BG 0x0842
        'panel_bg': (28, 33, 42),        # COLOR_DARK_GRAY 0x18C3
        'text_primary': (230, 237, 243), # COLOR_WHITE 0xFFFF
        'text_muted': (135, 145, 160),   # Muted grey
        'text_dim': (90, 98, 112),       # Dim grey
        'cyan': (93, 187, 191),          # COLOR_CYAN 0x07FF
        'magenta': (198, 120, 160),      # COLOR_MAGENTA 0xF81F
        'yellow': (229, 192, 123),       # COLOR_YELLOW 0xFFE0
        'sage_green': (138, 180, 148),   # Natural sage green
        'btn_bg': (42, 47, 56),          # Button background
        'btn_border': (58, 65, 78),      # Button border
    }

    # Pre-render vinyl cover art
    cover_128 = Image.new('RGB', (128, 128), PALETTE['screen_bg'])
    cdraw = ImageDraw.Draw(cover_128)
    for y in range(128):
        for x in range(128):
            dx = x - 64
            dy = y - 64
            dist = math.sqrt(dx * dx + dy * dy)
            if dist <= 14:
                cover_128.putpixel((x, y), PALETTE['yellow'])
            elif 18 <= dist <= 56:
                if int(dist) % 4 == 0:
                    cover_128.putpixel((x, y), (38, 44, 56))
                else:
                    cover_128.putpixel((x, y), (14, 16, 22))
    cdraw.ellipse([61, 61, 67, 67], fill=(10, 12, 16))

    song_string = "Daft Punk - Get Lucky (feat. Pharrell Williams)   "
    frames = []

    for frame_idx in range(NUM_FRAMES):
        t = frame_idx / NUM_FRAMES
        angle_rad = t * 2 * math.pi
        
        img = Image.new('RGB', (W, H), PALETTE['bg'])
        draw = ImageDraw.Draw(img)

        # 1. Main Background Card
        draw.rounded_rectangle([15, 15, W - 15, H - 15], radius=12, fill=PALETTE['card'], outline=PALETTE['card_border'], width=1)

        # Header Bar
        draw.text((36, 32), "MUSIC DESKDOCK", font=font_title, fill=PALETTE['text_primary'])
        draw.text((185, 36), "•  ESP32 & Windows WASAPI Companion", font=font_sub, fill=PALETTE['text_muted'])

        # Connection Status Badge
        badge_x, badge_y, badge_w, badge_h = W - 220, 30, 185, 24
        draw.rounded_rectangle([badge_x, badge_y, badge_x + badge_w, badge_y + badge_h], radius=6, fill=(22, 38, 30), outline=(50, 90, 65), width=1)
        pulse_r = 4 + math.sin(angle_rad * 2) * 0.8
        draw.ellipse([badge_x + 12 - pulse_r, badge_y + 12 - pulse_r, badge_x + 12 + pulse_r, badge_y + 12 + pulse_r], fill=PALETTE['sage_green'])
        draw.text((badge_x + 24, badge_y + 4), "LIVE  192.168.1.51", font=font_badge, fill=PALETTE['sage_green'])

        draw.line([35, 68, W - 35, 68], fill=PALETTE['card_border'], width=1)

        # 2. Left Side: Physical DeskDock Device Enclosure
        dev_x, dev_y, dev_w, dev_h = 35, 86, 390, 360
        draw.rounded_rectangle([dev_x, dev_y, dev_x + dev_w, dev_y + dev_h], radius=14, fill=PALETTE['device_body'], outline=PALETTE['device_border'], width=2)
        
        # Screws in corners
        for sx, sy in [(dev_x + 12, dev_y + 12), (dev_x + dev_w - 12, dev_y + 12), (dev_x + 12, dev_y + dev_h - 12), (dev_x + dev_w - 12, dev_y + dev_h - 12)]:
            draw.ellipse([sx - 3, sy - 3, sx + 3, sy + 3], fill=(24, 26, 32), outline=(55, 60, 72), width=1)

        draw.text((dev_x + 24, dev_y + 14), "ESP32 DEVKIT V1  •  ST7735 160×128 (DOUBLE-BUFFERED)", font=font_mono_small, fill=PALETTE['text_dim'])

        # 3. REAL ESP32 DISPLAY UI EMULATION (Rendered at 160x128 native, then 2x scaled)
        scr_native = Image.new('RGB', (160, 128), PALETTE['screen_bg'])
        sdraw = ImageDraw.Draw(scr_native)

        # Beat calculation (relaxed tempo: 4 beats per 60 frames = 1 beat/sec)
        beat_phase = (frame_idx % 15) / 15.0
        is_beat = beat_phase < 0.20
        beat_intensity = max(0.0, 1.0 - (beat_phase / 0.30)) if is_beat else 0.0

        # Dynamic volume (smooth natural wave)
        vol_base = 54 + 16 * math.sin(angle_rad * 2) + 6 * math.cos(angle_rad * 4)
        if is_beat:
            vol_base += 20 * beat_intensity
        volume = int(np.clip(vol_base, 0, 100))

        # --- Exact main.cpp renderFrame logic ---
        # 1. Left 128x128 Album Art
        scr_native.paste(cover_128, (0, 0))
        if is_beat:
            sdraw.rectangle([0, 0, 127, 127], outline=PALETTE['magenta'], width=1)
            sdraw.rectangle([1, 1, 126, 126], outline=PALETTE['yellow'], width=1)

        # 2. Right 32px Side Panel (X = 128 to 159)
        sdraw.rectangle([128, 0, 159, 127], fill=PALETTE['panel_bg'])
        sdraw.line([128, 0, 128, 127], fill=PALETTE['magenta'], width=1)

        # Play Symbol
        sdraw.polygon([(138, 8), (138, 18), (146, 13)], fill=PALETTE['cyan'])

        # Volume Bar (138 to 149, height maps 0-100 to 0-80)
        bar_h = int((volume / 100.0) * 80)
        bar_color = PALETTE['yellow'] if is_beat else PALETTE['cyan']
        if bar_h > 0:
            sdraw.rectangle([138, 110 - bar_h, 149, 110], fill=bar_color)
        sdraw.rectangle([138, 30, 149, 110], outline=PALETTE['text_primary'], width=1)

        # 3. Bottom Marquee Overlay (0 to 127, Y = 110 to 127)
        sdraw.rectangle([0, 110, 127, 127], fill=PALETTE['panel_bg'])
        sdraw.line([0, 110, 127, 110], fill=PALETTE['cyan'], width=1)

        char_pos = int((frame_idx / NUM_FRAMES) * len(song_string)) % len(song_string)
        disp_text = (song_string + song_string)[char_pos : char_pos + 18]
        sdraw.text((4, 114), disp_text, font=font_lcd, fill=PALETTE['text_primary'])

        # Upscale 2.1x to fit device window (336 x 268)
        scr_scaled = scr_native.resize((340, 240), Image.NEAREST)

        # Paste on chassis
        scr_x, scr_y = dev_x + 24, dev_y + 34
        draw.rounded_rectangle([scr_x - 3, scr_y - 3, scr_x + 340 + 3, scr_y + 240 + 3], radius=6, fill=(10, 11, 14), outline=(40, 44, 54), width=2)
        img.paste(scr_scaled, (scr_x, scr_y))

        # 4. Status LEDs on Chassis
        led_y = dev_y + 290
        # Blue Sync LED
        blue_color = (int(PALETTE['cyan'][0] * 0.8), int(PALETTE['cyan'][1] * 0.8), int(PALETTE['cyan'][2] * 0.8))
        draw.ellipse([dev_x + 40 - 5, led_y - 5, dev_x + 40 + 5, led_y + 5], fill=blue_color, outline=(60, 90, 110))
        draw.text((dev_x + 52, led_y - 6), "SYNC (D12)", font=font_mono_small, fill=PALETTE['text_muted'])

        # Green Beat LED
        green_val = int(255 * (0.2 + 0.8 * beat_intensity))
        green_color = (int(PALETTE['sage_green'][0] * (green_val / 255)), int(PALETTE['sage_green'][1] * (green_val / 255)), int(PALETTE['sage_green'][2] * (green_val / 255)))
        draw.ellipse([dev_x + 160 - 5, led_y - 5, dev_x + 160 + 5, led_y + 5], fill=green_color, outline=(60, 100, 70))
        draw.text((dev_x + 172, led_y - 6), "BEAT (D14)", font=font_mono_small, fill=PALETTE['text_muted'])

        # Red Idle LED
        draw.ellipse([dev_x + 280 - 5, led_y - 5, dev_x + 280 + 5, led_y + 5], fill=(60, 25, 25), outline=(90, 40, 40))
        draw.text((dev_x + 292, led_y - 6), "IDLE (D27)", font=font_mono_small, fill=PALETTE['text_dim'])

        # 5. Hardware Navigation Buttons
        btn_y = dev_y + 314
        btn_w, btn_h = 96, 32
        btns = [("PREV (D25)", dev_x + 28), ("PLAY (D26)", dev_x + 148), ("NEXT (D33)", dev_x + 268)]
        for label, bx in btns:
            draw.rounded_rectangle([bx, btn_y, bx + btn_w, btn_y + btn_h], radius=6, fill=PALETTE['btn_bg'], outline=PALETTE['btn_border'], width=1)
            draw.text((bx + 16, btn_y + 9), label, font=font_btn, fill=PALETTE['text_primary'])

        # 6. Right Side Panel: System Metrics & FFT Audio Telemetry
        side_x, side_y, side_w, side_h = 445, 86, 360, 360
        draw.rounded_rectangle([side_x, side_y, side_x + side_w, side_y + side_h], radius=12, fill=(22, 24, 29), outline=PALETTE['card_border'], width=1)

        draw.text((side_x + 20, side_y + 16), "LIVE AUDIO & TELEMETRY STREAM", font=font_badge, fill=PALETTE['cyan'])

        # FFT Audio Spectrum Box
        fft_x, fft_y, fft_w, fft_h = side_x + 20, side_y + 40, side_w - 40, 100
        draw.rounded_rectangle([fft_x, fft_y, fft_x + fft_w, fft_y + fft_h], radius=8, fill=(15, 17, 21), outline=(38, 42, 52), width=1)
        draw.text((fft_x + 12, fft_y + 8), "WASAPI Loopback FFT Spectrum (20 Hz - 16 kHz)", font=font_mono_small, fill=PALETTE['text_dim'])

        # Draw relaxed FFT spectrum bars
        num_fft = 24
        bw = (fft_w - 24) // num_fft
        for bi in range(num_fft):
            ffactor = math.exp(-bi * 0.09)
            fdyn = math.sin(angle_rad * 2 + bi * 0.4) * 0.25 + math.cos(angle_rad * 3 + bi * 0.6) * 0.15
            if bi < 5 and is_beat:
                fdyn += 0.45 * beat_intensity
            bar_height = max(6, int(58 * (ffactor * 0.7 + fdyn * 0.3)))
            bx = fft_x + 12 + bi * bw
            by = fft_y + fft_h - 12 - bar_height
            bcolor = PALETTE['yellow'] if (bi < 5 and is_beat) else PALETTE['sage_green']
            draw.rectangle([bx, by, bx + bw - 2, fft_y + fft_h - 12], fill=bcolor)

        # Key Metrics Grid
        grid_y = side_y + 154
        metrics = [
            ("RMS VOLUME", f"{volume} %", "-14.2 dBFS", PALETTE['sage_green']),
            ("BASS KICK", "TRIGGERED" if is_beat else "LISTENING", "20-140 Hz Band", PALETTE['yellow'] if is_beat else PALETTE['text_muted']),
            ("UDP TELEMETRY", "40.0 FPS", "Port 12345 (Sub-10ms)", PALETTE['cyan']),
            ("HTTP RAW COVER", "32.7 KB (RGB565)", "Port 8080 (Lossless TCP)", PALETTE['text_primary']),
        ]

        for idx, (m_title, m_val, m_sub, m_col) in enumerate(metrics):
            gx = side_x + 20 + (idx % 2) * (fft_w // 2 + 5)
            gy = grid_y + (idx // 2) * 58
            gw = fft_w // 2 - 5
            draw.rounded_rectangle([gx, gy, gx + gw, gy + 50], radius=6, fill=(17, 19, 23), outline=(35, 39, 48), width=1)
            draw.text((gx + 10, gy + 6), m_title, font=font_mono_small, fill=PALETTE['text_dim'])
            draw.text((gx + 10, gy + 18), m_val, font=font_mono_bold, fill=m_col)
            draw.text((gx + 10, gy + 34), m_sub, font=font_mono_small, fill=PALETTE['text_muted'])

        # Protocol Flow
        flow_y = side_y + 280
        draw.rounded_rectangle([side_x + 20, flow_y, side_x + side_w - 20, flow_y + 64], radius=6, fill=(15, 17, 21), outline=(35, 39, 48), width=1)
        draw.text((side_x + 30, flow_y + 8), "BIDIRECTIONAL WI-FI BRIDGE", font=font_mono_small, fill=PALETTE['text_dim'])
        draw.text((side_x + 30, flow_y + 24), "PC Host ────► UDP Telemetry & HTTP ────► ESP32", font=font_mono_small, fill=PALETTE['sage_green'])
        draw.text((side_x + 30, flow_y + 42), "ESP32   ────► Hardware Button Packet ──► PC Host", font=font_mono_small, fill=PALETTE['yellow'])

        frames.append(img)

    out_path = 'assets/deskdock_demo.gif'
    frames[0].save(out_path, save_all=True, append_images=frames[1:], duration=DURATION, loop=0, optimize=True)
    print(f"Successfully generated relaxed deskdock demo at: {out_path} ({len(frames)} frames, {DURATION}ms delay)")

if __name__ == '__main__':
    create_animation()
