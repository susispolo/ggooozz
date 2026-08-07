"""
MusicBrainz + AcousticBrainz API client.
Gets recording IDs and 200+ acoustic features.
"""
import asyncio
import logging
from dataclasses import dataclass, field
from typing import Optional

import aiohttp

log = logging.getLogger(__name__)


@dataclass
class AcousticBrainzFeatures:
    """Features from AcousticBrainz API."""
    # High-level
    danceability: float = 0.0
    energy: float = 0.0
    valence: float = 0.0
    acousticness: float = 0.0
    instrumentalness: float = 0.0
    speechiness: float = 0.0

    # Mood tags
    mood_happy: float = 0.0
    mood_sad: float = 0.0
    mood_aggressive: float = 0.0
    mood_relaxed: float = 0.0
    mood_party: float = 0.0

    # Genre tags
    genre_rock: float = 0.0
    genre_pop: float = 0.0
    genre_jazz: float = 0.0
    genre_electronic: float = 0.0
    genre_hip_hop: float = 0.0

    # Low-level
    bpm: float = 0.0
    key: str = ""
    mode: str = ""  # major/minor
    loudness: float = 0.0

    def to_dict(self) -> dict:
        return {
            "danceability": self.danceability,
            "energy": self.energy,
            "valence": self.valence,
            "acousticness": self.acousticness,
            "instrumentalness": self.instrumentalness,
            "speechiness": self.speechiness,
            "mood_happy": self.mood_happy,
            "mood_sad": self.mood_sad,
            "mood_aggressive": self.mood_aggressive,
            "mood_relaxed": self.mood_relaxed,
            "mood_party": self.mood_party,
            "genre_rock": self.genre_rock,
            "genre_pop": self.genre_pop,
            "genre_jazz": self.genre_jazz,
            "genre_electronic": self.genre_electronic,
            "genre_hip_hop": self.genre_hip_hop,
            "bpm": self.bpm,
            "key": self.key,
            "mode": self.mode,
            "loudness": self.loudness,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AcousticBrainzFeatures":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class MusicBrainzClient:
    """Client for MusicBrainz + AcousticBrainz APIs."""

    MUSICBRAINZ_BASE = "https://musicbrainz.org/ws/2"
    ACOUSTICBRAINZ_BASE = "https://acousticbrainz.org/api/v1"

    def __init__(self):
        self._session: Optional[aiohttp.ClientSession] = None
        self._last_request_time = 0.0

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=10, connect=5)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def _rate_limit(self):
        """Ensure we don't exceed MusicBrainz rate limit (1 req/sec)."""
        now = asyncio.get_event_loop().time()
        elapsed = now - self._last_request_time
        if elapsed < 1.0:
            await asyncio.sleep(1.0 - elapsed)
        self._last_request_time = asyncio.get_event_loop().time()

    async def search_recording(self, artist: str, track: str) -> Optional[str]:
        """
        Search MusicBrainz for a recording and return its ID.
        Returns MusicBrainz recording ID or None.
        """
        await self._rate_limit()

        session = await self._get_session()
        params = {
            "query": f'artist:"{artist}" AND recording:"{track}"',
            "fmt": "json",
            "limit": 1,
        }

        try:
            async with session.get(f"{self.MUSICBRAINZ_BASE}/recording/", params=params) as resp:
                if resp.status != 200:
                    log.warning("MusicBrainz search failed: %s", resp.status)
                    return None

                data = await resp.json()
                recordings = data.get("recordings", [])

                if recordings:
                    mbid = recordings[0]["id"]
                    log.info("Found MusicBrainz ID: %s for %s - %s", mbid, artist, track)
                    return mbid

                log.info("No MusicBrainz recording found for %s - %s", artist, track)
                return None

        except Exception as e:
            log.error("MusicBrainz search error: %s", e)
            return None

    async def get_acoustic_features(self, musicbrainz_id: str) -> Optional[AcousticBrainzFeatures]:
        """
        Get acoustic features from AcousticBrainz using MusicBrainz ID.
        Returns AcousticBrainzFeatures or None.
        """
        session = await self._get_session()

        # Get high-level features
        highlevel = {}
        try:
            async with session.get(f"{self.ACOUSTICBRAINZ_BASE}/{musicbrainz_id}/highlevel") as resp:
                if resp.status == 200:
                    highlevel = await resp.json()
        except Exception as e:
            log.warning("AcousticBrainz highlevel error: %s", e)

        # Get low-level features
        lowlevel = {}
        try:
            async with session.get(f"{self.ACOUSTICBRAINZ_BASE}/{musicbrainz_id}/lowlevel") as resp:
                if resp.status == 200:
                    lowlevel = await resp.json()
        except Exception as e:
            log.warning("AcousticBrainz lowlevel error: %s", e)

        if not highlevel and not lowlevel:
            return None

        return self._parse_features(highlevel, lowlevel)

    def _parse_features(self, highlevel: dict, lowlevel: dict) -> AcousticBrainzFeatures:
        """Parse AcousticBrainz response into features."""
        features = AcousticBrainzFeatures()

        # High-level features
        hl = highlevel.get("highlevel", {})

        # Helper to safely extract value
        def safe_value(data, key, default=0.0):
            """Safely extract value from AcousticBrainz response."""
            if key not in data:
                return default
            val = data[key]
            if isinstance(val, dict):
                return val.get("value", default)
            elif isinstance(val, (int, float)):
                return float(val)
            elif isinstance(val, str):
                try:
                    return float(val)
                except ValueError:
                    return default
            return default

        # Danceability
        features.danceability = safe_value(hl, "danceability")

        # Energy
        features.energy = safe_value(hl, "energy")

        # Valence (happiness)
        features.valence = safe_value(hl, "valence")

        # Acousticness
        features.acousticness = safe_value(hl, "acoustic")

        # Instrumentalness
        features.instrumentalness = safe_value(hl, "instrumental")

        # Speechiness
        features.speechiness = safe_value(hl, "speechiness")

        # Mood tags
        features.mood_happy = safe_value(hl, "mood_happy")
        features.mood_sad = safe_value(hl, "mood_sad")
        features.mood_aggressive = safe_value(hl, "mood_aggressive")
        features.mood_relaxed = safe_value(hl, "mood_relaxed")
        features.mood_party = safe_value(hl, "mood_party")

        # Genre tags
        genre = safe_value(hl, "genre_rosamerica", "")
        if genre == "rock":
            features.genre_rock = 1.0
        elif genre == "pop":
            features.genre_pop = 1.0
        elif genre == "jazz":
            features.genre_jazz = 1.0
        elif genre == "electronic":
            features.genre_electronic = 1.0
        elif genre == "hip_hop":
            features.genre_hip_hop = 1.0

        # Low-level features
        ll = lowlevel.get("lowlevel", {})

        # BPM
        if "bpm" in ll:
            features.bpm = ll["bpm"]

        # Key
        if "key" in ll:
            features.key = ll["key"].get("key", "")
            features.mode = ll["key"].get("mode", "")

        # Loudness
        if "loudness" in ll:
            features.loudness = ll["loudness"].get("value", 0.0)

        return features

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()
