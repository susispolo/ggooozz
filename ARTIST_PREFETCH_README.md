# Artist-Based Prefetch System

## Overview

This is a comprehensive prefetch system that fetches **all songs** from **top artists** across multiple genres, then pre-analyzes everything including finding 5 similar songs for each track. This makes the bot responses nearly instant for popular music.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  ARTIST PREFETCH SYSTEM (Continuous Background Process)         │
│                                                                 │
│  FOR EACH GENRE:                                                │
│  ├─ Pop: 200 artists                                            │
│  ├─ Rap: 100 artists                                            │
│  ├─ Persian: 100 artists                                        │
│  └─ Rock: 100 artists                                           │
│                                                                 │
│  FOR EACH ARTIST:                                               │
│  ├─ Fetch ALL songs (could be 10-500+ songs per artist)         │
│  │                                                              │
│  │  FOR EACH SONG:                                              │
│  │  ├─ Full audio analysis (librosa)                            │
│  │  ├─ MusicBrainz/AcousticBrainz features                      │
│  │  ├─ Last.fm tags                                             │
│  │  ├─ Cache to database                                        │
│  │  │                                                           │
│  │  └─ Find 5 SIMILAR SONGS:                                   │
│  │      ├─ Last.fm similar tracks                               │
│  │      ├─ Deezer artist top tracks                             │
│  │      ├─ Genre-based search                                   │
│  │      └─ Full analysis for each similar song                  │
│  │                                                              │
│  └─ Send hourly report via Telegram                             │
└─────────────────────────────────────────────────────────────────┘
```

## Data Volume Estimates

### Artists
- **Pop**: 200 artists × avg 80 songs = **16,000 songs**
- **Rap**: 100 artists × avg 60 songs = **6,000 songs**
- **Persian**: 100 artists × avg 50 songs = **5,000 songs**
- **Rock**: 100 artists × avg 70 songs = **7,000 songs**

**Total**: ~34,000 songs from 500 artists

### Similar Songs
- **34,000 songs × 5 similar each** = **170,000 similar songs**

### Combined Total
- **~200,000+ songs** pre-analyzed and cached

### Storage
- **Per song**: ~3.5 KB
- **Total**: ~700 MB - 1 GB

## Quick Start

### Option 1: Run with Bot (Automatic)

```bash
# Start the bot - prefetch runs in background
python bot.py
```

The prefetch system starts automatically and runs continuously.

### Option 2: Run Prefetch Standalone

```bash
# Run once for all genres
python prefetch_artists.py

# Run continuously (repeats every 24 hours)
python prefetch_artists.py --continuous

# Run for specific genre
python prefetch_artists.py --genre pop
python prefetch_artists.py --genre rap
python prefetch_artists.py --genre persian
python prefetch_artists.py --genre rock
```

### Option 3: Check Status

```bash
# Show cache statistics
python prefetch_artists.py --stats

# Run cleanup
python prefetch_artists.py --cleanup
```

## Configuration

### Environment Variables

Add to `.env` file:

```bash
# Enable/disable prefetch (default: true)
ENABLE_PREFETCH=true

# Prefetch mode: "popular" (simple) or "artist" (comprehensive)
PREFETCH_MODE=artist

# Bot token (for sending hourly reports)
TELEGRAM_BOT_TOKEN=your_token_here

# Last.fm API key (optional, improves similar songs)
LASTFM_API_KEY=your_key_here
```

### Customize Genre Targets

Edit `prefetch_artists.py` to change targets:

```python
GENRE_TARGETS = {
    "pop": {"artist_count": 200, "genre_ids": [132, 46], "name": "Pop"},
    "rap": {"artist_count": 100, "genre_ids": [116], "name": "Rap/Hip-Hop"},
    "persian": {"artist_count": 100, "genre_ids": [196], "name": "Persian"},
    "rock": {"artist_count": 100, "genre_ids": [152], "name": "Rock"},
}

# Add more genres:
"electronic": {"artist_count": 100, "genre_ids": [106], "name": "Electronic"},
"jazz": {"artist_count": 50, "genre_ids": [129], "name": "Jazz"},
"classical": {"artist_count": 50, "genre_ids": [173], "name": "Classical"},
```

### Similar Songs Configuration

```python
# Number of similar songs per track (default: 5)
SIMILAR_SONGS_PER_TRACK = 5

# Rate limiting
MAX_SONGS_PER_HOUR = 500
MAX_API_CALLS_PER_MINUTE = 50
```

## Hourly Reports

The system sends hourly progress reports via Telegram showing:

```
📊 Hourly Prefetch Report
🕐 2026-08-07 15:00:00

