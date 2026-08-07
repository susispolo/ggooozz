"""
Music card image generator.
Creates shareable images with song info and feature visualization.
"""
import io
import logging
from typing import Optional

log = logging.getLogger(__name__)


def generate_music_card(
    title: str,
    artist: str,
    bpm: float = 0,
    energy: float = 0,
    valence: float = 0,
    danceability: float = 0,
    album_art_url: Optional[str] = None,
) -> Optional[bytes]:
    """
    Generate a music card image.
    Returns PNG bytes or None.
    """
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        log.error("Pillow not installed! Run: pip install Pillow")
        return None

    # Card dimensions
    width, height = 800, 400

    # Create image with dark gradient background
    img = Image.new('RGB', (width, height), color=(15, 15, 25))
    draw = ImageDraw.Draw(img)

    # Draw sophisticated gradient background (dark blue to purple)
    for y in range(height):
        ratio = y / height
        r = int(15 + ratio * 25)
        g = int(15 + ratio * 10)
        b = int(25 + ratio * 35)
        draw.line([(0, y), (width, y)], fill=(r, g, b))

    # Try to load font
    try:
        font_large = ImageFont.truetype("arial.ttf", 36)
        font_medium = ImageFont.truetype("arial.ttf", 24)
        font_small = ImageFont.truetype("arial.ttf", 18)
        font_tiny = ImageFont.truetype("arial.ttf", 14)
    except:
        font_large = ImageFont.load_default()
        font_medium = ImageFont.load_default()
        font_small = ImageFont.load_default()
        font_tiny = ImageFont.load_default()

    # Draw decorative accent line at top
    draw.rectangle([(0, 0), (width, 4)], fill=(100, 150, 255))

    # Draw song info with better typography
    draw.text((50, 40), title, fill=(255, 255, 255), font=font_large)
    draw.text((50, 90), artist, fill=(150, 180, 220), font=font_medium)

    # Draw feature bars with modern design
    features = [
        ("Energy", energy, (255, 80, 80)),
        ("Valence", valence, (80, 200, 120)),
        ("Dance", danceability, (80, 120, 255)),
    ]

    y_pos = 160
    for name, value, color in features:
        # Feature name
        draw.text((50, y_pos), name, fill=(180, 200, 220), font=font_small)

        # Bar background with rounded corners effect
        draw.rectangle([(160, y_pos), (750, y_pos + 28)], fill=(40, 45, 55))

        # Bar fill with gradient effect
        bar_width = int(value * 590)
        if bar_width > 0:
            for x in range(160, 160 + bar_width):
                ratio = (x - 160) / max(bar_width, 1)
                r = int(color[0] * (0.7 + 0.3 * ratio))
                g = int(color[1] * (0.7 + 0.3 * ratio))
                b = int(color[2] * (0.7 + 0.3 * ratio))
                draw.line([(x, y_pos), (x, y_pos + 28)], fill=(r, g, b))

        # Value percentage
        pct = f"{int(value * 100)}%"
        draw.text((760, y_pos + 4), pct, fill=(150, 150, 150), font=font_tiny)

        y_pos += 48

    # Draw BPM in a stylish box
    draw.rectangle([(50, 320), (180, 360)], fill=(40, 45, 55))
    draw.text((60, 328), f"♪ {bpm:.0f} BPM", fill=(100, 150, 255), font=font_small)

    # Draw branding with accent
    draw.text((width - 220, 370), "Music Suggest Bot", fill=(80, 90, 100), font=font_tiny)

    # Save to bytes
    buffer = io.BytesIO()
    img.save(buffer, format='PNG', optimize=True)
    buffer.seek(0)

    log.info("[CARD] generated music card for %s - %s (%d bytes)", title, artist, len(buffer.getvalue()))
    return buffer.getvalue()


