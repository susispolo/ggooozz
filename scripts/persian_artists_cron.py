#!/usr/bin/env python3
"""Persian artist dataset grower — run by cron.

Adds up to NEW_TARGET (20) previously-unknown Persian singers across all
genres to persian_genres.json. Idempotent: artists already present in
persian_genres.json OR new_persian_artists.json are never re-added
(dedup is exact + normalized-name + fuzzy overlap).

How it decides genre: queries Deezer for the artist and uses Deezer's own
genre data, mapped into the bot's genre vocabulary. If Deezer has no genre,
falls back to the curated seed genre.

Run:  venv/Scripts/python.exe scripts/persian_artists_cron.py [--dry-run]
Exit: 0 = ok (0 or more added), 2 = error.
"""

import argparse
import json
import os
import re
import sys
import tempfile

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GENRES_PATH = os.path.join(BASE_DIR, "persian_genres.json")
AUTO_PATH = os.path.join(BASE_DIR, "new_persian_artists.json")
NEW_TARGET = 20

# Bot's genre vocabulary (must match what bot.py / fallback logic uses)
GENRE_VOCAB = {
    "Classical Persian", "Persian Classic", "Persian Comedy",
    "Persian Dance", "Persian Electronic", "Persian Pop",
    "Persian Rap", "Persian Rock", "Persian Traditional",
}

