import math
import os
import numpy as np
from PIL import Image, ImageDraw, ImageFont

def render_real_esp32_ui():
    os.makedirs('assets', exist_ok=True)

    # Native ST7735 dimensions
    NATIVE_W = 160
    NATIVE_H = 128
    SCALE = 4  # 4x scale -> 640 x 512 for crisp display presentation
    OUT_W = NATIVE_W * SCALE
    OUT_H = NATIVE_H * SCALE

    # 60 frames at 15 FPS = 4.0 second relaxed, smooth loop
    NUM_FRAMES = 60
    FPS = 15
    DURATION = int(1000 / FPS)  # ~66 ms per frame

    # Exact RGB values corresponding to RGB565 palette in src/main.cpp
    # (Tuned to natural & neutral tones)
    COLOR_BG = (16, 20, 28)          # 0x0842 Dark Slate background
    COLOR_CYAN = (93, 187, 191)       # 0x07FF Muted Cyan
    COLOR_MAGENTA = (198, 120, 160)   # 0xF81F Soft Magenta
    COLOR_YELLOW = (229, 192, 123)    # 0xFFE0 Warm Amber/Gold
    COLOR_WHITE = (230, 237, 243)     # 0xFFFF Crisp Linen White
    COLOR_DARK_GRAY = (28, 33, 42)    # 0x18C3 Dark Grey panel
    COLOR_GROOVE = (38, 44, 56)       # Vinyl groove lines

    # Try loading a clean font for the 18-char marquee
    try:
        font_marquee = ImageFont.truetype('C:/Windows/Fonts/consola.ttf', 9)
    except Exception:
        font_marquee = ImageFont.load_default()

    # Pre-generate default 128x128 cover art buffer (from drawDefaultCover in main.cpp)
    cover_img = Image.new('RGB', (128, 128), COLOR_BG)
    cover_draw = ImageDraw.Draw(cover_img)
    
    # Render vinyl disc with realistic grooves
    for y in range(128):
        for x in range(128):
            dx = x - 64
            dy = y - 64
            dist_sq = dx * dx + dy * dy
            dist = math.sqrt(dist_sq)

            if dist <= 14:
                cover_img.putpixel((x, y), COLOR_YELLOW)
            elif 18 <= dist <= 56:
                if int(dist) % 4 == 0:
                    cover_img.putpixel((x, y), COLOR_GROOVE)
                else:
                    cover_img.putpixel((x, y), (14, 16, 22))

    # Center spindle hole
    cover_draw.ellipse([61, 61, 67, 67], fill=(10, 12, 16))

    song_string = "Daft Punk - Get Lucky (feat. Pharrell Williams)   "
    
    frames = []

    # 4 beats over 60 frames = relaxed ~60-70 BPM tempo (1 beat every 15 frames = 1.0s)
    for frame_idx in range(NUM_FRAMES):
        t = frame_idx / NUM_FRAMES
        angle_rad = t * 2 * math.pi
        
        # 1. Allocate native 160x128 canvas (mimicking GFXcanvas16)
        native_canvas = Image.new('RGB', (NATIVE_W, NATIVE_H), COLOR_BG)
        draw = ImageDraw.Draw(native_canvas)

        # Beat detection: smooth attack and natural decay
        beat_phase = (frame_idx % 15) / 15.0
        is_beat = beat_phase < 0.20
        beat_intensity = max(0.0, 1.0 - (beat_phase / 0.30)) if is_beat else 0.0

        # Dynamic volume calculation (calm sine waves + beat bump)
        vol_base = 52 + 18 * math.sin(angle_rad * 2) + 8 * math.cos(angle_rad * 4)
        if is_beat:
            vol_base += 20 * beat_intensity
        volume = int(np.clip(vol_base, 0, 100))

        # --- 1. LEFT 128x128 ALBUM COVER ART ---
        # Paste cover buffer at (0, 0)
        native_canvas.paste(cover_img, (0, 0))

        # On beat: draw pulsing neon borders
        if is_beat:
            # Outer magenta rect at (0, 0, 127, 127)
            draw.rectangle([0, 0, 127, 127], outline=COLOR_MAGENTA, width=1)
            # Inner yellow rect at (1, 1, 126, 126)
            draw.rectangle([1, 1, 126, 126], outline=COLOR_YELLOW, width=1)

        # --- 2. RIGHT 32-PIXEL SIDE CONTROL PANEL (X = 128 to 159) ---
        draw.rectangle([128, 0, 159, 127], fill=COLOR_DARK_GRAY)
        # Vertical separator line at X = 128
        draw.line([128, 0, 128, 127], fill=COLOR_MAGENTA, width=1)

        # Play / Pause Icon at (138, 8)
        # Small play triangle in Cyan
        draw.polygon([(138, 8), (138, 18), (146, 13)], fill=COLOR_CYAN)

        # Audio Volume Bar Visualizer
        # map(volume, 0, 100, 0, 80)
        bar_h = int((volume / 100.0) * 80)
        bar_color = COLOR_YELLOW if is_beat else COLOR_CYAN
        
        # Volume fill from (138, 110 - bar_h) to (149, 110)
        if bar_h > 0:
            draw.rectangle([138, 110 - bar_h, 149, 110], fill=bar_color)
            
        # Volume border container: (138, 30, 149, 110)
        draw.rectangle([138, 30, 149, 110], outline=COLOR_WHITE, width=1)

        # --- 3. BOTTOM SCROLLING MARQUEE OVERLAY ---
        # Marquee strip: (0, 110, 127, 127)
        draw.rectangle([0, 110, 127, 127], fill=COLOR_DARK_GRAY)
        # Horizontal Cyan divider line at y = 110
        draw.line([0, 110, 127, 110], fill=COLOR_CYAN, width=1)

        # Marquee text scroll step (relaxed smooth scrolling)
        char_pos = int((frame_idx / NUM_FRAMES) * len(song_string)) % len(song_string)
        extended = song_string + song_string
        disp_text = extended[char_pos : char_pos + 18]
        draw.text((4, 114), disp_text, font=font_marquee, fill=COLOR_WHITE)

        # --- 4. UPSCALE NATIVE FRAME TO HIGH RESOLUTION ---
        # Scale 4x using nearest neighbor for authentic, sharp LCD pixel structure
        upscaled = native_canvas.resize((OUT_W, OUT_H), Image.NEAREST)

        # Wrap inside a sleek display bezel canvas (680 x 550)
        bezel_w, bezel_h = OUT_W + 40, OUT_H + 40
        frame_canvas = Image.new('RGB', (bezel_w, bezel_h), (20, 23, 30))
        fdraw = ImageDraw.Draw(frame_canvas)

        # Bezel body
        fdraw.rounded_rectangle([6, 6, bezel_w - 6, bezel_h - 6], radius=10, fill=(12, 14, 18), outline=(42, 48, 60), width=2)
        # Paste LCD screen in center
        frame_canvas.paste(upscaled, (20, 20))
        # Inner screen border
        fdraw.rectangle([19, 19, 20 + OUT_W, 20 + OUT_H], outline=(30, 35, 45), width=1)

        frames.append(frame_canvas)

    # Save realistic display animation GIF
    out_path = 'assets/esp32_display_demo.gif'
    frames[0].save(
        out_path,
        save_all=True,
        append_images=frames[1:],
        duration=DURATION,
        loop=0,
        optimize=True
    )
    print(f"Successfully generated real ESP32 display demo at: {out_path} ({len(frames)} frames, {DURATION}ms delay)")

if __name__ == '__main__':
    render_real_esp32_ui()
