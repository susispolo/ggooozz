"""
User taste profiling and personalized recommendations.
Analyzes user's listening history to build taste fingerprint.
"""
import logging
from dataclasses import dataclass, field

log = logging.getLogger(__name__)


@dataclass
class TasteProfile:
    """User's taste fingerprint."""
    avg_bpm: float = 0.0
    avg_energy: float = 0.0
    avg_valence: float = 0.0
    avg_danceability: float = 0.0
    top_genres: list[str] = field(default_factory=list)
    top_artists: list[str] = field(default_factory=list)
    mood_distribution: dict = field(default_factory=dict)
    total_ratings: int = 0
    avg_rating: float = 0.0


def calculate_mood(valence: float, energy: float) -> str:
    """Calculate mood from valence and energy."""
    if valence > 0.6 and energy > 0.6:
        return "happy"
    elif valence > 0.6 and energy < 0.4:
        return "calm"
    elif valence < 0.4 and energy > 0.6:
        return "angry"
    elif valence < 0.4 and energy < 0.4:
        return "sad"
    else:
        return "neutral"


def build_taste_profile(
    votes: list[dict],
    audio_features_cache: dict,
) -> TasteProfile:
    """Build taste profile from user's voting history.

    Args:
        votes: list of dicts with track_id, rating
        audio_features_cache: dict mapping track_id to features

    Returns:
        TasteProfile
    """
    log.info("[TASTE] build_taste_profile: %d votes, %d cached features",
             len(votes), len(audio_features_cache))
    profile = TasteProfile()

    if not votes:
        return profile

    total_bpm = 0
    total_energy = 0
    total_valence = 0
    total_danceability = 0
    feature_count = 0
    mood_counts = {}

    for vote in votes:
        track_id = vote.get("track_id")
        features = audio_features_cache.get(track_id)

        if features:
            audio = features.get("audio_features")
            acoustic = features.get("acoustic_features")

            if audio:
                if audio.bpm > 0:
                    total_bpm += audio.bpm
                total_energy += audio.rms_energy
                feature_count += 1

            if acoustic:
                total_valence += acoustic.valence
                total_danceability += acoustic.danceability

                # Track mood
                mood = calculate_mood(acoustic.valence, acoustic.energy)
                mood_counts[mood] = mood_counts.get(mood, 0) + 1

    if feature_count > 0:
        profile.avg_bpm = total_bpm / feature_count
        profile.avg_energy = total_energy / feature_count
        profile.avg_valence = total_valence / feature_count
        profile.avg_danceability = total_danceability / feature_count

    profile.mood_distribution = mood_counts
    profile.total_ratings = len(votes)

    # Calculate average rating
    ratings = [v.get("rating", 0) for v in votes]
    profile.avg_rating = sum(ratings) / len(ratings) if ratings else 0

    log.info("[TASTE] profile done: bpm=%.1f energy=%.2f valence=%.2f dance=%.2f ratings=%d avg_rating=%.2f moods=%s",
             profile.avg_bpm, profile.avg_energy, profile.avg_valence, profile.avg_danceability,
             profile.total_ratings, profile.avg_rating, profile.mood_distribution)
    return profile


def format_taste_profile(profile: TasteProfile, username: str = "") -> str:
    """Format taste profile for Telegram display."""
    lines = []

    if username:
        lines.append(f"🎵 <b>{username}'s Music Taste</b>")
    else:
        lines.append("🎵 <b>Your Music Taste</b>")
    lines.append("")

    # Stats
    lines.append("━━━ <b>Your Stats</b> ━━━")
    lines.append(f"📊 Total ratings: {profile.total_ratings}")
    lines.append(f"⭐ Average rating: {profile.avg_rating:.1f}/5")
    lines.append("")

    # Audio preferences
    lines.append("━━━ <b>Audio Preferences</b> ━━━")

    # BPM preference
    if profile.avg_bpm > 0:
        bpm_label = "Fast" if profile.avg_bpm > 120 else "Medium" if profile.avg_bpm > 90 else "Slow"
        bpm_bar = "█" * int(profile.avg_bpm / 200 * 10) + "░" * (10 - int(profile.avg_bpm / 200 * 10))
        lines.append(f"🥁 Preferred tempo: {bpm_label} ({profile.avg_bpm:.0f} BPM)")
        lines.append(f"   <code>[{bpm_bar}]</code>")
    lines.append("")

    # Energy preference
    energy_bar = "█" * int(profile.avg_energy * 10) + "░" * (10 - int(profile.avg_energy * 10))
    energy_label = "High" if profile.avg_energy > 0.6 else "Medium" if profile.avg_energy > 0.3 else "Low"
    lines.append(f"⚡ Energy level: {energy_label}")
    lines.append(f"   <code>[{energy_bar}]</code>")
    lines.append("")

    # Mood distribution
    if profile.mood_distribution:
        lines.append("━━━ <b>Mood Distribution</b> ━━━")
        mood_emojis = {
            "happy": "😊", "calm": "😌", "sad": "😢",
            "angry": "😤", "neutral": "😐"
        }
        total_moods = sum(profile.mood_distribution.values())
        for mood, count in sorted(profile.mood_distribution.items(), key=lambda x: x[1], reverse=True):
            emoji = mood_emojis.get(mood, "🎵")
            pct = int(count / total_moods * 100) if total_moods > 0 else 0
            bar = "█" * (pct // 10) + "░" * (10 - pct // 10)
            lines.append(f"{emoji} {mood.capitalize()}: {pct}%")
            lines.append(f"   <code>[{bar}]</code>")
        lines.append("")

    return "\n".join(lines)


def get_recommendation_weights(profile: TasteProfile) -> dict:
    """
    Get weights for similarity scoring based on user's taste.
    Emphasizes features the user cares about.
    """
    weights = {
        "timbre": 0.35,
        "tempo": 0.20,
        "energy": 0.15,
        "valence": 0.15,
        "dance": 0.10,
        "lastfm": 0.05,
    }

    # If user prefers fast music, increase tempo weight
    if profile.avg_bpm > 120:
        weights["tempo"] = 0.25
        weights["energy"] = 0.20
        weights["timbre"] = 0.30

    # If user prefers high energy, increase energy weight
    if profile.avg_energy > 0.6:
        weights["energy"] = 0.20
        weights["tempo"] = 0.20
        weights["timbre"] = 0.30

    return weights
