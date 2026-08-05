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

    # Create image with gradient background
    img = Image.new('RGB', (width, height), color=(30, 30, 40))
    draw = ImageDraw.Draw(img)

    # Draw gradient background
    for y in range(height):
        r = int(30 + (y / height) * 20)
        g = int(30 + (y / height) * 10)
        b = int(40 + (y / height) * 30)
        draw.line([(0, y), (width, y)], fill=(r, g, b))

    # Try to load font
    try:
        font_large = ImageFont.truetype("arial.ttf", 36)
        font_medium = ImageFont.truetype("arial.ttf", 24)
        font_small = ImageFont.truetype("arial.ttf", 18)
    except:
        font_large = ImageFont.load_default()
        font_medium = ImageFont.load_default()
        font_small = ImageFont.load_default()

    # Draw text
    draw.text((50, 50), title, fill=(255, 255, 255), font=font_large)
    draw.text((50, 100), artist, fill=(180, 180, 180), font=font_medium)

    # Draw feature bars
    features = [
        ("Energy", energy, (255, 100, 100)),
        ("Valence", valence, (100, 255, 100)),
        ("Dance", danceability, (100, 100, 255)),
    ]

    y_pos = 180
    for name, value, color in features:
        draw.text((50, y_pos), name, fill=(200, 200, 200), font=font_small)

        # Bar background
        draw.rectangle([(150, y_pos), (750, y_pos + 25)], fill=(60, 60, 70))

        # Bar fill
        bar_width = int(value * 600)
        draw.rectangle([(150, y_pos), (150 + bar_width, y_pos + 25)], fill=color)

        y_pos += 45

    # Draw BPM
    draw.text((50, 320), f"BPM: {bpm:.0f}", fill=(200, 200, 200), font=font_small)

    # Draw branding
    draw.text((width - 200, 350), "Music Suggest Bot", fill=(100, 100, 100), font=font_small)

    # Save to bytes
    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
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
    img = Image.new('RGB', (width, height), color=(30, 30, 40))
    draw = ImageDraw.Draw(img)

    # Gradient background
    for y in range(height):
        r = int(30 + (y / height) * 20)
        g = int(30 + (y / height) * 10)
        b = int(40 + (y / height) * 30)
        draw.line([(0, y), (width, y)], fill=(r, g, b))

    try:
        font_large = ImageFont.truetype("arial.ttf", 28)
        font_medium = ImageFont.truetype("arial.ttf", 20)
        font_small = ImageFont.truetype("arial.ttf", 16)
    except:
        font_large = ImageFont.load_default()
        font_medium = ImageFont.load_default()
        font_small = ImageFont.load_default()

    # Track 1
    draw.text((50, 30), track1_title, fill=(255, 100, 100), font=font_large)
    draw.text((50, 70), track1_artist, fill=(200, 150, 150), font=font_medium)

    # Track 2
    draw.text((450, 30), track2_title, fill=(100, 100, 255), font=font_large)
    draw.text((450, 70), track2_artist, fill=(150, 150, 200), font=font_medium)

    # VS
    draw.text((370, 40), "VS", fill=(255, 255, 255), font=font_large)

    # Comparison bars
    features = ["BPM", "Energy", "Valence", "Dance"]
    keys = ["bpm", "energy", "valence", "danceability"]

    y_pos = 130
    for feat_name, key in zip(features, keys):
        val1 = track1_features.get(key, 0)
        val2 = track2_features.get(key, 0)

        # Normalize BPM
        if key == "bpm":
            val1 = min(val1 / 200, 1.0)
            val2 = min(val2 / 200, 1.0)

        draw.text((50, y_pos), feat_name, fill=(200, 200, 200), font=font_small)

        # Track 1 bar (left side)
        bar1_width = int(val1 * 300)
        draw.rectangle([(200, y_pos), (200 + bar1_width, y_pos + 20)], fill=(255, 100, 100))

        # Track 2 bar (right side)
        bar2_width = int(val2 * 300)
        draw.rectangle([(550 - bar2_width, y_pos), (550, y_pos + 20)], fill=(100, 100, 255))

        y_pos += 40

    # Draw branding
    draw.text((width - 200, height - 50), "Music Suggest Bot", fill=(100, 100, 100), font=font_small)

    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
    buffer.seek(0)

    return buffer.getvalue()
