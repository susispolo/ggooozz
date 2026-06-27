"""Probe what Deezer's free API actually offers."""
import requests, json

# 1. Get a track — see available fields
track_id = 3135556  # Bohemian Rhapsody on Deezer
r = requests.get(f"https://api.deezer.com/track/{track_id}", timeout=15)
print("=== TRACK FIELDS ===")
for k, v in r.json().items():
    if not isinstance(v, (dict, list)):
        print(f"  {k}: {v}")
    elif isinstance(v, list) and len(v) < 5:
        print(f"  {k}: {v}")
    elif isinstance(v, dict):
        print(f"  {k}: <dict> keys={list(v.keys())}")

# 2. Search by name
r2 = requests.get("https://api.deezer.com/search?q=bohemian+rhapsody&limit=3", timeout=15)
print("\n=== SEARCH RESULTS ===")
for t in r2.json().get("data", []):
    print(f"  {t['title']} — {t['artist']['name']}  (BPM: {t.get('bpm','?')})")

# 3. Radio/similar tracks
r3 = requests.get(f"https://api.deezer.com/track/{track_id}/radio?limit=5", timeout=15)
print("\n=== SIMILAR (radio) TRACKS ===")
for t in r3.json().get("data", []):
    print(f"  {t['title']} — {t['artist']['name']}  (BPM: {t.get('bpm','?')})")

# 4. Artist info for genres
r4 = requests.get("https://api.deezer.com/artist/27", timeout=15)  # Queen
print("\n=== ARTIST FIELDS ===")
for k, v in r4.json().items():
    if not isinstance(v, (dict, list)):
        print(f"  {k}: {v}")

# 5. See if a track has that "arrow" (next/day) endpoint
r5 = requests.get(f"https://api.deezer.com/track/{track_id}/radio?autocomplete=1", timeout=15)
print(f"\n=== RADIO AUTOCOMPLETE: {len(r5.json().get('data',[]))} tracks ===")
for t in r5.json().get("data", [])[:3]:
    print(f"  {t['title']} — {t['artist']['name']}")
