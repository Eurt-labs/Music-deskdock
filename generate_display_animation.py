import math
import os
import numpy as np
from PIL import Image, ImageDraw, ImageFont

def create_display_animation():
    os.makedirs('assets', exist_ok=True)
    
    W, H = 720, 540
    NUM_FRAMES = 60
    FPS = 20
    DURATION = int(1000 / FPS)  # 50 ms per frame
    
    # Fonts
    font_title = ImageFont.truetype('C:/Windows/Fonts/segoeuib.ttf', 15)
    font_mono = ImageFont.truetype('C:/Windows/Fonts/consola.ttf', 12)
    font_mono_small = ImageFont.truetype('C:/Windows/Fonts/consola.ttf', 9)
    font_badge = ImageFont.truetype('C:/Windows/Fonts/segoeuib.ttf', 10)
    font_lcd = ImageFont.truetype('C:/Windows/Fonts/segoeuib.ttf', 13)
    font_vol = ImageFont.truetype('C:/Windows/Fonts/consolab.ttf', 11)

    # Natural & Neutral Palette
    PALETTE = {
        'bg': (19, 21, 25),              # Deep matte charcoal
        'card': (24, 27, 34),            # Card background
        'border': (42, 46, 56),          # Card border
        'pcb': (31, 35, 43),             # TFT module PCB
        'pcb_border': (50, 56, 70),      # PCB border
        'bezel': (13, 15, 18),           # Metal screen bezel
        'screen_bg': (17, 19, 23),       # ST7735 display black/slate
        'panel_bg': (21, 23, 29),        # Side panel
        'text_primary': (230, 235, 242), # Linen white
        'text_muted': (135, 145, 160),   # Muted grey
        'text_dim': (96, 105, 122),      # Dim grey
        'sage_green': (138, 180, 148),   # Natural sage green
        'sage_light': (168, 206, 178),   # Soft mint
        'warm_amber': (212, 163, 115),   # Warm amber / gold
        'slate_blue': (115, 160, 205),   # Slate blue
        'terracotta': (205, 115, 115),   # Muted red
        'gold_hole': (158, 124, 72),     # Mounting hole copper ring
    }

    frames = []
    song_title = "The Weeknd - Blinding Lights   •   Album: After Hours   •   WASAPI 44.1kHz   •   "

    for frame_idx in range(NUM_FRAMES):
        t = frame_idx / NUM_FRAMES
        angle_rad = t * 2 * math.pi
        
        img = Image.new('RGB', (W, H), PALETTE['bg'])
        draw = ImageDraw.Draw(img)

        # 1. Outer Container Card
        draw.rounded_rectangle([18, 18, W - 18, H - 18], radius=14, fill=PALETTE['card'], outline=PALETTE['border'], width=1)

        # Header Bar
        draw.text((42, 36), "ST7735 1.8\" TFT DISPLAY", font=font_title, fill=PALETTE['text_primary'])
        draw.text((235, 39), "160 × 128 Landscape  •  Double-Buffered RAM", font=font_mono, fill=PALETTE['slate_blue'])

        # 40 FPS Badge
        badge_x, badge_y, badge_w, badge_h = W - 170, 32, 126, 24
        draw.rounded_rectangle([badge_x, badge_y, badge_x + badge_w, badge_y + badge_h], radius=4, fill=(21, 38, 29), outline=(46, 84, 61), width=1)
        pulse_r = 3.5 + math.sin(angle_rad * 2) * 0.8
        draw.ellipse([badge_x + 12 - pulse_r, badge_y + 12 - pulse_r, badge_x + 12 + pulse_r, badge_y + 12 + pulse_r], fill=PALETTE['sage_green'])
        draw.text((badge_x + 22, badge_y + 5), "40 FPS SYNC", font=font_badge, fill=PALETTE['sage_green'])

        draw.line([42, 64, W - 42, 64], fill=PALETTE['border'], width=1)

        # 2. PCB Carrier Board
        pcb_x, pcb_y, pcb_w, pcb_h = 42, 80, 636, 420
        draw.rounded_rectangle([pcb_x, pcb_y, pcb_x + pcb_w, pcb_y + pcb_h], radius=12, fill=PALETTE['pcb'], outline=PALETTE['pcb_border'], width=2)

        # 4 Corner Mounting Holes with Copper Rings
        for mx, my in [(pcb_x + 16, pcb_y + 16), (pcb_x + pcb_w - 16, pcb_y + 16), (pcb_x + 16, pcb_y + pcb_h - 16), (pcb_x + pcb_w - 16, pcb_y + pcb_h - 16)]:
            draw.ellipse([mx - 7, my - 7, mx + 7, my + 7], fill=PALETTE['bg'], outline=PALETTE['gold_hole'], width=2)

        # Pin Header Labels at top
        pins = [("VCC", 110), ("GND", 155), ("CS (D5)", 205), ("RST (D4)", 265), ("DC (D2)", 335), ("MOSI (D23)", 400), ("SCK (D18)", 480), ("LED", 550)]
        for pname, px in pins:
            draw.text((px, pcb_y + 12), pname, font=font_mono_small, fill=PALETTE['text_dim'])

        # Metal Screen Bezel Frame
        bez_x, bez_y, bez_w, bez_h = pcb_x + 24, pcb_y + 30, 588, 368
        draw.rounded_rectangle([bez_x, bez_y, bez_x + bez_w, bez_y + bez_h], radius=8, fill=PALETTE['bezel'], outline=(37, 42, 52), width=2)

        # 3. Active ST7735 Screen Surface (576 x 356 px)
        scr_x, scr_y, scr_w, scr_h = bez_x + 6, bez_y + 6, bez_w - 12, bez_h - 12
        draw.rectangle([scr_x, scr_y, scr_x + scr_w, scr_y + scr_h], fill=PALETTE['screen_bg'])

        # Beat detection timing (4 beats per 60 frames)
        beat_phase = (frame_idx % 15) / 15.0
        is_beat = beat_phase < 0.25
        beat_intensity = max(0.0, 1.0 - (beat_phase / 0.35)) if is_beat else 0.0

        # Screen Division: Left 460px = Album Artwork, Right 116px = Side Panel
        cover_w = 460
        cover_h = scr_h

        # Album Art Background
        draw.rectangle([scr_x, scr_y, scr_x + cover_w, scr_y + cover_h], fill=(20, 23, 29))

        # Spinning Vinyl Record
        vinyl_cx = scr_x + cover_w // 2
        vinyl_cy = scr_y + (cover_h - 52) // 2
        spin_angle = angle_rad * 3

        # Vinyl Grooves
        for r_disc in [130, 115, 100, 85, 70, 55]:
            c_val = int(24 + (r_disc % 25) * 0.7)
            draw.ellipse([vinyl_cx - r_disc, vinyl_cy - r_disc, vinyl_cx + r_disc, vinyl_cy + r_disc], fill=(c_val, c_val + 2, c_val + 6), outline=(34, 38, 48), width=1)

        # Vinyl Center Label (Warm Amber)
        label_r = 44
        draw.ellipse([vinyl_cx - label_r, vinyl_cy - label_r, vinyl_cx + label_r, vinyl_cy + label_r], fill=(164, 114, 66), outline=PALETTE['warm_amber'], width=2)
        draw.ellipse([vinyl_cx - 9, vinyl_cy - 9, vinyl_cx + 9, vinyl_cy + 9], fill=(13, 15, 18))

        # Grooved reflection highlight lines
        for h_off in [-0.38, 0.38]:
            h_ang = spin_angle + h_off
            hx1 = vinyl_cx + math.cos(h_ang) * 50
            hy1 = vinyl_cy + math.sin(h_ang) * 50
            hx2 = vinyl_cx + math.cos(h_ang) * 125
            hy2 = vinyl_cy + math.sin(h_ang) * 125
            draw.line([hx1, hy1, hx2, hy2], fill=(55, 62, 76), width=2)

        # Dynamic Pulsing Beat Border
        if beat_intensity > 0.05:
            b_color = (
                int(PALETTE['warm_amber'][0] * beat_intensity + PALETTE['screen_bg'][0] * (1 - beat_intensity)),
                int(PALETTE['warm_amber'][1] * beat_intensity + PALETTE['screen_bg'][1] * (1 - beat_intensity)),
                int(PALETTE['warm_amber'][2] * beat_intensity + PALETTE['screen_bg'][2] * (1 - beat_intensity)),
            )
            draw.rectangle([scr_x + 2, scr_y + 2, scr_x + cover_w - 2, scr_y + scr_h - 54], outline=b_color, width=3)
        else:
            draw.rectangle([scr_x + 2, scr_y + 2, scr_x + cover_w - 2, scr_y + scr_h - 54], outline=(38, 42, 52), width=1)

        # Bottom Marquee Song Banner Strip
        banner_y = scr_y + scr_h - 52
        draw.rectangle([scr_x, banner_y, scr_x + cover_w, scr_y + scr_h], fill=(22, 25, 32))
        draw.line([scr_x, banner_y, scr_x + cover_w, banner_y], fill=PALETTE['slate_blue'], width=2)

        char_offset = int((frame_idx / NUM_FRAMES) * 42) % len(song_title)
        disp_marquee = (song_title + song_title)[char_offset : char_offset + 42]
        draw.text((scr_x + 14, banner_y + 16), disp_marquee, font=font_lcd, fill=PALETTE['text_primary'])

        # 4. Right 116px Side Panel & Volume Equalizer
        panel_x = scr_x + cover_w
        panel_w = scr_w - cover_w
        draw.rectangle([panel_x, scr_y, scr_x + scr_w, scr_y + scr_h], fill=PALETTE['panel_bg'])
        draw.line([panel_x, scr_y, panel_x, scr_y + scr_h], fill=(40, 45, 56), width=2)

        # Play triangle icon
        play_cx = panel_x + panel_w // 2
        draw.polygon([(play_cx - 8, scr_y + 20), (play_cx - 8, scr_y + 40), (play_cx + 10, scr_y + 30)], fill=PALETTE['sage_green'])

        # Vertical Equalizer Bar
        eq_box_x = panel_x + 32
        eq_box_y = scr_y + 54
        eq_box_w = 52
        eq_box_h = 240

        draw.rounded_rectangle([eq_box_x, eq_box_y, eq_box_x + eq_box_w, eq_box_y + eq_box_h], radius=4, fill=(13, 15, 18), outline=(41, 46, 57), width=1)

        # Volume calculation with beat bump
        base_vol = 0.60 + 0.18 * math.sin(angle_rad * 4) + 0.12 * math.cos(angle_rad * 6)
        if is_beat:
            base_vol = min(0.96, base_vol + 0.26 * beat_intensity)
        vol_pct = int(base_vol * 100)

        # 14 discrete LED-style equalizer blocks
        num_segs = 14
        seg_h = (eq_box_h - 10) // num_segs
        for seg in range(num_segs):
            sy = eq_box_y + eq_box_h - 6 - (seg + 1) * seg_h
            is_active = (seg / num_segs) <= base_vol
            
            if seg >= 12:
                seg_col = PALETTE['terracotta'] if is_active else (60, 25, 25)
            elif seg >= 8:
                seg_col = PALETTE['warm_amber'] if is_active else (55, 42, 25)
            else:
                seg_col = PALETTE['sage_green'] if is_active else (25, 45, 32)
                
            draw.rectangle([eq_box_x + 5, sy, eq_box_x + eq_box_w - 5, sy + seg_h - 2], fill=seg_col)

        # Volume Readout Text
        draw.text((panel_x + 24, scr_y + scr_h - 36), f"{vol_pct}% VOL", font=font_vol, fill=PALETTE['sage_green'])

        # Glass sheen overlay (subtle transparent corner)
        frames.append(img)

    # Save animated GIF
    out_gif = 'assets/esp32_display_demo.gif'
    frames[0].save(
        out_gif,
        save_all=True,
        append_images=frames[1:],
        duration=DURATION,
        loop=0,
        optimize=True
    )
    print(f"Successfully generated display GIF animation at: {out_gif} ({len(frames)} frames)")

if __name__ == '__main__':
    create_display_animation()
