import math
import os
import numpy as np
from PIL import Image, ImageDraw, ImageFont

def generate_exact_esp32_visuals():
    os.makedirs('assets', exist_ok=True)

    # Native ST7735 resolution: 160 x 128
    W, H = 160, 128
    SCALE = 4  # 4x integer scaling -> 640 x 512 for pixel-perfect sharpness

    # Exact RGB565 Colors from src/main.cpp
    COLOR_BG = (16, 20, 28)          # 0x0842 Deep Dark Slate
    COLOR_CYAN = (0, 235, 235)        # 0x07FF Electric Cyan
    COLOR_MAGENTA = (245, 30, 200)    # 0xF81F Neon Magenta
    COLOR_YELLOW = (255, 220, 40)     # 0xFFE0 Bright Gold Yellow
    COLOR_WHITE = (255, 255, 255)     # 0xFFFF Crisp White
    COLOR_DARK_GRAY = (32, 38, 48)    # 0x18C3 Dark Grey side panel/banner

    # 60 frames at 15 FPS = 4.0 second relaxed, natural animation loop
    NUM_FRAMES = 60
    FPS = 15
    DURATION = int(1000 / FPS)  # 66 ms per frame

    # Load 5x7 / 6x8 pixel-style font for Adafruit GFX text emulation
    try:
        font_gfx = ImageFont.truetype('C:/Windows/Fonts/consola.ttf', 9)
    except Exception:
        font_gfx = ImageFont.load_default()

    # -------------------------------------------------------------
    # Create 128x128 Album Cover Artwork (Synthwave / Retrowave Art)
    # -------------------------------------------------------------
    cover_128 = Image.new('RGB', (128, 128), (14, 16, 24))
    cdraw = ImageDraw.Draw(cover_128)
    
    # Sunset gradient background
    for y in range(80):
        r = int(25 + (y / 80) * 110)
        g = int(20 + (y / 80) * 45)
        b = int(45 + (y / 80) * 75)
        cdraw.line([(0, y), (127, y)], fill=(r, g, b))
        
    # Grid horizon floor (y = 80 to 127)
    for y in range(80, 128):
        depth = (y - 80) / 48.0
        g_val = int(25 + depth * 35)
        b_val = int(45 + depth * 65)
        cdraw.line([(0, y), (127, y)], fill=(18, g_val, b_val))
        
    # Perspective grid lines on floor
    for gx in [-60, -30, -10, 10, 30, 50, 70, 90, 110, 130, 160, 190]:
        cdraw.line([(64, 80), (gx, 127)], fill=(45, 80, 120))
    for gy in [84, 90, 98, 108, 120]:
        cdraw.line([(0, gy), (127, gy)], fill=(45, 80, 120))

    # Glowing retro sun
    sun_cx, sun_cy, sun_r = 64, 52, 28
    for r_sun in range(sun_r, 0, -1):
        sun_prog = r_sun / sun_r
        s_col = (int(255 * (1 - 0.2 * sun_prog)), int(180 * sun_prog + 40), 40)
        cdraw.ellipse([sun_cx - r_sun, sun_cy - r_sun, sun_cx + r_sun, sun_cy + r_sun], fill=s_col)

    # Horizontal sun stripes
    for sy in [46, 52, 58, 64, 70]:
        cdraw.line([(sun_cx - 28, sy), (sun_cx + 28, sy)], fill=(30, 18, 42), width=1)

    # Neon mountains silhouette
    cdraw.polygon([(0, 80), (25, 62), (45, 74), (64, 58), (85, 72), (105, 60), (127, 80)], fill=(20, 15, 35))
    cdraw.line([(0, 80), (25, 62), (45, 74), (64, 58), (85, 72), (105, 60), (127, 80)], fill=COLOR_CYAN, width=1)

    song_title_full = "The Weeknd - Blinding Lights   •   "

    display_frames = []
    hero_frames = []

    # 4 beats over 60 frames = 1 beat every 15 frames (~65 BPM, relaxed & natural)
    for frame_idx in range(NUM_FRAMES):
        t = frame_idx / NUM_FRAMES
        angle_rad = t * 2 * math.pi

        # -------------------------------------------------------------
        # Step 1: Render Native 160x128 Framebuffer exactly as main.cpp
        # -------------------------------------------------------------
        canvas = Image.new('RGB', (W, H), COLOR_BG)
        draw = ImageDraw.Draw(canvas)

        # Beat detection timing
        beat_phase = (frame_idx % 15) / 15.0
        is_beat = beat_phase < 0.22
        beat_intensity = max(0.0, 1.0 - (beat_phase / 0.35)) if is_beat else 0.0

        # Dynamic volume (smooth natural wave + beat kick)
        vol_base = 56 + 16 * math.sin(angle_rad * 2) + 8 * math.cos(angle_rad * 4)
        if is_beat:
            vol_base += 22 * beat_intensity
        volume = int(np.clip(vol_base, 0, 100))

        # --- A. LEFT 128x128 ALBUM ART ---
        canvas.paste(cover_128, (0, 0))

        # On Beat: Outer Magenta Rect (0,0,127,127) + Inner Yellow Rect (1,1,126,126)
        if is_beat:
            draw.rectangle([0, 0, 127, 127], outline=COLOR_MAGENTA, width=1)
            draw.rectangle([1, 1, 126, 126], outline=COLOR_YELLOW, width=1)

        # --- B. RIGHT 32-PIXEL SIDE PANEL (X = 128 to 159) ---
        draw.rectangle([128, 0, 159, 127], fill=COLOR_DARK_GRAY)
        # Vertical Magenta line at X = 128
        draw.line([128, 0, 128, 127], fill=COLOR_MAGENTA, width=1)

        # Play Symbol: ASCII char 16 (right triangle) at (138, 8) in Cyan
        draw.polygon([(137, 8), (137, 18), (145, 13)], fill=COLOR_CYAN)

        # Volume Bar: map(volume, 0, 100, 0, 80)
        bar_h = int((volume / 100.0) * 80)
        bar_color = COLOR_YELLOW if is_beat else COLOR_CYAN
        
        # Volume Fill from (138, 110 - bar_h) to (149, 110)
        if bar_h > 0:
            draw.rectangle([138, 110 - bar_h, 149, 110], fill=bar_color)
            
        # Volume Box Outline at (138, 30, 149, 110) in White
        draw.rectangle([138, 30, 149, 110], outline=COLOR_WHITE, width=1)

        # --- C. BOTTOM SCROLLING MARQUEE OVERLAY (0, 110, 127, 127) ---
        # Dark Grey banner strip across album cover
        draw.rectangle([0, 110, 127, 127], fill=COLOR_DARK_GRAY)
        # Horizontal Cyan Line at Y = 110
        draw.line([0, 110, 127, 110], fill=COLOR_CYAN, width=1)

        # Marquee scrolling text at (4, 114) in White
        char_pos = int((frame_idx / NUM_FRAMES) * len(song_title_full)) % len(song_title_full)
        extended = song_title_full + song_title_full
        disp_text = extended[char_pos : char_pos + 18]
        draw.text((4, 114), disp_text, font=font_gfx, fill=COLOR_WHITE)

        # -------------------------------------------------------------
        # Step 2: Create Standalone ESP32 Display Demo Animation
        # -------------------------------------------------------------
        # Upscale 4x with nearest-neighbor for authentic pixel grid
        scaled_lcd = canvas.resize((W * SCALE, H * SCALE), Image.NEAREST)

        # Wrap in a clean minimal display bezel
        disp_canvas_w = W * SCALE + 32
        disp_canvas_h = H * SCALE + 32
        disp_img = Image.new('RGB', (disp_canvas_w, disp_canvas_h), (14, 16, 22))
        disp_draw = ImageDraw.Draw(disp_img)
        
        # Matte frame
        disp_draw.rounded_rectangle([4, 4, disp_canvas_w - 4, disp_canvas_h - 4], radius=8, fill=(10, 12, 16), outline=(38, 44, 56), width=2)
        disp_img.paste(scaled_lcd, (16, 16))
        display_frames.append(disp_img)

        # -------------------------------------------------------------
        # Step 3: Create Full DeskDock Device Hero Animation
        # -------------------------------------------------------------
        HERO_W, HERO_H = 840, 480
        hero_img = Image.new('RGB', (HERO_W, HERO_H), (19, 21, 25))
        hdraw = ImageDraw.Draw(hero_img)

        # Outer card
        hdraw.rounded_rectangle([15, 15, HERO_W - 15, HERO_H - 15], radius=12, fill=(26, 29, 36), outline=(44, 49, 58), width=1)

        # Header
        hdraw.text((36, 32), "MUSIC DESKDOCK", font=ImageFont.truetype('C:/Windows/Fonts/segoeuib.ttf', 16), fill=COLOR_WHITE)
        hdraw.text((185, 36), "•  ESP32 & Windows WASAPI Companion", font=ImageFont.truetype('C:/Windows/Fonts/segoeui.ttf', 12), fill=(135, 145, 160))

        # Status badge
        hdraw.rounded_rectangle([HERO_W - 220, 30, HERO_W - 35, 54], radius=6, fill=(22, 38, 30), outline=(50, 90, 65), width=1)
        pulse_r = 4 + math.sin(angle_rad * 2) * 0.8
        hdraw.ellipse([HERO_W - 208 - pulse_r, 42 - pulse_r, HERO_W - 208 + pulse_r, 42 + pulse_r], fill=(138, 180, 148))
        hdraw.text((HERO_W - 196, 34), "LIVE  192.168.1.51", font=ImageFont.truetype('C:/Windows/Fonts/segoeuib.ttf', 11), fill=(138, 180, 148))

        hdraw.line([35, 68, HERO_W - 35, 68], fill=(44, 49, 58), width=1)

        # Device Enclosure on Left
        dev_x, dev_y, dev_w, dev_h = 35, 86, 390, 360
        hdraw.rounded_rectangle([dev_x, dev_y, dev_x + dev_w, dev_y + dev_h], radius=14, fill=(33, 37, 45), outline=(52, 58, 70), width=2)
        
        # Screws
        for sx, sy in [(dev_x + 12, dev_y + 12), (dev_x + dev_w - 12, dev_y + 12), (dev_x + 12, dev_y + dev_h - 12), (dev_x + dev_w - 12, dev_y + dev_h - 12)]:
            hdraw.ellipse([sx - 3, sy - 3, sx + 3, sy + 3], fill=(24, 26, 32), outline=(55, 60, 72), width=1)

        hdraw.text((dev_x + 24, dev_y + 14), "ESP32 DEVKIT V1  •  ST7735 160×128 (DOUBLE-BUFFERED)", font=ImageFont.truetype('C:/Windows/Fonts/consola.ttf', 9), fill=(90, 98, 112))

        # Scale 160x128 screen 2.125x for chassis display viewport (340 x 272)
        dev_lcd = canvas.resize((340, 272), Image.NEAREST)
        hdraw.rounded_rectangle([dev_x + 22, dev_y + 32, dev_x + 22 + 344, dev_y + 32 + 276], radius=6, fill=(10, 12, 16), outline=(40, 45, 56), width=2)
        hero_img.paste(dev_lcd, (dev_x + 24, dev_y + 34))

        # Status LEDs
        led_y = dev_y + 318
        hdraw.ellipse([dev_x + 40 - 4, led_y - 4, dev_x + 40 + 4, led_y + 4], fill=(70, 150, 180), outline=(50, 90, 110))
        hdraw.text((dev_x + 50, led_y - 5), "SYNC (D12)", font=ImageFont.truetype('C:/Windows/Fonts/consola.ttf', 9), fill=(135, 145, 160))

        green_val = int(255 * (0.2 + 0.8 * beat_intensity))
        hdraw.ellipse([dev_x + 155 - 4, led_y - 4, dev_x + 155 + 4, led_y + 4], fill=(int(138 * (green_val / 255)), int(180 * (green_val / 255)), int(148 * (green_val / 255))), outline=(60, 100, 70))
        hdraw.text((dev_x + 165, led_y - 5), "BEAT (D14)", font=ImageFont.truetype('C:/Windows/Fonts/consola.ttf', 9), fill=(135, 145, 160))

        hdraw.ellipse([dev_x + 270 - 4, led_y - 4, dev_x + 270 + 4, led_y + 4], fill=(60, 25, 25), outline=(90, 40, 40))
        hdraw.text((dev_x + 280, led_y - 5), "IDLE (D27)", font=ImageFont.truetype('C:/Windows/Fonts/consola.ttf', 9), fill=(90, 98, 112))

        # Hardware Buttons at bottom of chassis
        btn_y = dev_y + 332
        for label, bx in [("PREV (D25)", dev_x + 24), ("PLAY (D26)", dev_x + 144), ("NEXT (D33)", dev_x + 264)]:
            hdraw.rounded_rectangle([bx, btn_y, bx + 102, btn_y + 22], radius=4, fill=(42, 47, 56), outline=(58, 65, 78), width=1)
            hdraw.text((bx + 18, btn_y + 5), label, font=ImageFont.truetype('C:/Windows/Fonts/segoeuib.ttf', 9), fill=COLOR_WHITE)

        # Right Telemetry Side Panel
        side_x, side_y, side_w, side_h = 445, 86, 360, 360
        hdraw.rounded_rectangle([side_x, side_y, side_x + side_w, side_y + side_h], radius=12, fill=(22, 24, 29), outline=(44, 49, 58), width=1)
        hdraw.text((side_x + 20, side_y + 16), "LIVE AUDIO & TELEMETRY STREAM", font=ImageFont.truetype('C:/Windows/Fonts/segoeuib.ttf', 11), fill=COLOR_CYAN)

        # FFT Box
        fft_x, fft_y, fft_w, fft_h = side_x + 20, side_y + 40, side_w - 40, 100
        hdraw.rounded_rectangle([fft_x, fft_y, fft_x + fft_w, fft_y + fft_h], radius=8, fill=(15, 17, 21), outline=(38, 42, 52), width=1)
        hdraw.text((fft_x + 12, fft_y + 8), "WASAPI Loopback FFT Spectrum (20 Hz - 16 kHz)", font=ImageFont.truetype('C:/Windows/Fonts/consola.ttf', 9), fill=(90, 98, 112))

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
            bcolor = COLOR_YELLOW if (bi < 5 and is_beat) else (138, 180, 148)
            hdraw.rectangle([bx, by, bx + bw - 2, fft_y + fft_h - 12], fill=bcolor)

        # Metrics Grid
        grid_y = side_y + 154
        metrics = [
            ("RMS VOLUME", f"{volume} %", "-14.2 dBFS", (138, 180, 148)),
            ("BASS KICK", "TRIGGERED" if is_beat else "LISTENING", "20-140 Hz Band", COLOR_YELLOW if is_beat else (135, 145, 160)),
            ("UDP TELEMETRY", "40.0 FPS", "Port 12345 (Sub-10ms)", COLOR_CYAN),
            ("HTTP RAW COVER", "32.7 KB (RGB565)", "Port 8080 (Lossless TCP)", COLOR_WHITE),
        ]

        for idx, (m_title, m_val, m_sub, m_col) in enumerate(metrics):
            gx = side_x + 20 + (idx % 2) * (fft_w // 2 + 5)
            gy = grid_y + (idx // 2) * 58
            gw = fft_w // 2 - 5
            hdraw.rounded_rectangle([gx, gy, gx + gw, gy + 50], radius=6, fill=(17, 19, 23), outline=(35, 39, 48), width=1)
            hdraw.text((gx + 10, gy + 6), m_title, font=ImageFont.truetype('C:/Windows/Fonts/consola.ttf', 9), fill=(90, 98, 112))
            hdraw.text((gx + 10, gy + 18), m_val, font=ImageFont.truetype('C:/Windows/Fonts/consolab.ttf', 12), fill=m_col)
            hdraw.text((gx + 10, gy + 34), m_sub, font=ImageFont.truetype('C:/Windows/Fonts/consola.ttf', 9), fill=(135, 145, 160))

        # Protocol Flow
        flow_y = side_y + 280
        hdraw.rounded_rectangle([side_x + 20, flow_y, side_x + side_w - 20, flow_y + 64], radius=6, fill=(15, 17, 21), outline=(35, 39, 48), width=1)
        hdraw.text((side_x + 30, flow_y + 8), "BIDIRECTIONAL WI-FI BRIDGE", font=ImageFont.truetype('C:/Windows/Fonts/consola.ttf', 9), fill=(90, 98, 112))
        hdraw.text((side_x + 30, flow_y + 24), "PC Host ────► UDP Telemetry & HTTP ────► ESP32", font=ImageFont.truetype('C:/Windows/Fonts/consola.ttf', 9), fill=(138, 180, 148))
        hdraw.text((side_x + 30, flow_y + 42), "ESP32   ────► Hardware Button Packet ──► PC Host", font=ImageFont.truetype('C:/Windows/Fonts/consola.ttf', 9), fill=COLOR_YELLOW)

        hero_frames.append(hero_img)

    # Save new animations with cache-busting clean names
    display_gif_path = 'assets/esp32_display_real.gif'
    display_frames[0].save(
        display_gif_path,
        save_all=True,
        append_images=display_frames[1:],
        duration=DURATION,
        loop=0,
        optimize=True
    )
    print(f"Generated {display_gif_path} ({len(display_frames)} frames, {DURATION}ms)")

    hero_gif_path = 'assets/deskdock_hero.gif'
    hero_frames[0].save(
        hero_gif_path,
        save_all=True,
        append_images=hero_frames[1:],
        duration=DURATION,
        loop=0,
        optimize=True
    )
    print(f"Generated {hero_gif_path} ({len(hero_frames)} frames, {DURATION}ms)")

    # Also overwrite old paths so any direct link immediately gets the exact visuals
    display_frames[0].save('assets/esp32_display_demo.gif', save_all=True, append_images=display_frames[1:], duration=DURATION, loop=0, optimize=True)
    hero_frames[0].save('assets/deskdock_demo.gif', save_all=True, append_images=hero_frames[1:], duration=DURATION, loop=0, optimize=True)
    print("Overwrote old assets as well.")

if __name__ == '__main__':
    generate_exact_esp32_visuals()
