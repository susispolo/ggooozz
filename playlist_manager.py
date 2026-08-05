"""
Playlist generation and management.
Creates playlists based on similar tracks with smooth energy arcs.
"""
import logging
from dataclasses import dataclass

log = logging.getLogger(__name__)


@dataclass
class PlaylistTrack:
    """Track in a playlist."""
    track_id: int
    title: str
    artist: str
    energy: float = 0.0
    bpm: float = 0.0
    preview_url: str = ""


def calculate_energy_score(audio_features, acoustic_features) -> float:
    """Calculate energy score (0-1) from features."""
    score = 0.5

    if audio_features:
        # RMS energy contributes 60%
        score += audio_features.rms_energy * 0.3
        # BPM contributes 40%
        if audio_features.bpm > 0:
            bpm_norm = min(audio_features.bpm / 180.0, 1.0)
            score += bpm_norm * 0.2

    if acoustic_features:
        # AcousticBrainz energy contributes
        score += acoustic_features.energy * 0.2

    score = min(max(score, 0.0), 1.0)
    log.info("[PLAYLIST] calculate_energy_score -> %.3f (audio=%s acoustic=%s)",
             score, bool(audio_features), bool(acoustic_features))
    return score


def sort_by_energy_arc(tracks: list[PlaylistTrack]) -> list[PlaylistTrack]:
    """
    Sort tracks to create a smooth energy arc:
    - Start with medium energy
    - Build up to high energy
    - End with lower energy (cool down)
    """
    if len(tracks) <= 2:
        return tracks

    # Sort by energy
    sorted_tracks = sorted(tracks, key=lambda t: t.energy)

    # Split into thirds
    n = len(sorted_tracks)
    low = sorted_tracks[:n//3]
    mid = sorted_tracks[n//3:2*n//3]
    high = sorted_tracks[2*n//3:]

    # Build arc: mid -> high -> low
    result = mid + high + low

    log.info("[PLAYLIST] sort_by_energy_arc: %d tracks -> order energies: %s",
             len(result), [round(t.energy, 2) for t in result])
    return result


def create_playlist_name(seed_track: str) -> str:
    """Generate a playlist name from seed track."""
    return f"Similar to {seed_track}"


async def generate_playlist(
    seed_track: dict,
    similar_tracks: list[dict],
    max_tracks: int = 10,
) -> list[PlaylistTrack]:
    """
    Generate a playlist from a seed track and similar tracks.

    Args:
        seed_track: dict with title, artist, energy, bpm, preview_url
        similar_tracks: list of dicts with track info and features
        max_tracks: maximum tracks in playlist

    Returns:
        List of PlaylistTrack sorted by energy arc
    """
    tracks = []

    # Add seed track
    tracks.append(PlaylistTrack(
        track_id=seed_track.get("track_id", 0),
        title=seed_track.get("title", ""),
        artist=seed_track.get("artist", ""),
        energy=seed_track.get("energy", 0.5),
        bpm=seed_track.get("bpm", 0),
        preview_url=seed_track.get("preview_url", ""),
    ))

    # Add similar tracks
    for t in similar_tracks[:max_tracks - 1]:
        tracks.append(PlaylistTrack(
            track_id=t.get("track_id", 0),
            title=t.get("title", ""),
            artist=t.get("artist", ""),
            energy=t.get("energy", 0.5),
            bpm=t.get("bpm", 0),
            preview_url=t.get("preview_url", ""),
        ))

    # Sort by energy arc
    result = sort_by_energy_arc(tracks)
    log.info("[PLAYLIST] generate_playlist seed=%r max_tracks=%s -> %d tracks",
             seed_track.get("title", ""), max_tracks, len(result[:max_tracks]))
    return result[:max_tracks]


def format_playlist_text(tracks: list[PlaylistTrack], name: str = "") -> str:
    """Format playlist as text for Telegram."""
    lines = []
    if name:
        lines.append(f"🎵 <b>{name}</b>")
        lines.append("")

    for i, track in enumerate(tracks, 1):
        energy_bar = "█" * int(track.energy * 10) + "░" * (10 - int(track.energy * 10))
        lines.append(f"{i}. <b>{track.title}</b> - {track.artist}")
        lines.append(f"   <code>[{energy_bar}]</code> {track.bpm:.0f} BPM")
        lines.append("")

    return "\n".join(lines)
