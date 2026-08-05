"""
Lyrics API client.
Fetches lyrics from free APIs.
"""
import logging
from dataclasses import dataclass
from typing import Optional

import aiohttp

log = logging.getLogger(__name__)


@dataclass
class LyricsResult:
    """Lyrics search result."""
    title: str
    artist: str
    lyrics: str = ""
    url: str = ""


class LyricsClient:
    """Client for lyrics APIs."""

    # lyrics.ovh - free, no key needed
    BASE = "https://api.lyrics.ovh"

    def __init__(self):
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=10, connect=5)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def get_lyrics(self, artist: str, title: str) -> Optional[LyricsResult]:
        """
        Get lyrics for a track.
        Returns LyricsResult or None.
        """
        session = await self._get_session()

        try:
            async with session.get(f"{self.BASE}/v1/{artist}/{title}") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    lyrics = data.get("lyrics", "")
                    if lyrics:
                        log.info("Found lyrics for %s - %s", artist, title)
                        return LyricsResult(
                            title=title,
                            artist=artist,
                            lyrics=lyrics,
                        )
                elif resp.status == 404:
                    log.info("No lyrics found for %s - %s", artist, title)
                    return None
                else:
                    log.warning("Lyrics API error: %s", resp.status)
                    return None

        except Exception as e:
            log.error("Lyrics fetch error: %s", e)
            return None

    async def search_lyrics(self, query: str, limit: int = 5) -> list[LyricsResult]:
        """
        Search for lyrics by text query.
        Returns list of matching results.
        """
        session = await self._get_session()

        try:
            async with session.get(f"{self.BASE}/suggest/{query}") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    results = []

                    for item in data.get("data", [])[:limit]:
                        results.append(LyricsResult(
                            title=item.get("title", ""),
                            artist=item.get("artist", {}).get("name", ""),
                        ))

                    log.info("Found %d lyrics results for: %s", len(results), query)
                    return results

                else:
                    log.warning("Lyrics search error: %s", resp.status)
                    return []

        except Exception as e:
            log.error("Lyrics search error: %s", e)
            return []

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()


def format_lyrics(lyrics: LyricsResult, max_chars: int = 3000) -> str:
    """Format lyrics for Telegram display (with collapsible blockquote)."""
    lines = [
        f"🎤 <b>{lyrics.title}</b>",
        f"👤 {lyrics.artist}",
        "",
    ]

    # Truncate if too long
    text = lyrics.lyrics
    if len(text) > max_chars:
        text = text[:max_chars] + "..."

    # Wrap in blockquote for collapsible display
    lines.append(f"<blockquote>{text}</blockquote>")

    return "\n".join(lines)
