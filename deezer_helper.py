"""
Deezer API client - completely free, no API key required.
Async version using aiohttp.
"""
from dataclasses import dataclass, field
from typing import Optional
import asyncio
import logging
import aiohttp

log = logging.getLogger(__name__)


@dataclass
class TrackInfo:
    id: int
    title: str
    artist: str
    artist_id: int
    album: str
    album_art: Optional[str]
    duration: int
    bpm: Optional[float] = None
    explicit: bool = False
    deezer_url: str = ""
    preview_url: Optional[str] = None
    genres: list[str] = field(default_factory=list)
    lastfm_match: float = 0.0  # similarity score from Last.fm (0-1), set by bot.py
    release_date: str = ""  # e.g. "1975-10-31" (from Deezer track endpoint)

    def release_year(self) -> int:
        """Extract release year (0 if unknown)."""
        if not self.release_date:
            return 0
        try:
            return int(self.release_date[:4])
        except (ValueError, TypeError):
            return 0

    def bpm_str(self) -> str:
        return f"{self.bpm:.0f} BPM" if self.bpm else "-"

    def duration_str(self) -> str:
        m, s = divmod(self.duration, 60)
        return f"{m}:{s:02d}"


class DeezerClient:
    BASE = "https://api.deezer.com"
    MAX_RETRIES = 3
    RETRY_DELAY = 1.0

    def __init__(self):
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=15)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def _request_with_retry(self, url: str, params: dict = None) -> dict:
        session = await self._get_session()
        log.debug("[DEEZER] GET %s params=%s", url, params)
        for attempt in range(self.MAX_RETRIES):
            try:
                async with session.get(url, params=params) as resp:
                    log.debug("[DEEZER] %s -> status=%s (attempt %d)", url, resp.status, attempt + 1)
                    if resp.status == 429:
                        # Rate limited - exponential backoff
                        delay = self.RETRY_DELAY * (2 ** attempt)
                        log.warning("[DEEZER] rate-limited on %s, backing off %.1fs", url, delay)
                        await asyncio.sleep(delay)
                        continue
                    if resp.status == 200:
                        data = await resp.json()
                        log.debug("[DEEZER] %s -> %d bytes of json", url, len(str(data)))
                        return data
                    # Other errors - retry once
                    if attempt < self.MAX_RETRIES - 1:
                        log.warning("[DEEZER] %s status=%s retrying", url, resp.status)
                        await asyncio.sleep(self.RETRY_DELAY)
                        continue
                    log.error("[DEEZER] %s failed after %d attempts (status=%s)", url, self.MAX_RETRIES, resp.status)
                    return {}
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                if attempt < self.MAX_RETRIES - 1:
                    log.warning("[DEEZER] %s error=%s retrying", url, e)
                    await asyncio.sleep(self.RETRY_DELAY)
                    continue
                log.error("[DEEZER] %s failed after %d attempts (error=%s)", url, self.MAX_RETRIES, e)
                return {}
        return {}

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    async def search(self, query: str, limit: int = 5) -> list[TrackInfo]:
        log.info("[DEEZER] search query=%r limit=%s", query, limit)
        data = await self._request_with_retry(
            f"{self.BASE}/search/track",
            params={"q": query, "limit": limit, "order": "RANKING"}
        )
        results = [self._parse_track(t) for t in data.get("data", [])]
        log.info("[DEEZER] search query=%r -> %d results", query, len(results))
        return results

    async def get_track(self, track_id: int) -> Optional[TrackInfo]:
        log.info("[DEEZER] get_track id=%s", track_id)
        data = await self._request_with_retry(f"{self.BASE}/track/{track_id}")
        if not data:
            log.warning("[DEEZER] get_track id=%s -> no data", track_id)
            return None
        track = self._parse_track(data)

        # Get genres
        artist_data = await self._request_with_retry(f"{self.BASE}/artist/{track.artist_id}")
        if artist_data:
            for g in artist_data.get("genres", {}).get("data", []):
                track.genres.append(g["name"])
        log.info("[DEEZER] get_track id=%s -> %s - %s (genres=%s)", track_id, track.artist, track.title, track.genres)
        return track

    async def get_similar(self, track_id: int, limit: int = 10) -> list[TrackInfo]:
        log.info("[DEEZER] get_similar id=%s limit=%s", track_id, limit)
        data = await self._request_with_retry(
            f"{self.BASE}/track/{track_id}/radio",
            params={"limit": limit}
        )
        results = [self._parse_track(t) for t in data.get("data", [])] if data else []
        log.info("[DEEZER] get_similar id=%s -> %d results", track_id, len(results))
        return results

    async def get_artist_top(self, artist_id: int, limit: int = 10) -> list[TrackInfo]:
        log.info("[DEEZER] get_artist_top id=%s limit=%s", artist_id, limit)
        data = await self._request_with_retry(
            f"{self.BASE}/artist/{artist_id}/top",
            params={"limit": limit}
        )
        results = [self._parse_track(t) for t in data.get("data", [])] if data else []
        log.info("[DEEZER] get_artist_top id=%s -> %d results", artist_id, len(results))
        return results

    @staticmethod
    def _parse_track(raw: dict) -> TrackInfo:
        album_art = raw.get("album", {}).get("cover_medium") or raw.get("album", {}).get("cover")
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
            release_date=raw.get("release_date", ""),
        )