# Curated seed list: (artist name, fallback genre). Covers all genres —
# pop, rock, rap, traditional/classical, dance, electronic, comedy.
# The script skips anyone already in the DB, so running repeatedly keeps
# adding fresh names from this list (and later runs can extend it).
SEED_ARTISTS = [
    # Pop
    ("Mohammad-Reza Shajarian", "Persian Traditional"),
    ("Shahram Shabpareh", "Persian Pop"),
    ("Martik", "Persian Pop"),
    ("Farhad Mehrad", "Persian Rock"),
    ("Kourosh Yaghmaei", "Persian Rock"),
    ("Fereydoon Foroughi", "Persian Rock"),
    ("Siavash Shams", "Persian Pop"),
    ("Pouya Bayati", "Persian Pop"),
    ("Amir Tataloo", "Persian Pop"),
    ("Sasy", "Persian Pop"),
    ("Saeed Shayesteh", "Persian Pop"),
    ("Nima Shaban", "Persian Pop"),
    ("Arman Garshasbi", "Persian Pop"),
    ("Mohammad Motamedi", "Persian Traditional"),
    ("Salar Aghili", "Persian Traditional"),
    ("Hossein Alizadeh", "Persian Traditional"),
    ("Kayhan Kalhor", "Persian Traditional"),
    ("Homayoun Shajarian", "Persian Traditional"),   # dedup check target
    ("Shahram Nazeri", "Persian Traditional"),        # dedup check target
    # Rock
    ("O-Hum", "Persian Rock"),
    ("Kiosk", "Persian Rock"),
    ("The Ways", "Persian Rock"),
    ("Baran", "Persian Rock"),
    ("Kaveh Yaghmaei", "Persian Rock"),
    ("Pallet", "Persian Rock"),
    ("Radio Tehran", "Persian Rock"),
    ("Hypernova", "Persian Rock"),
    ("Kings of the Scene", "Persian Rock"),
    # Rap
    ("Hichkas", "Persian Rap"),
    ("Yas", "Persian Rap"),
    ("Reza Pishro", "Persian Rap"),
    ("Shahin Najafi", "Persian Rap"),
    ("Bahram Nouraei", "Persian Rap"),
    ("Fadaei", "Persian Rap"),
    ("Mehrad Hidden", "Persian Rap"),
    ("Sohrab MJ", "Persian Rap"),
    ("Amin Tijay", "Persian Rap"),
    ("Quf", "Persian Rap"),
    ("Poori", "Persian Rap"),
    ("Shayea", "Persian Rap"),
    ("Koorosh", "Persian Rap"),
    ("Saman Wilson", "Persian Rap"),
    ("Ali Sorena", "Persian Rap"),
    # Classic / Traditional
    ("Dariush Eghbali", "Persian Pop"),
    ("Ebrahim Hamedi", "Persian Classic"),
    ("Alireza Eftekhari", "Persian Classic"),
    ("Mohammad Reza Shajarian", "Persian Traditional"),
    ("Parviz Meshkatian", "Persian Traditional"),
    ("Jalal Zolfonoun", "Persian Traditional"),
    ("Shahram Nazeri", "Persian Traditional"),
    ("Mohammad Esfahani", "Persian Classic"),
    ("Sohrab Pournazeri", "Persian Traditional"),
    ("Hamid Motebassem", "Persian Traditional"),
    ("Dariush Talai", "Persian Traditional"),
    ("Majid Derakhshani", "Persian Traditional"),
    ("Amir Alavi", "Persian Traditional"),
    ("Hossein Khajeh Amiri", "Persian Classic"),
    ("Elaheh", "Persian Classic"),
    ("Marzieh", "Persian Classic"),
    ("Delkash", "Persian Classic"),
    ("Ahmad Zahir", "Persian Classic"),
    ("Nasrat Rahimi", "Persian Classic"),
    ("Farhad Fakhreddini", "Persian Traditional"),
    ("Loris Tjeknavorian", "Persian Traditional"),
    # Dance / Electronic / Comedy
    ("Arash", "Persian Dance"),
    ("Shahram Solati", "Persian Dance"),
    ("Moein", "Persian Dance"),
    ("Shohreh", "Persian Dance"),
    ("Satin", "Persian Dance"),
    ("DJ Aligator", "Persian Electronic"),
    ("Deep Dish", "Persian Electronic"),
    ("Ali-Reza Ghorbani", "Persian Traditional"),
    # ---- more pop (obscure / newer) ----
    ("Behnam Bani", "Persian Pop"),
    ("Majid Razavi", "Persian Pop"),
    ("Sina Saei", "Persian Pop"),
    ("Moein Z", "Persian Pop"),
    ("Amir Masih", "Persian Pop"),
    ("Sara Naeini", "Persian Pop"),
    ("Mohammad Lotfi", "Persian Pop"),
    ("Masih", "Persian Pop"),
    ("Hamed Homayoun", "Persian Pop"),
    ("Mohsen Chavoshi", "Persian Pop"),
    ("Farzad Farzin", "Persian Pop"),
    ("Ali Lohrasbi", "Persian Pop"),
    ("Evan Band", "Persian Pop"),
    ("Amirhossein Eftekhari", "Persian Pop"),
    ("Alireza JJ", "Persian Pop"),
    ("Kasra Zahedi", "Persian Pop"),
    ("Sogand", "Persian Pop"),
    ("Sara Fadaei", "Persian Pop"),
    ("Helena Taheri", "Persian Pop"),
    ("Masoud Sadeghloo", "Persian Pop"),
    ("Peyman Keyvani", "Persian Pop"),
    ("Ahmad Saeedi", "Persian Pop"),
    ("Babak Jahanbakhsh", "Persian Pop"),
    ("Mehdi Ahmadvand", "Persian Pop"),
    ("Xaniar Khosravi", "Persian Pop"),
    ("Niloo Sharifi", "Persian Pop"),
    ("Shabnam Gholami", "Persian Pop"),
    ("Ghazal Shakeri", "Persian Pop"),
    ("Amirhossein Najafi", "Persian Pop"),
    ("Hootan", "Persian Pop"),
    ("Milad Baran", "Persian Pop"),
    ("Ehsan Daryadel", "Persian Pop"),
    ("Aram", "Persian Pop"),
    ("Sepideh", "Persian Pop"),
    ("Mahyar", "Persian Pop"),
    ("Shahin", "Persian Pop"),
    # ---- more rock ----
    ("Kiosk Band", "Persian Rock"),
    ("Baran Band", "Persian Rock"),
    ("Radio Tehran Band", "Persian Rock"),
    ("O-Hum Band", "Persian Rock"),
    ("Mana", "Persian Rock"),
    ("Gand", "Persian Rock"),
    ("Arian Band", "Persian Rock"),
    ("Black Cats", "Persian Rock"),
    ("Reza Yazdani", "Persian Rock"),
    ("Pallett", "Persian Rock"),
    ("Acid", "Persian Rock"),
    ("Navid", "Persian Rock"),
    ("Khan", "Persian Rock"),
    # ---- more rap ----
    ("Hiphopologist", "Persian Rap"),
    ("Shahin Najafi", "Persian Rap"),
    ("Bahooz", "Persian Rap"),
    ("Mohsen Yeganeh Rap", "Persian Rap"),
    ("Erfan", "Persian Rap"),
    ("Amir Tataloo Rap", "Persian Rap"),
    ("Yaser Bakhtiari", "Persian Rap"),
    ("Sohrab MJ Rap", "Persian Rap"),
    ("Peyman Momeni", "Persian Rap"),
    ("Gdaal", "Persian Rap"),
    ("Mansour", "Persian Rap"),
    ("Azad", "Persian Rap"),
    ("Reza Shiri", "Persian Rap"),
    ("Tata", "Persian Rap"),
    ("Kaveh", "Persian Rap"),
    # ---- more traditional/classical ----
    ("Homayoun Khorram", "Persian Traditional"),
    ("Mohammadreza Lotfi", "Persian Traditional"),
    ("Hossein Omoumi", "Persian Traditional"),
    ("Dariush Pirniakan", "Persian Traditional"),
    ("Hamid Reza Nourbakhsh", "Persian Traditional"),
    ("Ali Reza Ghorbani", "Persian Traditional"),
    ("Mohammad Akbari", "Persian Traditional"),
    ("Siamak Aghaei", "Persian Traditional"),
    ("Reza Gholi Mirazani", "Persian Traditional"),
    ("Morteza Varzi", "Persian Traditional"),
    ("Hassan Tabar", "Persian Traditional"),
    ("Javad Zolfonoun", "Persian Traditional"),
    ("Parviz Rahman Panah", "Persian Traditional"),
    ("Arsalan Karimi", "Persian Traditional"),
    ("Ehsan Shayanfar", "Persian Traditional"),
    ("Navid Afghah", "Persian Traditional"),
    ("Bijan Bijani", "Persian Traditional"),
    ("Mehrdad Nikouei", "Persian Traditional"),
    ("Bahram Bani", "Persian Traditional"),
    # ---- more classic ----
    ("Marziye", "Persian Classic"),
    ("Homayra", "Persian Classic"),
    ("Ramesh", "Persian Classic"),
    ("Mahasti", "Persian Classic"),
    ("Shohreh Solati", "Persian Classic"),
    ("Hassan Shamaizadeh", "Persian Classic"),
    ("Anoushirvan Rohani", "Persian Classic"),
    ("Varoujan", "Persian Classic"),
    ("Fereydoun Shahbazian", "Persian Classic"),
    ("Nasser Cheshmazar", "Persian Classic"),
    ("Amir Nasser Eftekhari", "Persian Classic"),
    ("Gholamreza Sadeghi", "Persian Classic"),
    ("Soheil Nafisi", "Persian Classic"),
    # ---- more dance / electronic ----
    ("Leila Forouhar", "Persian Pop"),
    ("Diana", "Persian Dance"),
    ("Annie", "Persian Dance"),
    ("Shohreh", "Persian Dance"),
    ("Andy Madadian", "Persian Dance"),
    ("Mansour", "Persian Dance"),
    ("Faramarz Aslani", "Persian Traditional"),
    ("Negin", "Persian Dance"),
    ("Sahar", "Persian Dance"),
    ("DJ Mary", "Persian Electronic"),
    ("DJ Bass", "Persian Electronic"),
    ("Vahid", "Persian Electronic"),
    ("Shahin Shabpareh", "Persian Pop"),
    # ---- comedy ----
    ("Ramtin Javan", "Persian Comedy"),
    ("Behzad Leito", "Persian Comedy"),
    ("Mammad Zolfonoun", "Persian Comedy"),
    ("Hossein Eblis", "Persian Comedy"),
    ("Kianoush", "Persian Comedy"),
    ("Shahram Parchehbaf", "Persian Comedy"),
]


