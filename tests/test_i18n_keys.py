import sys
sys.path.insert(0, r"D:\music-suggest-bot")
from i18n import msg, label

for k in ["start_hero", "help_text", "download_howto", "search_prompt", "for_me_footer", "for_me_locked", "download_cta"]:
    for lang in ["en", "fa"]:
        m = msg(k, lang)
        if not m:
            raise SystemExit(f"MISSING: {k}/{lang}")
print("All new i18n keys present in EN+FA OK")
print("search_again label:", repr(label("search_again", "en")), repr(label("search_again", "fa")))
print("how_to_play label:", repr(label("how_to_play", "en")), repr(label("how_to_play", "fa")))