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

    # Create image with sophisticated dark background
    img = Image.new('RGB', (width, height), color=(8, 12, 18))
    draw = ImageDraw.Draw(img)

    # Draw subtle radial gradient background
    for radius in range(300, 0, -1):
        ratio = radius / 300
        r = int(8 + (1 - ratio) * 15)
        g = int(12 + (1 - ratio) * 10)
        b = int(18 + (1 - ratio) * 20)
        draw.ellipse(
            [center_x - radius, center_y - radius, center_x + radius, center_y + radius],
            fill=(r, g, b)
        )

    # Generate color from features (more vibrant palette)
    def feature_to_color(bpm, energy, valence):
        r = int(min(energy * 200 + 50, 255))
        g = int(min(valence * 180 + 70, 255))
        b = int(min((bpm / 180) * 200 + 55, 255))
        return (r, g, b)

    base_color = feature_to_color(bpm, energy, valence)

    # Draw outer decorative rings with glow effect
    num_rings = 6
    for i in range(num_rings):
        radius = 80 + i * 35
        # Outer glow
        for w in range(3):
            alpha_ratio = 1 - (w / 3)
            color_var = (
                int(base_color[0] * alpha_ratio * 0.3),
                int(base_color[1] * alpha_ratio * 0.3),
                int(base_color[2] * alpha_ratio * 0.3)
            )
            draw.ellipse(
                [center_x - radius - w, center_y - radius - w,
                 center_x + radius + w, center_y + radius + w],
                outline=color_var,
                width=1
            )
        # Main ring
        color_var = (
            int((i * 40 + base_color[0]) % 256),
            int((i * 60 + 100 + base_color[1]) % 256),
            int((i * 80 + 50 + base_color[2]) % 256)
        )
        draw.ellipse(
            [center_x - radius, center_y - radius, center_x + radius, center_y + radius],
            outline=color_var,
            width=2
        )

    # Draw radial lines based on MFCC features
    if mfcc_means and len(mfcc_means) >= 6:
        num_lines = min(len(mfcc_means), 12)
        for i in range(num_lines):
            angle = (i / num_lines) * 2 * math.pi - math.pi / 2  # Start from top
            # Use MFCC value to determine line length
            length = 100 + abs(mfcc_means[i % len(mfcc_means)]) * 60
            length = min(length, 200)

            start_x = center_x + int(30 * math.cos(angle))
            start_y = center_y + int(30 * math.sin(angle))
            end_x = center_x + int(length * math.cos(angle))
            end_y = center_y + int(length * math.sin(angle))

            # Gradient line with glow
            for w in range(3):
                alpha_ratio = 1 - (w / 3)
                line_color = (
                    int(((i / num_lines) * 180 + 50) * alpha_ratio),
                    int((base_color[1] * 0.8 + 40) * alpha_ratio),
                    int(((1 - i / num_lines) * 180 + 50) * alpha_ratio)
                )
                draw.line([(start_x, start_y), (end_x, end_y)], fill=line_color, width=2)

    # Draw chroma circles with pulse effect
    if chroma_means and len(chroma_means) >= 12:
        for i, chroma_val in enumerate(chroma_means[:12]):
            angle = (i / 12) * 2 * math.pi - math.pi / 2
            radius = 160 + chroma_val * 60

            x = center_x + int(radius * math.cos(angle))
            y = center_y + int(radius * math.sin(angle))

            # Outer glow
            for w in range(4):
                circle_size = 8 + int(chroma_val * 12) + w
                alpha_ratio = 1 - (w / 4)
                circle_color = (
                    int((i / 12) * 200 * alpha_ratio),
                    int(chroma_val * 200 * alpha_ratio),
                    int((1 - chroma_val) * 200 * alpha_ratio)
                )
                draw.ellipse(
                    [x - circle_size, y - circle_size, x + circle_size, y + circle_size],
                    fill=circle_color
                )

    # Draw central glowing dot
    for w in range(10, 0, -1):
        alpha = w / 10
        glow_color = (
            int(base_color[0] * alpha),
            int(base_color[1] * alpha),
            int(base_color[2] * alpha)
        )
        draw.ellipse(
            [center_x - w * 2, center_y - w * 2, center_x + w * 2, center_y + w * 2],
            fill=glow_color
        )
    draw.ellipse(
        [center_x - 8, center_y - 8, center_x + 8, center_y + 8],
        fill=base_color
    )

    # Add text labels with better styling
    try:
        font_small = ImageFont.truetype("arial.ttf", 14)
        font_medium = ImageFont.truetype("arial.ttf", 18)
        font_large = ImageFont.truetype("arial.ttf", 22)
    except:
        font_small = ImageFont.load_default()
        font_medium = ImageFont.load_default()
        font_large = ImageFont.load_default()

    # Title area with semi-transparent background
    draw.rectangle([(0, 0), (width, 70)], fill=(0, 0, 0))
    draw.text((50, 15), f"♫ {title}", fill=(255, 255, 255), font=font_large)
    draw.text((50, 45), f"by {artist}", fill=(140, 160, 180), font=font_small)

    # Feature labels at bottom
    draw.rectangle([(0, height - 60), (width, height)], fill=(0, 0, 0))
    draw.text((50, height - 50), f"♪ {bpm:.0f} BPM", fill=(100, 150, 255), font=font_small)
    draw.text((200, height - 50), f"⚡ {energy:.2f}", fill=(255, 150, 100), font=font_small)
    draw.text((350, height - 50), f"☺ {valence:.2f}", fill=(100, 255, 150), font=font_small)

    # Branding
    draw.text((width - 160, height - 50), "Musical DNA", fill=(60, 70, 80), font=font_small)

    # Save to bytes
    buffer = io.BytesIO()
    img.save(buffer, format='PNG', optimize=True)
    buffer.seek(0)

    log.info("[DNA] generated for %s - %s (%d bytes)", title, artist, len(buffer.getvalue()))
    return buffer.getvalue()
