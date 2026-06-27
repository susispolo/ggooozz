"""Quick smoke test for the bot modules."""
from spotify_helper import SpotifyClient, TrackInfo
from deezer_helper import DeezerClient

print("All imports OK")

t = TrackInfo(
    id="abc",
    name="Test Song",
    artists=["A", "B"],
    album="Album",
    album_art=None,
    duration_ms=200000,
    spotify_url="https://open.spotify.com/track/abc",
)
print(f"TrackInfo: {t.name} by {t.artist_str()}")
print(f"bpm: {t.bpm_str()}, key: {t.key_str()}")
print("All local tests passed")
