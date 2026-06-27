"""
Deezer API client — completely free, no API key required.
───────────────────────────────────────────────────────
Provides: search, track details (BPM, genre, preview),
          track-to-track radio (similar tracks).
"""
from dataclasses import dataclass, field
from typing import Optional

import requests


@dataclass
class TrackInfo:
    """Normalised track info from Deezer."""
    id: int
    title: str
    artist: str
    artist_id: int
    album: str
    album_art: Optional[str]      # 500x500 cover
    duration: int                  # seconds
    bpm: Optional[float] = None
    explicit: bool = False
    deezer_url: str = ""
    preview_url: Optional[str] = None   # 30s legal MP3 preview
    genres: list[str] = field(default_factory=list)

    def bpm_str(self) -> str:
        return f"{self.bpm:.0f} BPM" if self.bpm else "—"

    def duration_str(self) -> str:
        m, s = divmod(self.duration, 60)
        return f"{m}:{s:02d}"


class DeezerClient:
    """Free, no-auth Deezer API."""

    BASE = "https://api.deezer.com"

    def search(self, query: str, limit: int = 5) -> list[TrackInfo]:
        """Search tracks. Results are relevance-ranked — serves as 'did you mean?'."""
        r = requests.get(
            f"{self.BASE}/search/track",
            params={"q": query, "limit": limit, "order": "RANKING"},
            timeout=15,
        )
        r.raise_for_status()
        data = r.json()
        return [self._parse_track(t) for t in data.get("data", [])]

    def get_track(self, track_id: int) -> Optional[TrackInfo]:
        """Get full track details including BPM, genres."""
        r = requests.get(f"{self.BASE}/track/{track_id}", timeout=15)
        if r.status_code != 200:
            return None
        t = r.json()
        track = self._parse_track(t)

        # Get artist genres
        try:
            ar = requests.get(f"{self.BASE}/artist/{track.artist_id}", timeout=15)
            if ar.status_code == 200:
                artist_data = ar.json()
                for g in artist_data.get("genres", {}).get("data", []):
                    track.genres.append(g["name"])
        except Exception:
            pass

        return track

    def get_similar(self, track_id: int, limit: int = 10) -> list[TrackInfo]:
        """
        Deezer's 'radio' endpoint — gives tracks similar to a seed track.
        This is Deezer's own similarity engine (free).
        """
        r = requests.get(
            f"{self.BASE}/track/{track_id}/radio",
            params={"limit": limit},
            timeout=15,
        )
        if r.status_code != 200:
            return []
        data = r.json()
        return [self._parse_track(t) for t in data.get("data", [])]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _parse_track(raw: dict) -> TrackInfo:
        images = raw.get("album", {}).get("cover", {})
        # Deezer returns cover_xl, cover_big, cover_medium, cover_small
        album_art = raw.get("album", {}).get("cover_medium") or raw.get("album", {}).get("cover")
        # Fallback
        if not album_art and isinstance(images, str):
            album_art = images

        return TrackInfo(
            id=raw.get("id", 0),
            title=raw.get("title", "") or raw.get("title_short", ""),
            artist=raw.get("artist", {}).get("name", "Unknown"),
            artist_id=raw.get("artist", {}).get("id", 0),
            album=raw.get("album", {}).get("title", ""),
            album_art=album_art,
            duration=raw.get("duration", 0),
            bpm=raw.get("bpm"),
            explicit=raw.get("explicit", False),
            deezer_url=raw.get("link", ""),
            preview_url=raw.get("preview"),
        )
