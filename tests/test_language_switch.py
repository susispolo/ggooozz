"""Verify the language-switch callback and Persian keyboard handling.

Simulates the full lang_fa -> keyboard refresh -> button-press flow
with lightweight fakes (no Telegram network). Catches the class of bug
seen in production: UnboundLocalError on msg() and button labels not
matching after switching to Persian.
"""
import asyncio
import sys
import os
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bot
import user_prefs as up
from i18n import set_lang as i18n_set_lang

up.DB_PATH = os.path.join(tempfile.mkdtemp(), "t.db")

PASS = 0
FAIL = 0


def check(name, cond):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        print(f"  FAIL  {name}")


class FakeQuery:
    def __init__(self):
        self.edited = None

    async def answer(self):
        pass

    async def edit_message_text(self, text=None, **kw):
        self.edited = text
        return True


class FakeMessage:
    def __init__(self, text=""):
        self.text = text
        self.sent = []

    async def reply_text(self, text=None, **kw):
        self.sent.append(text)
        return FakeMessage(text)


class FakeChat:
    def __init__(self, cid=999):
        self.id = cid
        self.sent = []

    async def send_message(self, text=None, **kw):
        self.sent.append(text)
        return FakeMessage(text)


class FakeUser:
    def __init__(self, uid):
        self.id = uid


class FakeUpdate:
    def __init__(self, uid, data, msg_text="", message=None):
        self.effective_user = FakeUser(uid)
        self.effective_chat = FakeChat()
        self.callback_query = FakeQuery()
        self.callback_query.data = data
        self.message = message or FakeMessage(msg_text)


async def main():
    await up.init_db()
    uid = 240082844
    # Seed a chosen language so the first-time picker doesn't hijack the flow
    await up.set_user_language(uid, "en")
    i18n_set_lang(uid, "en")

    # 0. First-time user (no language row) must be routed to the picker
    fresh_uid = 888000
    upd = FakeUpdate(fresh_uid, "", msg_text="🔍 Search")
    try:
        await bot.handle_text(upd, None)
        check("first-time user routed to language picker", True)
    except Exception as e:
        check(f"first-time user routed to language picker (got {e!r})", False)

    # 1. Language callback: lang_fa must not raise
    upd = FakeUpdate(uid, "lang_fa")
    try:
        await bot.handle_callback(upd, None)
        check("lang_fa callback no-crash", True)
    except Exception as e:
        check(f"lang_fa callback no-crash (got {e!r})", False)

    # 2. Language persisted
    persisted = await up.get_user_language(uid)
    check("language persisted as fa", persisted == "fa")

    # 3. Main keyboard in fa shows Persian labels
    kb = bot._main_menu_keyboard("fa")
    labels = [b.text for row in kb.keyboard for b in row]
    check("fa keyboard has Persian labels", any("جستجو" in l for l in labels))

    # 4. English keyboard button still works after switching to fa
    upd = FakeUpdate(uid, "", msg_text="🔍 Search")
    try:
        await bot.handle_text(upd, None)
        check("old English Search button still matches", True)
    except Exception as e:
        check(f"old English Search button still matches (got {e!r})", False)

    # 5. Persian button works
    upd = FakeUpdate(uid, "", msg_text="📋 لیست من")
    try:
        await bot.handle_text(upd, None)
        check("Persian My Playlist button matches", True)
    except Exception as e:
        check(f"Persian My Playlist button matches (got {e!r})", False)

    # 6. English 'Add to Playlist' (stale keyboard) matches
    upd = FakeUpdate(uid, "", msg_text="➕ Add to Playlist")
    try:
        await bot.handle_text(upd, None)
        check("stale English Add-to-Playlist matches", True)
    except Exception as e:
        check(f"stale English Add-to-Playlist matches (got {e!r})", False)

    print(f"\n{'-'*40}\nPASS={PASS} FAIL={FAIL}")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    asyncio.run(main())
