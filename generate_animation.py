import math
import os
import numpy as np
from PIL import Image, ImageDraw, ImageFont

def create_animation():
    os.makedirs('assets', exist_ok=True)
    
    W, H = 840, 480
    NUM_FRAMES = 60
    FPS = 20
    DURATION = int(1000 / FPS)  # 50 ms per frame = 3.0 second seamless loop
    
    # Fonts from Windows system directory
    font_title = ImageFont.truetype('C:/Windows/Fonts/segoeuib.ttf', 16)
    font_sub = ImageFont.truetype('C:/Windows/Fonts/segoeui.ttf', 12)
    font_mono = ImageFont.truetype('C:/Windows/Fonts/consola.ttf', 12)
    font_mono_small = ImageFont.truetype('C:/Windows/Fonts/consola.ttf', 10)
    font_mono_bold = ImageFont.truetype('C:/Windows/Fonts/consolab.ttf', 12)
    font_badge = ImageFont.truetype('C:/Windows/Fonts/segoeuib.ttf', 11)
    font_btn = ImageFont.truetype('C:/Windows/Fonts/segoeuib.ttf', 10)
    font_lcd = ImageFont.truetype('C:/Windows/Fonts/segoeuib.ttf', 11)

    # Natural & Neutral Color Palette
    PALETTE = {
        'bg': (19, 21, 25),              # Deep matte charcoal
        'card': (27, 30, 36),            # Subtle card slate
        'card_border': (44, 49, 58),     # Refined border
        'device_body': (34, 38, 46),     # Deskdock chassis
        'device_border': (52, 58, 70),   # Bezel accent
        'screen_bg': (14, 16, 20),       # ST7735 black/slate
        'panel_bg': (22, 25, 31),        # Screen side panel
        'text_primary': (230, 235, 242), # Warm linen white
        'text_muted': (135, 145, 160),   # Muted cool grey
        'text_dim': (90, 98, 112),       # Dim grey
        'sage_green': (138, 180, 148),   # Natural sage green
        'sage_light': (168, 206, 178),   # Soft mint highlight
        'warm_amber': (218, 165, 105),   # Warm amber / gold
        'slate_blue': (115, 160, 205),   # Muted slate blue
        'terracotta': (205, 115, 115),   # Soft muted red
        'btn_bg': (42, 47, 56),          # Button background
        'btn_border': (60, 68, 80),      # Button border
    }

    frames = []

    # Precalculate song text for marquee
    song_title = "Daft Punk - Get Lucky (feat. Pharrell Williams)   •   Album: Random Access Memories   •   "

    for frame_idx in range(NUM_FRAMES):
        t = frame_idx / NUM_FRAMES
        angle_rad = t * 2 * math.pi
        
        # Base canvas
        img = Image.new('RGB', (W, H), PALETTE['bg'])
        draw = ImageDraw.Draw(img)

        # -------------------------------------------------------------
        # 1. Main Background Card with subtle rounded corners & border
        # -------------------------------------------------------------
        draw.rounded_rectangle([15, 15, W - 15, H - 15], radius=12, fill=PALETTE['card'], outline=PALETTE['card_border'], width=1)

        # Header Bar
        draw.text((36, 32), "MUSIC DESKDOCK", font=font_title, fill=PALETTE['text_primary'])
        draw.text((185, 36), "•  ESP32 & Windows WASAPI Companion", font=font_sub, fill=PALETTE['text_muted'])

        # Connection Status Badge
        badge_x, badge_y, badge_w, badge_h = W - 220, 30, 185, 24
        draw.rounded_rectangle([badge_x, badge_y, badge_x + badge_w, badge_y + badge_h], radius=6, fill=(22, 38, 30), outline=(50, 90, 65), width=1)
        # Pulsing green dot
        pulse_r = 4 + math.sin(angle_rad * 2) * 1.0
        draw.ellipse([badge_x + 12 - pulse_r, badge_y + 12 - pulse_r, badge_x + 12 + pulse_r, badge_y + 12 + pulse_r], fill=PALETTE['sage_light'])
        draw.text((badge_x + 24, badge_y + 4), "LIVE  192.168.1.51", font=font_badge, fill=PALETTE['sage_light'])

        # Divider line
        draw.line([35, 68, W - 35, 68], fill=PALETTE['card_border'], width=1)

        # -------------------------------------------------------------
        # 2. Left Side: Physical DeskDock Device Enclosure
        # -------------------------------------------------------------
        dev_x, dev_y, dev_w, dev_h = 35, 86, 390, 360
        # Device outer chassis with rounded corners
        draw.rounded_rectangle([dev_x, dev_y, dev_x + dev_w, dev_y + dev_h], radius=14, fill=PALETTE['device_body'], outline=PALETTE['device_border'], width=2)
        
        # Subtle screws in 4 corners of chassis
        for sx, sy in [(dev_x + 12, dev_y + 12), (dev_x + dev_w - 12, dev_y + 12), (dev_x + 12, dev_y + dev_h - 12), (dev_x + dev_w - 12, dev_y + dev_h - 12)]:
            draw.ellipse([sx - 3, sy - 3, sx + 3, sy + 3], fill=(24, 26, 32), outline=(55, 60, 72), width=1)
            draw.line([sx - 2, sy, sx + 2, sy], fill=(70, 76, 90), width=1)

        # Top Device Branding / Header
        draw.text((dev_x + 24, dev_y + 14), "ESP32 DEVKIT V1  •  ST7735 160×128", font=font_mono_small, fill=PALETTE['text_dim'])

        # -------------------------------------------------------------
        # 3. ST7735 Screen Emulation (Scaled to 342 x 240)
        # -------------------------------------------------------------
        scr_x, scr_y, scr_w, scr_h = dev_x + 24, dev_y + 34, 342, 240
        draw.rounded_rectangle([scr_x - 3, scr_y - 3, scr_x + scr_w + 3, scr_y + scr_h + 3], radius=6, fill=(10, 11, 14), outline=(40, 44, 54), width=2)
        draw.rectangle([scr_x, scr_y, scr_x + scr_w, scr_y + scr_h], fill=PALETTE['screen_bg'])

        # Beat detection timing (beats every ~0.75s => 4 beats in 60 frames)
        beat_phase = (frame_idx % 15) / 15.0
        is_beat = beat_phase < 0.25
        beat_intensity = max(0.0, 1.0 - (beat_phase / 0.35)) if is_beat else 0.0

        # Screen Division: Left 256px = Album Cover, Right 86px = Visualizer Side Panel
        cover_w = 256
        cover_rect = [scr_x, scr_y, scr_x + cover_w, scr_y + scr_h]

        # Draw spinning vinyl record art
        vinyl_cx = scr_x + cover_w // 2
        vinyl_cy = scr_y + (scr_h - 32) // 2
        spin_angle = angle_rad * 3

        # Vinyl outer grooved disc rings
        for r_disc in [90, 80, 70, 60, 50, 40]:
            c_val = int(22 + (r_disc % 20) * 0.8)
            draw.ellipse([vinyl_cx - r_disc, vinyl_cy - r_disc, vinyl_cx + r_disc, vinyl_cy + r_disc], fill=(c_val, c_val + 2, c_val + 5), outline=(32, 36, 45), width=1)

        # Vinyl center label (warm amber)
        label_r = 30
        draw.ellipse([vinyl_cx - label_r, vinyl_cy - label_r, vinyl_cx + label_r, vinyl_cy + label_r], fill=(160, 110, 60), outline=PALETTE['warm_amber'], width=1)
        # Center spindle hole
        draw.ellipse([vinyl_cx - 6, vinyl_cy - 6, vinyl_cx + 6, vinyl_cy + 6], fill=(14, 16, 20))

        # Grooved reflection highlight
        for h_off in [-0.4, 0.4]:
            h_ang = spin_angle + h_off
            hx1 = vinyl_cx + math.cos(h_ang) * 35
            hy1 = vinyl_cy + math.sin(h_ang) * 35
            hx2 = vinyl_cx + math.cos(h_ang) * 85
            hy2 = vinyl_cy + math.sin(h_ang) * 85
            draw.line([hx1, hy1, hx2, hy2], fill=(60, 70, 85), width=2)

        # Pulsing Beat Frame on album cover (Warm Amber & Sage)
        if beat_intensity > 0.05:
            b_color = (
                int(PALETTE['warm_amber'][0] * beat_intensity + PALETTE['screen_bg'][0] * (1 - beat_intensity)),
                int(PALETTE['warm_amber'][1] * beat_intensity + PALETTE['screen_bg'][1] * (1 - beat_intensity)),
                int(PALETTE['warm_amber'][2] * beat_intensity + PALETTE['screen_bg'][2] * (1 - beat_intensity)),
            )
            draw.rectangle([scr_x + 1, scr_y + 1, scr_x + cover_w - 1, scr_y + scr_h - 33], outline=b_color, width=2)

        # Right Side Panel (Volume meter + Play state)
        panel_x = scr_x + cover_w
        panel_w = scr_w - cover_w
        draw.rectangle([panel_x, scr_y, scr_x + scr_w, scr_y + scr_h], fill=PALETTE['panel_bg'])
        draw.line([panel_x, scr_y, panel_x, scr_y + scr_h], fill=PALETTE['device_border'], width=1)

        # Play triangle icon
        play_icon_x = panel_x + panel_w // 2
        draw.polygon([(play_icon_x - 5, scr_y + 16), (play_icon_x - 5, scr_y + 30), (play_icon_x + 8, scr_y + 23)], fill=PALETTE['sage_green'])

        # Vertical Audio Volume Equalizer Bar
        bar_box_x = panel_x + 22
        bar_box_y = scr_y + 44
        bar_box_w = 42
        bar_box_h = 150

        draw.rectangle([bar_box_x, bar_box_y, bar_box_x + bar_box_w, bar_box_y + bar_box_h], fill=(16, 18, 23), outline=(45, 50, 62), width=1)

        # Dynamic volume calculation with beat boost
        base_vol = 0.55 + 0.20 * math.sin(angle_rad * 4) + 0.15 * math.cos(angle_rad * 6)
        if is_beat:
            base_vol = min(0.95, base_vol + 0.25 * beat_intensity)
        current_vol_h = int(bar_box_h * base_vol)

        # Render discrete equalizer segments
        num_segments = 15
        for seg in range(num_segments):
            seg_y = bar_box_y + bar_box_h - (seg + 1) * (bar_box_h // num_segments)
            seg_h = (bar_box_h // num_segments) - 2
            
            if (bar_box_h - (seg_y - bar_box_y)) <= current_vol_h:
                if seg > 11:
                    seg_fill = PALETTE['terracotta']
                elif seg > 7:
                    seg_fill = PALETTE['warm_amber']
                else:
                    seg_fill = PALETTE['sage_green']
                draw.rectangle([bar_box_x + 3, seg_y, bar_box_x + bar_box_w - 3, seg_y + seg_h], fill=seg_fill)

        # Bottom Scrolling Song Marquee Banner
        banner_y = scr_y + scr_h - 32
        draw.rectangle([scr_x, banner_y, scr_x + scr_w, scr_y + scr_h], fill=(18, 21, 26))
        draw.line([scr_x, banner_y, scr_x + scr_w, banner_y], fill=PALETTE['slate_blue'], width=1)

        char_offset = int((frame_idx / NUM_FRAMES) * 36) % len(song_title)
        disp_marquee = (song_title + song_title)[char_offset : char_offset + 38]
        draw.text((scr_x + 10, banner_y + 8), disp_marquee, font=font_lcd, fill=PALETTE['text_primary'])

        # -------------------------------------------------------------
        # 4. Status LEDs on Chassis
        # -------------------------------------------------------------
        led_y = dev_y + 290
        # Blue LED (Wi-Fi streaming) - gentle breathing
        blue_glow = 0.7 + 0.3 * math.sin(angle_rad * 2)
        blue_color = (int(PALETTE['slate_blue'][0] * blue_glow), int(PALETTE['slate_blue'][1] * blue_glow), int(PALETTE['slate_blue'][2] * blue_glow))
        draw.ellipse([dev_x + 40 - 5, led_y - 5, dev_x + 40 + 5, led_y + 5], fill=blue_color, outline=(80, 110, 150))
        draw.text((dev_x + 52, led_y - 6), "SYNC", font=font_mono_small, fill=PALETTE['text_muted'])

        # Green LED (Beat Pulse) - snaps on beat
        green_val = int(255 * (0.15 + 0.85 * beat_intensity))
        green_color = (int(PALETTE['sage_green'][0] * (green_val / 255)), int(PALETTE['sage_green'][1] * (green_val / 255)), int(PALETTE['sage_green'][2] * (green_val / 255)))
        draw.ellipse([dev_x + 160 - 5, led_y - 5, dev_x + 160 + 5, led_y + 5], fill=green_color, outline=(70, 120, 80))
        draw.text((dev_x + 172, led_y - 6), "BEAT", font=font_mono_small, fill=PALETTE['text_muted'])

        # Red LED (Idle / Paused) - dim indicator
        draw.ellipse([dev_x + 280 - 5, led_y - 5, dev_x + 280 + 5, led_y + 5], fill=(70, 30, 30), outline=(100, 45, 45))
        draw.text((dev_x + 292, led_y - 6), "IDLE", font=font_mono_small, fill=PALETTE['text_dim'])

        # -------------------------------------------------------------
        # 5. Hardware Navigation Buttons
        # -------------------------------------------------------------
        btn_y = dev_y + 314
        btn_w, btn_h = 96, 32
        btns = [
            ("PREV (D25)", dev_x + 28),
            ("PLAY (D26)", dev_x + 148),
            ("NEXT (D33)", dev_x + 268)
        ]
        
        # Simulate button press every ~40 frames
        pressed_btn_idx = 1 if (35 <= frame_idx <= 42) else -1

        for i, (label, bx) in enumerate(btns):
            is_pressed = (i == pressed_btn_idx)
            b_bg = (55, 62, 75) if is_pressed else PALETTE['btn_bg']
            b_border = PALETTE['warm_amber'] if is_pressed else PALETTE['btn_border']
            b_text_col = PALETTE['warm_amber'] if is_pressed else PALETTE['text_primary']
            
            draw.rounded_rectangle([bx, btn_y, bx + btn_w, btn_y + btn_h], radius=6, fill=b_bg, outline=b_border, width=1)
            draw.text((bx + 16, btn_y + 9), label, font=font_btn, fill=b_text_col)

        # -------------------------------------------------------------
        # 6. Right Side Panel: System Metrics & FFT Audio Telemetry
        # -------------------------------------------------------------
        side_x = 445
        side_y = 86
        side_w = 360
        side_h = 360

        draw.rounded_rectangle([side_x, side_y, side_x + side_w, side_y + side_h], radius=12, fill=(22, 24, 29), outline=PALETTE['card_border'], width=1)

        # Telemetry Section Title
        draw.text((side_x + 20, side_y + 16), "LIVE AUDIO & TELEMETRY STREAM", font=font_badge, fill=PALETTE['slate_blue'])

        # Audio FFT Spectrum Visualizer Card
        fft_box_x = side_x + 20
        fft_box_y = side_y + 40
        fft_box_w = side_w - 40
        fft_box_h = 100

        draw.rounded_rectangle([fft_box_x, fft_box_y, fft_box_x + fft_box_w, fft_box_y + fft_box_h], radius=8, fill=(15, 17, 21), outline=(38, 42, 52), width=1)
        draw.text((fft_box_x + 12, fft_box_y + 8), "WASAPI Loopback FFT Spectrum (20 Hz - 16 kHz)", font=font_mono_small, fill=PALETTE['text_dim'])

        # Draw simulated dynamic FFT spectrum bars
        num_fft_bars = 28
        bar_w = (fft_box_w - 24) // num_fft_bars
        for b_idx in range(num_fft_bars):
            freq_factor = math.exp(-b_idx * 0.08)
            dyn = math.sin(angle_rad * 3 + b_idx * 0.4) * 0.3 + math.cos(angle_rad * 5 + b_idx * 0.7) * 0.2
            if b_idx < 5 and is_beat:
                dyn += 0.5 * beat_intensity
            
            bar_height = max(6, int(60 * (freq_factor * 0.7 + dyn * 0.3)))
            bx = fft_box_x + 12 + b_idx * bar_w
            by = fft_box_y + fft_box_h - 12 - bar_height

            bar_c = PALETTE['warm_amber'] if (b_idx < 6 and is_beat) else PALETTE['sage_green']
            draw.rectangle([bx, by, bx + bar_w - 2, fft_box_y + fft_box_h - 12], fill=bar_c)

        # Key Metrics Grid (2x2)
        grid_y = side_y + 154
        metrics = [
            ("RMS VOLUME", f"{int(base_vol * 100)} %", "-13.8 dBFS", PALETTE['sage_green']),
            ("BASS KICK", "TRIGGERED" if is_beat else "LISTENING", "20-140 Hz Band", PALETTE['warm_amber'] if is_beat else PALETTE['text_muted']),
            ("UDP TELEMETRY", "40.2 FPS", "Port 12345 (Sub-10ms)", PALETTE['slate_blue']),
            ("HTTP RAW COVER", "32.7 KB (RGB565)", "Port 8080 (Lossless TCP)", PALETTE['text_primary']),
        ]

        for idx, (m_title, m_val, m_sub, m_col) in enumerate(metrics):
            gx = side_x + 20 + (idx % 2) * (fft_box_w // 2 + 5)
            gy = grid_y + (idx // 2) * 58
            gw = fft_box_w // 2 - 5
            gh = 50

            draw.rounded_rectangle([gx, gy, gx + gw, gy + gh], radius=6, fill=(17, 19, 23), outline=(35, 39, 48), width=1)
            draw.text((gx + 10, gy + 6), m_title, font=font_mono_small, fill=PALETTE['text_dim'])
            draw.text((gx + 10, gy + 18), m_val, font=font_mono_bold, fill=m_col)
            draw.text((gx + 10, gy + 34), m_sub, font=font_mono_small, fill=PALETTE['text_muted'])

        # Protocol Architecture Flow at Bottom of Panel
        flow_y = side_y + 280
        draw.rounded_rectangle([side_x + 20, flow_y, side_x + side_w - 20, flow_y + 64], radius=6, fill=(15, 17, 21), outline=(35, 39, 48), width=1)
        draw.text((side_x + 30, flow_y + 8), "BIDIRECTIONAL WI-FI BRIDGE", font=font_mono_small, fill=PALETTE['text_dim'])
        draw.text((side_x + 30, flow_y + 24), "PC Host ────► UDP Telemetry & HTTP ────► ESP32", font=font_mono_small, fill=PALETTE['sage_green'])
        draw.text((side_x + 30, flow_y + 42), "ESP32   ────► Hardware Button Packet ──► PC Host", font=font_mono_small, fill=PALETTE['warm_amber'])

        # Append frame
        frames.append(img)

    # Save as optimized animated GIF
    out_path = 'assets/deskdock_demo.gif'
    frames[0].save(
        out_path,
        save_all=True,
        append_images=frames[1:],
        duration=DURATION,
        loop=0,
        optimize=True
    )
    print(f"Successfully generated GIF animation at: {out_path} ({len(frames)} frames)")

if __name__ == '__main__':
    create_animation()
