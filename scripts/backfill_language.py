"""
One-time backfill: re-detect language for playlist rows that predate the
language column (they got the default 'en' during migration).
Run manually once:
  venv/Scripts/python.exe scripts/backfill_language.py
"""
import asyncio
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from logging_config import setup_logging
setup_logging(level=logging.INFO, log_file="")

import user_prefs
from language_detect import detect_language


async def main():
    async with __import__("aiosqlite").connect(user_prefs.DB_PATH) as conn:
        cur = await conn.execute(
            "SELECT id, original_text, title, artist, language FROM user_playlist"
        )
        rows = await cur.fetchall()

    if not rows:
        print("No rows to backfill.")
        return

    print(f"Backfilling {len(rows)} rows...")
    changed = 0
    async with __import__("aiosqlite").connect(user_prefs.DB_PATH) as conn:
        for row_id, original, title, artist, old_lang in rows:
            lang = detect_language(title or "", artist or "", original or "")
            if lang != old_lang:
                await conn.execute("UPDATE user_playlist SET language=? WHERE id=?", (lang, row_id))
                print(f"  row {row_id}: {title} - {artist} : {old_lang} -> {lang}")
                changed += 1
            else:
                print(f"  row {row_id}: {title} - {artist} stays {lang}")
        await conn.commit()
    print(f"Done. {changed} rows updated.")


if __name__ == "__main__":
    asyncio.run(main())