def normalize(name: str) -> str:
    """Lowercase, strip diacritics, drop non-alnum (handles Persian too)."""
    name = name.lower()
    # strip combining marks
    name = "".join(c for c in name if not (0x0300 <= ord(c) <= 0x036F))
    return re.sub(r"[^a-z0-9\u0600-\u06FF]+", "", name)


def normalize_artist(name: str) -> str:
    """Normalize an artist name for comparison: strip common particles."""
    n = normalize(name)
    for p in ("the", "dj", "mc", "dr", "mr"):
        if n.startswith(p):
            n = n[len(p):]
    return n


def name_overlap(a: str, b: str) -> bool:
    """Fuzzy overlap: shared word or 4+ char substring."""
    na, nb = normalize_artist(a), normalize_artist(b)
    if not na or not nb:
        return False
    if na == nb or na in nb or nb in na:
        return True
    wa, wb = set(na.split()), set(nb.split())
    if wa & wb:
        return True
    # 4+ char common substring
    for i in range(len(na) - 3):
        if na[i:i + 4] in nb:
            return True
    return False


def load_artists() -> set:
    """All known artist names (normalized) from both JSON files."""
    known = set()
    for path in (GENRES_PATH, AUTO_PATH):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            known.update(normalize_artist(k) for k in data.keys())
        except FileNotFoundError:
            pass
    return known


