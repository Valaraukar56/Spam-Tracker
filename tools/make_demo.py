"""Genere des donnees de demonstration 100 % fictives (pour les captures d'ecran et les tests).

    python tools\\make_demo.py <dossier>

Cree dans <dossier> :
    replays\\demo.server\\<compte fictif>\\index.json   matchs inventes (pseudos, identifiants)
    data\\catalog.json                                 cartes inventees, sans illustration
Puis lancer l'app sur ces donnees :
    set SPAM_DATA_DIR=<dossier>\\data
    set SPAM_REPLAYS_DIR=<dossier>\\replays
    python app.py

Aucune donnee reelle, aucun contenu du jeu (noms, illustrations) n'est utilise.
"""

import json
import random
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

random.seed(42)   # toujours les memes donnees

ME = "00000000-0000-4000-8000-000000000001"   # compte fictif
CARD_NAMES = [
    ("Gardien d'exemple", "earth"), ("Lueur de test", "light"), ("Braise fictive", "fire"),
    ("Vague de demo", "water"), ("Ronce imaginaire", "nature"), ("Ombre factice", "shadow"),
    ("Sentinelle grise", "earth"), ("Etincelle", "fire"), ("Marée basse", "water"),
    ("Pousse tenace", "nature"), ("Phare lointain", "light"), ("Voile sombre", "shadow"),
    ("Golem de papier", "earth"), ("Comète docile", "light"), ("Salamandre calme", "fire"),
    ("Anguille rieuse", "water"),
]
RARITIES = ["common", "common", "rare", "epic", "legendary"]
OPPONENTS = ["Aster", "Brindille", "Corvus", "Dahlia", "Eskal", "Fjord", "Givre", "Hélio"]


def card_uuid(i):
    return str(uuid.UUID(int=0xC0DE0000_0000_4000_8000_000000000000 + i))


ELEMENT_RGB = {"fire": (255, 106, 61), "water": (62, 166, 255), "earth": (201, 154, 91),
               "nature": (108, 207, 90), "light": (255, 215, 94), "shadow": (162, 116, 255)}


def make_art(folder, cards):
    """Illustrations abstraites generees (degrades et formes) : aucun contenu du jeu."""
    from PIL import Image, ImageDraw, ImageFilter
    folder.mkdir(parents=True, exist_ok=True)
    w, h = 200, 285
    for i, (uid, c) in enumerate(cards.items()):
        rnd = random.Random(i)
        r, g, b = ELEMENT_RGB[c["elements"][0]]
        img = Image.new("RGB", (w, h))
        px = img.load()
        for y in range(h):          # degrade vertical de la couleur d'element vers la nuit
            t = y / h
            for x in range(w):
                k = 0.85 - 0.6 * t + 0.08 * ((x + y) % 7) / 7
                px[x, y] = (int(r * k * 0.7 + 12), int(g * k * 0.7 + 14), int(b * k * 0.7 + 22))
        d = ImageDraw.Draw(img, "RGBA")
        for _ in range(7):          # formes floues : "paysage" abstrait
            cx, cy, rad = rnd.randint(0, w), rnd.randint(40, h), rnd.randint(20, 90)
            d.ellipse((cx - rad, cy - rad, cx + rad, cy + rad),
                      fill=(min(255, r + 60), min(255, g + 60), min(255, b + 60), rnd.randint(40, 110)))
        d.polygon([(0, h), (w * 0.3, h * 0.62), (w * 0.55, h * 0.78), (w * 0.8, h * 0.55), (w, h)],
                  fill=(8, 10, 16, 200))
        img = img.filter(ImageFilter.GaussianBlur(1.2))
        img.save(folder / f"{uid}.webp", "WEBP", quality=85)


def main(target):
    target = Path(target)
    cards = {}
    for i, (name, element) in enumerate(CARD_NAMES):
        uid = card_uuid(i)
        cards[uid] = {"uuid": uid, "name": name, "number": i + 1, "elements": [element],
                      "rarity": RARITIES[i % len(RARITIES)], "hp": 400 + 50 * (i % 8),
                      "abilities": [], "talents": [], "image": False}
    data = target / "data"
    data.mkdir(parents=True, exist_ok=True)
    make_art(data / "cards", cards)
    # faux dossier de jeu (fichier vide) pour que les Reglages n'affichent aucun chemin reel
    fake_game = target / "SteamLibrary" / "steamapps" / "common" / "SPAM"
    (fake_game / "SPAM_Data").mkdir(parents=True, exist_ok=True)
    (fake_game / "SPAM_Data" / "resources.assets").touch()
    (data / "settings.json").write_text(json.dumps({"game_dir": str(fake_game)}), encoding="utf-8")
    for c in cards.values():
        c["image"] = True
    (data / "catalog.json").write_text(json.dumps({
        "generated_utc": "2026-01-01T12:00:00+00:00", "source": "demo", "game_version": "1.26",
        "tested_with": "1.26", "count": len(cards), "cards": cards}, ensure_ascii=False, indent=1), encoding="utf-8")

    ids = list(cards)
    decks = [ids[0:4], ids[0:3] + [ids[5]], [ids[1], ids[2], ids[6], ids[9]]]
    start = datetime(2026, 1, 10, 18, 0, tzinfo=timezone.utc)
    my_stars, my_rank, matches = 64, 1480, []
    for n in range(14):
        ranked = n >= 4                        # les 4 premiers en Normal, puis du Classe
        ai = n == 2                            # un match contre l'IA
        win = random.random() < 0.62
        if ranked:
            my_stars += 1 if win else -1
            my_rank += random.randint(-60, -20) if win else random.randint(10, 40)
        opp_stars = max(1, my_stars + random.randint(-6, 6))
        t0 = start + timedelta(minutes=17 * n)
        dur = random.randint(90, 600)
        opp_id = str(uuid.UUID(int=0x0BB00000_0000_4000_8000_000000000000 + n % 8))
        matches.append({
            "FormatVersion": 2, "AppVersion": "1.26", "GameUid": f"match-{9000000 + n}",
            "AccountId": ME, "Seat": 0, "GameMode": 10 if ranked else 0, "Level": "",
            "OpponentId": opp_id, "OpponentName": "IA d'entraînement" if ai else OPPONENTS[n % 8],
            "OpponentIsAi": ai, "WinnerId": ME if win else opp_id, "IsDraw": False,
            "MyCards": decks[n % 3], "OpponentCards": random.sample(ids, 4),
            "StartUtc": t0.isoformat().replace("+00:00", "Z"),
            "EndUtc": (t0 + timedelta(seconds=dur)).isoformat().replace("+00:00", "Z"),
            "DurationMs": dur * 1000, "MessageCount": 400, "TurnCount": random.randint(3, 14),
            "Loading": {"matchId": f"match-{9000000 + n}",
                        "opponent": {"username": OPPONENTS[n % 8], "stars": 0 if ai else opp_stars,
                                     "rank": 0 if ai else my_rank + random.randint(-200, 200)},
                        "me": {"username": "Joueur", "stars": my_stars, "rank": my_rank}},
        })
    folder = target / "replays" / "demo.server" / ME
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "index.json").write_text(json.dumps(matches[::-1], ensure_ascii=False), encoding="utf-8")
    print(f"Demo creee dans {target} : {len(matches)} matchs, {len(cards)} cartes fictives.")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
