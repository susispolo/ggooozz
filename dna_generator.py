"""
Musical DNA visualization generator.
Creates unique visual fingerprints for songs based on audio features.
"""
import io
import math
import logging
from typing import Optional

log = logging.getLogger(__name__)


def generate_musical_dna(
    title: str,
    artist: str,
    bpm: float = 0,
    energy: float = 0,
    valence: float = 0,
    danceability: float = 0,
    mfcc_means: list[float] = None,
    chroma_means: list[float] = None,
) -> Optional[bytes]:
    """
    Generate a unique visual fingerprint for a song.
    Returns PNG bytes or None.
    """
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        log.error("Pillow not installed! Run: pip install Pillow")
        return None

    # DNA dimensions
    width, height = 600, 600
    center_x, center_y = width // 2, height // 2

    # Create image with dark background
    img = Image.new('RGB', (width, height), color=(10, 10, 20))
    draw = ImageDraw.Draw(img)

    # Generate color from features
    def feature_to_color(bpm, energy, valence):
        r = int(min(energy * 255, 255))
        g = int(min(valence * 255, 255))
        b = int(min((bpm / 200) * 255, 255))
        return (r, g, b)

    base_color = feature_to_color(bpm, energy, valence)

    # Draw concentric rings
    num_rings = 8
    for i in range(num_rings):
        radius = 50 + i * 30
        color_var = ((i * 30) % 256, (i * 50 + 100) % 256, (i * 70 + 50) % 256)
        draw.ellipse(
            [center_x - radius, center_y - radius, center_x + radius, center_y + radius],
            outline=color_var,
            width=2
        )

    # Draw radial lines based on features
    if mfcc_means and len(mfcc_means) >= 6:
        num_lines = min(len(mfcc_means), 12)
        for i in range(num_lines):
            angle = (i / num_lines) * 2 * math.pi
            # Use MFCC value to determine line length
            length = 80 + abs(mfcc_means[i % len(mfcc_means)]) * 50
            length = min(length, 250)

            end_x = center_x + int(length * math.cos(angle))
            end_y = center_y + int(length * math.sin(angle))

            # Color based on position and features
            line_color = (
                int((i / num_lines) * 255),
                int(base_color[1]),
                int((1 - i / num_lines) * 255)
            )

            draw.line([(center_x, center_y), (end_x, end_y)], fill=line_color, width=2)

    # Draw chroma circles
    if chroma_means and len(chroma_means) >= 12:
        for i, chroma_val in enumerate(chroma_means[:12]):
            angle = (i / 12) * 2 * math.pi
            radius = 150 + chroma_val * 50

            x = center_x + int(radius * math.cos(angle))
            y = center_y + int(radius * math.sin(angle))

            # Small circle at each chroma position
            circle_size = 5 + int(chroma_val * 10)
            circle_color = (
                int((i / 12) * 255),
                int(chroma_val * 255),
                int((1 - chroma_val) * 255)
            )
            draw.ellipse(
                [x - circle_size, y - circle_size, x + circle_size, y + circle_size],
                fill=circle_color
            )

    # Draw central dot
    draw.ellipse(
        [center_x - 10, center_y - 10, center_x + 10, center_y + 10],
        fill=base_color
    )

    # Add text labels
    try:
        font_small = ImageFont.truetype("arial.ttf", 14)
        font_medium = ImageFont.truetype("arial.ttf", 18)
    except:
        font_small = ImageFont.load_default()
        font_medium = ImageFont.load_default()

    # Title
    draw.text((50, 20), f"🎵 {title}", fill=(255, 255, 255), font=font_medium)
    draw.text((50, 50), f"👤 {artist}", fill=(180, 180, 180), font=font_small)

    # Feature labels
    draw.text((50, height - 80), f"BPM: {bpm:.0f}", fill=(200, 200, 200), font=font_small)
    draw.text((200, height - 80), f"Energy: {energy:.2f}", fill=(200, 200, 200), font=font_small)
    draw.text((380, height - 80), f"Valence: {valence:.2f}", fill=(200, 200, 200), font=font_small)

    # Branding
    draw.text((width - 150, height - 30), "Musical DNA", fill=(100, 100, 100), font=font_small)

    # Save to bytes
    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
    buffer.seek(0)

    log.info("[DNA] generated for %s - %s (%d bytes)", title, artist, len(buffer.getvalue()))
    return buffer.getvalue()