🎤 Artists Added (12):
  • Taylor Swift
  • Ed Sheeran
  • The Weeknd
  ... and 9 more

🎵 Songs Added: 847
🔍 Similar Songs Found: 4,235

💾 Total Cached: 45,231 songs

❌ Errors: 3

📈 Genre Breakdown:
  • Pop: 847 songs
```

### Enable Reports

1. Start the bot: `python bot.py`
2. Send `/prefetch` to the bot
3. You'll receive hourly reports!

## Performance Benefits

### Before Prefetch

```
User searches "Bohemian Rhapsody"
→ Deezer API: 0.5s
→ Download preview: 1s
→ Librosa analysis: 5s
→ MusicBrainz API: 2s
→ AcousticBrainz API: 2s
→ Last.fm API: 0.5s
→ Find similar songs: 10s
→ Analyze similar songs: 25s
→ Total: ~46 seconds
```

### After Prefetch

```
User searches "Bohemian Rhapsody"
→ Check cache: 0.001s
→ Return cached features: 0.001s
→ Similar songs already cached: 0.001s
→ Total: ~0.003 seconds (15,000x faster!)
```

## Rate Limits & Safety

The system respects all API rate limits:

| API             | Limit         | Usage per Run | Status |
|-----------------|---------------|---------------|--------|
| Deezer          | ~50 req/min   | ~30 req/min   | ✅ Safe |
| MusicBrainz     | 60 req/min    | ~40 req/min   | ✅ Safe |
| Last.fm         | 300 req/min   | ~100 req/min  | ✅ Safe |
| Librosa (CPU)   | ~3-5 sec/song | ~8 songs/min  | ✅ Safe |

**Total runtime**: ~15-20 hours for full prefetch (runs in background)

## Monitoring

### View Logs

```bash
# Real-time artist prefetch logs
tail -f prefetch_artists.log

# Bot logs include prefetch info
tail -f bot.log | grep PREFETCH

# Check for errors
grep "ERROR" prefetch_artists.log
```

### Check Statistics

```bash
# Quick stats
python prefetch_artists.py --stats

# Example output:
# === Cache Statistics ===
# Total songs: 45,231
# With audio features: 43,892
# With acoustic features: 38,456
# With MusicBrainz ID: 41,234
# With Last.fm tags: 35,678
# Last 24h: 12,456
# Last 7 days: 45,231
# ========================
```

### Database Inspection

```bash
# Open SQLite database
sqlite3 feature_cache.db

# View table structure
.schema track_features

# Count cached songs
SELECT COUNT(*) FROM track_features;

# View recent additions
SELECT title, artist, analyzed_at
FROM track_features
ORDER BY analyzed_at DESC
LIMIT 10;

# Count by genre (requires adding genre column)
# SELECT genre, COUNT(*) FROM track_features GROUP BY genre;
```

## Troubleshooting

### Issue: Prefetch not starting

**Check logs:**
```bash
grep "SCHEDULER" bot.log
```

**Common causes:**
1. `ENABLE_PREFETCH=false` in `.env`
2. `PREFETCH_MODE=popular` (not artist)
3. Import error in `prefetch_artists.py`

**Solution:**
```bash
# Test prefetch manually
python prefetch_artists.py --genre pop

# Check for errors
python -c "from prefetch_artists import run_artist_prefetch; import asyncio; asyncio.run(run_artist_prefetch())"
```

### Issue: High memory usage

**Cause**: Too many songs cached in memory

**Solution:**
```bash
# Run cleanup more frequently
python prefetch_artists.py --cleanup --cleanup-days 14

# Or reduce artist targets
# Edit prefetch_artists.py:
GENRE_TARGETS = {
    "pop": {"artist_count": 100, ...},  # Down from 200
    "rap": {"artist_count": 50, ...},   # Down from 100
    ...
}
```

### Issue: Slow prefetch speed

**Cause**: Rate limiting or CPU bottleneck

**Solution:**
```python
# Increase delays between API calls
await asyncio.sleep(0.2)  # Up from 0.1

# Reduce similar songs per track
SIMILAR_SONGS_PER_TRACK = 3  # Down from 5
```

### Issue: Large database size

**Check size:**
```bash
ls -lh feature_cache.db
```

**Solution:**
```bash
# Run aggressive cleanup
python prefetch_artists.py --cleanup --cleanup-days 14

