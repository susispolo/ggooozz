"""Remove duplicated playlist rows (keep earliest per user/track/title)."""
import asyncio
import aiosqlite

DB = "user_prefs.db"


async def main():
    async with aiosqlite.connect(DB) as conn:
        cur = await conn.execute(
            """SELECT id FROM user_playlist
               WHERE id NOT IN (
                 SELECT MIN(id) FROM user_playlist GROUP BY user_id, track_id, title
               )"""
        )
        dups = [r[0] for r in await cur.fetchall()]
        print("duplicate ids to remove:", dups)
        if dups:
            placeholders = ",".join("?" * len(dups))
            await conn.execute(
                f"DELETE FROM user_playlist WHERE id IN ({placeholders})", dups
            )
            await conn.commit()
            print(f"removed {len(dups)} duplicates")
        else:
            print("no duplicates")

        print("\nRemaining rows for user 240082844:")
        cur = await conn.execute(
            "SELECT id, title, artist, language, genre FROM user_playlist WHERE user_id=240082844 ORDER BY id"
        )
        for r in await cur.fetchall():
            print(" ", r)


if __name__ == "__main__":
    asyncio.run(main())