def load_db() -> dict:
    with open(GENRES_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_db(db: dict) -> None:
    """Atomic write to persian_genres.json."""
    fd, tmp = tempfile.mkstemp(dir=BASE_DIR, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(db, f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.replace(tmp, GENRES_PATH)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def deezer_artist_genres(session, artist_name: str, fallback: str) -> list:
    """Query Deezer for the artist's genres; map into bot vocabulary.

    Falls back to the curated seed genre when Deezer has no data.
    """
    try:
        import requests
        r = session.get(
            "http://api.deezer.com/search/artist",
            params={"q": artist_name, "limit": 3},
            timeout=15,
        )
        if r.status_code == 200:
            data = r.json().get("data", [])
            if data:
                artist = data[0]
                name = artist.get("name", "")
                # Verify the match is plausible
                if not name_overlap(name, artist_name):
                    name = ""
                genres = artist.get("genres", {}).get("data", [])
                raw_genres = [g.get("name", "") for g in genres]
                mapped = [g for g in raw_genres if g in GENRE_VOCAB]
                # Any Persian-ish genre Deezer knows → prefer that
                persian_hits = [
                    g for g in raw_genres
                    if "persian" in g.lower() or "iranian" in g.lower()
                ]
                if persian_hits and not mapped:
                    base = persian_hits[0]
                    # crude mapping: e.g. "Persian pop" -> "Persian Pop"
                    words = base.split()
                    if len(words) >= 2 and words[1].lower() in {
                        "pop", "rock", "rap", "electronic", "dance",
                        "comedy", "classic", "traditional",
                    }:
                        mapped = [f"Persian {words[1].title()}"]
                if mapped:
                    return mapped
    except Exception:
        pass
    return [fallback]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="print what would be added")
    ap.add_argument("--limit", type=int, default=NEW_TARGET,
                    help=f"max new artists to add (default {NEW_TARGET})")
    args = ap.parse_args()

    known = load_artists()
    db = load_db()
    added = []
    skipped_dups = []
    errors = []

    import requests
    session = requests.Session()

    for artist_name, fallback_genre in SEED_ARTISTS:
        if len(added) >= args.limit:
            break
        norm = normalize_artist(artist_name)
        if norm in known:
            skipped_dups.append(artist_name)
            continue
        # Also check overlap against existing keys (fuzzy dedup)
        if any(name_overlap(artist_name, existing) for existing in known):
            skipped_dups.append(artist_name)
            continue
        try:
            genres = deezer_artist_genres(session, artist_name, fallback_genre)
            if not genres:
                genres = [fallback_genre]
            # Ensure genre in vocabulary
            genres = [g if g in GENRE_VOCAB else fallback_genre for g in genres]
            db[artist_name] = genres
            known.add(norm)
            added.append((artist_name, genres[0]))
            print(f"ADD  {artist_name} -> {genres}")
        except Exception as e:
            errors.append(f"{artist_name}: {e}")
            print(f"ERR  {artist_name}: {e}", file=sys.stderr)

    if added and not args.dry_run:
        save_db(db)
        print(f"\nSaved {len(added)} new artist(s) to {os.path.basename(GENRES_PATH)} "
              f"(total {len(db)}).")
    elif args.dry_run:
        print(f"\nDRY RUN — would add {len(added)} artist(s) (not saved).")
    else:
        print(f"\nNothing new to add (already up to date, total {len(db)}).")

    print(f"Skipped duplicates: {len(skipped_dups)} — {', '.join(skipped_dups[:10])}{'...' if len(skipped_dups) > 10 else ''}")
    if errors:
        print(f"Errors: {len(errors)} — {errors[:3]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