# Or vacuum database
sqlite3 feature_cache.db "VACUUM;"
```

### Issue: Not receiving hourly reports

**Check:**
1. Did you send `/prefetch` to the bot?
2. Is `TELEGRAM_BOT_TOKEN` set in `.env`?
3. Check logs: `grep "REPORT" bot.log`

**Solution:**
```bash
# Test report sending
python -c "
import asyncio
from bot import send_prefetch_report
asyncio.run(send_prefetch_report('Test report'))
"
```

## Advanced Usage

### Custom Genre Support

Add new genres to the prefetch system:

```python
# In prefetch_artists.py, add to GENRE_TARGETS:
"jazz": {"artist_count": 50, "genre_ids": [129], "name": "Jazz"},
"classical": {"artist_count": 50, "genre_ids": [173], "name": "Classical"},
"electronic": {"artist_count": 100, "genre_ids": [106], "name": "Electronic"},
"arabic": {"artist_count": 100, "genre_ids": [165], "name": "Arabic"},
"turkish": {"artist_count": 100, "genre_ids": [195], "name": "Turkish"},
```

### Priority Prefetching

Prefetch specific artists or songs:

```python
# Add to prefetch_artists.py
PRIORITY_ARTISTS = [
    "Taylor Swift",
    "Ed Sheeran",
    "The Weeknd",
    "Bad Bunny",
]

async def prefetch_priority_artists():
    dz = DeezerClient()
    for artist_name in PRIORITY_ARTISTS:
        results = await dz.search(artist_name, limit=1)
        if results:
            tracks = await get_all_artist_tracks(dz, results[0].artist_id, artist_name)
            for track in tracks:
                await full_song_analysis(track, dz, mb, lfm)
```

### Export to JSON

Export cached data for analysis:

```bash
# Export all cached songs to JSON
python -c "
import asyncio
from feature_cache import export_cache_to_json
asyncio.run(export_cache_to_json('cached_songs_export.json'))
"

# Analyze with jq
cat cached_songs_export.json | jq '.[] | {title, artist, bpm, energy}'

# Count by artist
cat cached_songs_export.json | jq 'group_by(.artist) | map({artist: .[0].artist, count: length})'
```

### Schedule with System Cron

For more control, use system cron:

```bash
# Edit crontab
crontab -e

# Run prefetch every hour
0 * * * * cd /path/to/music-suggest-bot && python prefetch_artists.py >> prefetch.log 2>&1

# Run cleanup daily at 3 AM
0 3 * * * cd /path/to/music-suggest-bot && python prefetch_artists.py --cleanup >> prefetch.log 2>&1
```

## Architecture Decisions

### Why Artist-Based?

1. **Complete coverage**: Gets ALL songs, not just popular ones
2. **Better similar songs**: Artist-based similarity is more accurate
3. **Genre diversity**: Ensures wide variety of music
4. **Scalable**: Can easily add more artists/genres

### Why 5 Similar Songs?

1. **Balance**: Enough variety without excessive storage
2. **User experience**: Shows related music without overwhelming
3. **Cache efficiency**: Similar songs often requested together
4. **Storage**: ~170K songs × 3.5 KB = ~600 MB (manageable)

### Why Hourly Reports?

1. **Visibility**: Track progress in real-time
2. **Debugging**: Catch issues early
3. **Motivation**: See the system working
4. **Planning**: Estimate completion time

## Storage Management

### Automatic Cleanup

- Runs daily at 3 AM
- Removes entries older than 30 days
- Keeps database under 1 GB

### Manual Cleanup

```bash
# Remove entries older than 14 days
python prefetch_artists.py --cleanup --cleanup-days 14

# Aggressive cleanup (7 days)
python prefetch_artists.py --cleanup --cleanup-days 7
```

### Database Optimization

```bash
# Vacuum database (reclaim space)
sqlite3 feature_cache.db "VACUUM;"

# Analyze for better query performance
sqlite3 feature_cache.db "ANALYZE;"
```

## Contributing

To improve the prefetch system:

1. **Add new genres**: Electronic, Jazz, Classical, etc.
2. **Optimize analysis**: Faster librosa alternatives
3. **Better similar songs**: Use audio fingerprinting
4. **Smart scheduling**: Adjust based on bot load
5. **Distributed prefetch**: Run multiple workers

## Support

For issues or questions:

1. Check logs: `tail -f prefetch_artists.log`
2. Test manually: `python prefetch_artists.py --genre pop`
3. Check stats: `python prefetch_artists.py --stats`
4. Open GitHub issue with logs attached

---

**Last Updated**: 2026-08-07
**Version**: 1.0.0
