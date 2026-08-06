# Quick smoke test for the new language detection logic
import sys
sys.path.insert(0, r"D:\music-suggest-bot")
from language_detect import detect_language, language_label

cases = [
    ("Freight Train", "Elizabeth Cotten", ""),   # was often tagged de/sv
    ("Bohemian Rhapsody", "Queen", ""),
    ("Shape of You", "Ed Sheeran", ""),
    ("Yesterday", "The Beatles", ""),
    ("A Sky Full of Stars", "Coldplay", ""),
    ("Johnny B. Goode", "Chuck Berry", ""),
    ("Sultans of Swing", "Dire Straits", ""),
    ("La Vie en Rose", "Édith Piaf", ""),        # French
    ("Feliz Navidad", "José Feliciano", ""),     # Spanish
    ("Mädchen", "Rammstein", ""),                # German
    ("Believer", "Imagine Dragons", ""),
    ("Faded", "Alan Walker", ""),
    ("Dynamite", "BTS", ""),                     # K-pop artist map
    ("Gangnam Style", "Psy", ""),
    ("دلم گرفته", "محسن چاوشی", ""),              # Persian
    ("Bonnie and Clyde", "Jay-Z", ""),
    ("Amazing Grace", "Traditional", ""),
    ("Kimi no Na wa", "RADWIMPS", ""),           # Japanese translit
    ("Despacito", "Luis Fonsi", ""),             # Spanish
    ("99 Luftballons", "Nena", ""),              # German no diacritic
]

for t, a, o in cases:
    r = detect_language(t, a, o)
    name, flag = language_label(r)
    print(f"{flag} {name:12s} | {t!r} - {a!r}")
