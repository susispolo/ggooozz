"""
Last.fm API client.
Gets tags, similar tracks, and collaborative filtering data.
"""
import asyncio
import logging
from dataclasses import dataclass, field
from typing import Optional

import aiohttp

log = logging.getLogger(__name__)


@dataclass
class LastfmTrackInfo:
    """Track info from Last.fm."""
    name: str = ""
    artist: str = ""
    tags: list[str] = field(default_factory=list)
    playcount: int = 0
    listeners: int = 0


@dataclass
class LastfmSimilarTrack:
    """Similar track from Last.fm."""
    name: str = ""
    artist: str = ""
    match: float = 0.0  # 0.0 to 1.0 similarity score


class LastfmClient:
    """Client for Last.fm API."""

    BASE = "https://ws.audioscrobbler.com/2.0/"

    def __init__(self, api_key: str):
        self.api_key = api_key
        self._session: Optional[aiohttp.ClientSession] = None
        self._last_request_time = 0.0

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=8, connect=5)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def _rate_limit(self):
        """Ensure we don't exceed Last.fm rate limit (5 req/sec)."""
        now = asyncio.get_event_loop().time()
        elapsed = now - self._last_request_time
        if elapsed < 0.2:  # 5 req/sec = 0.2s between requests
            await asyncio.sleep(0.2 - elapsed)
        self._last_request_time = asyncio.get_event_loop().time()

    async def get_track_info(self, artist: str, track: str) -> Optional[LastfmTrackInfo]:
        """
        Get track info including tags from Last.fm.
        Returns LastfmTrackInfo or None.
        """
        await self._rate_limit()

        session = await self._get_session()
        params = {
            "method": "track.getInfo",
            "api_key": self.api_key,
            "artist": artist,
            "track": track,
            "format": "json",
        }

        try:
            async with session.get(self.BASE, params=params) as resp:
                if resp.status != 200:
                    log.warning("Last.fm track.getInfo failed: %s", resp.status)
                    return None

                data = await resp.json()
                track_data = data.get("track", {})

                if not track_data:
                    return None

                # Extract tags
                tags = []
                toptags = track_data.get("toptags", {}).get("tag", [])
                for tag in toptags:
                    tags.append(tag.get("name", ""))

                return LastfmTrackInfo(
                    name=track_data.get("name", ""),
                    artist=artist,
                    tags=tags,
                    playcount=int(track_data.get("playcount", 0)),
                    listeners=int(track_data.get("listeners", 0)),
                )

        except Exception as e:
            log.error("Last.fm track info error: %s", e)
            return None

    async def get_artist_top_tags(self, artist: str) -> list[str]:
        """
        Get top tags for an artist from Last.fm.
        Returns list of tag names (genres/moods).
        """
        await self._rate_limit()

        session = await self._get_session()
        params = {
            "method": "artist.getTopTags",
            "api_key": self.api_key,
            "artist": artist,
            "format": "json",
        }

        try:
            async with session.get(self.BASE, params=params) as resp:
                if resp.status != 200:
                    log.warning("Last.fm artist.getTopTags failed: %s", resp.status)
                    return []

                data = await resp.json()
                toptags = data.get("toptags", {}).get("tag", [])

                tags = []
                for tag in toptags[:10]:  # Top 10 tags
                    tag_name = tag.get("name", "")
                    if tag_name:
                        tags.append(tag_name)

                log.info("Last.fm artist tags for %s: %s", artist, tags[:5])
                return tags

        except Exception as e:
            log.error("Last.fm artist tags error: %s", e)
            return []

    async def get_similar_tracks(self, artist: str, track: str, limit: int = 10) -> list[LastfmSimilarTrack]:
        """
        Get similar tracks based on user listening behavior.
        Returns list of LastfmSimilarTrack.
        """
        await self._rate_limit()

        session = await self._get_session()
        params = {
            "method": "track.getSimilar",
            "api_key": self.api_key,
            "artist": artist,
            "track": track,
            "format": "json",
            "limit": limit,
            "autocorrect": 1,
        }

        try:
            async with session.get(self.BASE, params=params) as resp:
                if resp.status != 200:
                    log.warning("Last.fm track.getSimilar failed: %s", resp.status)
                    return []

                data = await resp.json()
                similar = data.get("similartracks", {}).get("track", [])

                results = []
                for t in similar:
                    match = float(t.get("match", 0))
                    results.append(LastfmSimilarTrack(
                        name=t.get("name", ""),
                        artist=t.get("artist", {}).get("name", ""),
                        match=match,
                    ))

                log.info("Last.fm found %d similar tracks for %s - %s", len(results), artist, track)
                return results

        except Exception as e:
            log.error("Last.fm similar tracks error: %s", e)
            return []

    async def get_artist_top_tracks(self, artist: str, limit: int = 10) -> list[str]:
        """Get top tracks for an artist."""
        await self._rate_limit()

        session = await self._get_session()
        params = {
            "method": "artist.getTopTracks",
            "api_key": self.api_key,
            "artist": artist,
            "format": "json",
            "limit": limit,
        }

        try:
            async with session.get(self.BASE, params=params) as resp:
                if resp.status != 200:
                    return []

                data = await resp.json()
                tracks = data.get("toptracks", {}).get("track", [])
                return [t.get("name", "") for t in tracks]

        except Exception as e:
            log.error("Last.fm artist top tracks error: %s", e)
            return []

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()