def generate_comparison_card(
    track1_title: str,
    track1_artist: str,
    track1_features: dict,
    track2_title: str,
    track2_artist: str,
    track2_features: dict,
) -> Optional[bytes]:
    """
    Generate a comparison card for two tracks.
    Returns PNG bytes or None.
    """
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        log.error("Pillow not installed! Run: pip install Pillow")
        return None

    width, height = 800, 500
    img = Image.new('RGB', (width, height), color=(15, 15, 25))
    draw = ImageDraw.Draw(img)

    # Sophisticated gradient background
    for y in range(height):
        ratio = y / height
        r = int(15 + ratio * 20)
        g = int(15 + ratio * 8)
        b = int(25 + ratio * 30)
        draw.line([(0, y), (width, y)], fill=(r, g, b))

    # Decorative top accent
    draw.rectangle([(0, 0), (width, 4)], fill=(100, 150, 255))

    try:
        font_large = ImageFont.truetype("arial.ttf", 28)
        font_medium = ImageFont.truetype("arial.ttf", 20)
        font_small = ImageFont.truetype("arial.ttf", 16)
        font_tiny = ImageFont.truetype("arial.ttf", 14)
    except:
        font_large = ImageFont.load_default()
        font_medium = ImageFont.load_default()
        font_small = ImageFont.load_default()
        font_tiny = ImageFont.load_default()

    # Track 1 (left side with red accent)
    draw.rectangle([(30, 20), (380, 90)], fill=(40, 25, 25))
    draw.text((40, 25), track1_title, fill=(255, 120, 120), font=font_large)
    draw.text((40, 60), track1_artist, fill=(200, 150, 150), font=font_medium)

    # Track 2 (right side with blue accent)
    draw.rectangle([(420, 20), (770, 90)], fill=(25, 25, 40))
    draw.text((430, 25), track2_title, fill=(120, 150, 255), font=font_large)
    draw.text((430, 60), track2_artist, fill=(150, 170, 200), font=font_medium)

    # VS badge
    draw.ellipse([(370, 30), (430, 70)], fill=(60, 60, 70))
    draw.text((385, 38), "VS", fill=(255, 255, 255), font=font_large)

    # Comparison bars with modern design
    features = ["BPM", "Energy", "Valence", "Dance"]
    keys = ["bpm", "energy", "valence", "danceability"]

    y_pos = 120
    for feat_name, key in zip(features, keys):
        val1 = track1_features.get(key, 0)
        val2 = track2_features.get(key, 0)

        # Normalize BPM
        if key == "bpm":
            val1 = min(val1 / 200, 1.0)
            val2 = min(val2 / 200, 1.0)

        # Feature name centered
        draw.text((360, y_pos + 2), feat_name, fill=(180, 200, 220), font=font_small, anchor="mt")

        # Track 1 bar (left side, grows right)
        bar1_width = int(val1 * 280)
        if bar1_width > 0:
            for x in range(70, 70 + bar1_width):
                ratio = (x - 70) / max(bar1_width, 1)
                r = int(255 * (0.7 + 0.3 * ratio))
                g = int(80 * (0.7 + 0.3 * ratio))
                b = int(80 * (0.7 + 0.3 * ratio))
                draw.line([(x, y_pos), (x, y_pos + 22)], fill=(r, g, b))

        # Track 2 bar (right side, grows left)
        bar2_width = int(val2 * 280)
        if bar2_width > 0:
            for x in range(730 - bar2_width, 730):
                ratio = (730 - x) / max(bar2_width, 1)
                r = int(80 * (0.7 + 0.3 * ratio))
                g = int(100 * (0.7 + 0.3 * ratio))
                b = int(255 * (0.7 + 0.3 * ratio))
                draw.line([(x, y_pos), (x, y_pos + 22)], fill=(r, g, b))

        # Value percentages
        pct1 = f"{int(val1 * 100)}%"
        pct2 = f"{int(val2 * 100)}%"
        draw.text((70, y_pos + 4), pct1, fill=(200, 150, 150), font=font_tiny)
        draw.text((740, y_pos + 4), pct2, fill=(150, 170, 200), font=font_tiny, anchor="rt")

        y_pos += 50

    # Draw branding with accent line
    draw.rectangle([(0, height - 40), (width, height)], fill=(10, 12, 18))
    draw.text((width - 220, height - 30), "Music Suggest Bot", fill=(70, 80, 90), font=font_tiny)

    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
    buffer.seek(0)

    return buffer.getvalue()
