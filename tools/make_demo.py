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


# Talents inventes (uuid -> nom), cites dans les replays fictifs
TALENTS = {str(uuid.UUID(int=0x7A1E0000_0000_4000_8000_000000000000 + i)): name for i, name in enumerate(
    ["Vigueur d'exemple", "Écho fictif", "Garde de test", "Élan imaginaire", "Focus de démo", "Riposte factice"])}


def dotnet_string(text):
    """Chaine au format BinaryWriter .NET : longueur (entier 7 bits) puis UTF-8."""
    raw, n, prefix = text.encode("utf-8"), len(text.encode("utf-8")), bytearray()
    while True:
        b, n = n & 0x7F, n >> 7
        prefix.append(b | (0x80 if n else 0))
        if not n:
            return bytes(prefix) + raw


def write_srpl(path, header, blocks, summary):
    """Replay fictif au format du jeu (MatchReplay v2) : decks de depart puis resume de fin (GameEnd)."""
    import gzip
    import struct
    start = b"\x9f\x08"                                  # message d'etat : bloc de chaque joueur
    for pid, deck in blocks:
        start += b"\x01" + pid.encode()
        for i, card in enumerate(deck):
            start += b"\x00\x18" + f"DemoCarte{i:02d}X".encode() + b"\x02J" + card.encode()
    end = b"\xd1\x07\x00\x00" + json.dumps(summary, ensure_ascii=False).encode("utf-16-le")   # 2001 = GameEnd
    msgs = [(0, start), (summary["turnCount"] * 30000, end)]
    body = b"SRPL" + struct.pack("<i", 2) + dotnet_string(json.dumps(header)) + struct.pack("<i", len(msgs))
    for t, data in msgs:
        body += struct.pack("<ii", t, len(data)) + data
    with gzip.open(path, "wb") as f:
        f.write(body)


def fake_summary(rnd, uid, me, opp, my_deck, opp_deck, win, turns):
    """Resume de fin de partie fictif (meme structure que celui ecrit par le jeu)."""
    tal = list(TALENTS.items())

    def side(deck, winner):
        cards = []
        for c in deck:
            tid, tname = rnd.choice(tal)
            cards.append({"id": c, "isAlive": winner or rnd.random() < 0.3, "talent": 1, "talentId": tid,
                          "talentName": tname, "damage": rnd.randint(150, 1800) + (300 if winner else 0),
                          "heal": rnd.choice([0, 0, rnd.randint(100, 1500)]), "kills": rnd.randint(0, 2)})
        hp, value = [], 2850
        for _ in range(turns + 1):
            hp.append(max(0, value))
            value += rnd.randint(-450, 350) + (120 if winner else -60)
        stats = {"v": 1, "shops": turns, "rerolls": rnd.randint(0, 4), "freeRerolls": 0, "skips": rnd.randint(0, 2),
                 "skipGold": 0, "bans": [], "turns": turns, "turnTimeMs": rnd.randint(60, 240) * 1000,
                 "timeouts": 0, "disconnects": 0, "emotes": rnd.randint(0, 2), "hp": hp, "shop": []}
        return cards, stats

    w_deck, l_deck = (my_deck, opp_deck) if win else (opp_deck, my_deck)
    (w_cards, w_stats), (l_cards, l_stats) = side(w_deck, True), side(l_deck, False)
    buys = [{"userId": rnd.choice([me, opp]), "card": rnd.choice(my_deck + opp_deck), "tox": "demo",
             "bought": "demo", "cost": rnd.choice([10, 20, 40, 70]), "turn": rnd.randint(2, turns)} for _ in range(rnd.randint(1, 4))]
    return {"tid": uid, "isDraw": False, "winner": me if win else opp, "loser": opp if win else me,
            "starter": rnd.choice([me, opp]), "turnCount": turns, "jsonOfMatch": "",
            "totalDamageWinner": sum(c["damage"] for c in w_cards), "totalDamageLoser": sum(c["damage"] for c in l_cards),
            "totalHealWinner": sum(c["heal"] for c in w_cards), "totalHealLoser": sum(c["heal"] for c in l_cards),
            "cardsWinner": w_cards, "cardsLoser": l_cards, "toxPurchases": buys,
            "endCause": rnd.choice(["surrender", "surrender", "normal"]),
            "matchStatsWinner": w_stats, "matchStatsLoser": l_stats}


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
        "tested_with": "1.26", "count": len(cards), "cards": cards, "talents": TALENTS},
        ensure_ascii=False, indent=1), encoding="utf-8")

    ids = list(cards)
    decks = [ids[0:4], ids[0:3] + [ids[5]], [ids[1], ids[2], ids[6], ids[9]]]
    # chaque adversaire fictif joue toujours le meme deck (pour que les matchups se regroupent)
    opp_decks = [[ids[10], ids[11], ids[12], ids[13]], [ids[4], ids[7], ids[8], ids[14]],
                 [ids[3], ids[5], ids[9], ids[15]], [ids[6], ids[10], ids[13], ids[15]]]
    folder = target / "replays" / "demo.server" / ME
    folder.mkdir(parents=True, exist_ok=True)
    rnd = random.Random(7)
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
        uid, turns = f"match-{9000000 + n}", random.randint(3, 14)
        my_deck, opp_deck = decks[n % 3], opp_decks[n % 4]
        write_srpl(folder / f"{uid}.srpl", {"GameUid": uid, "AccountId": ME, "OpponentId": opp_id},
                   [(ME, my_deck), (opp_id, opp_deck)], fake_summary(rnd, uid, ME, opp_id, my_deck, opp_deck, win, turns))
        matches.append({
            "FormatVersion": 2, "AppVersion": "1.26", "GameUid": uid,
            "AccountId": ME, "Seat": 0, "GameMode": 10 if ranked else 0, "Level": "",
            "OpponentId": opp_id, "OpponentName": "IA d'entraînement" if ai else OPPONENTS[n % 8],
            "OpponentIsAi": ai, "WinnerId": ME if win else opp_id, "IsDraw": False,
            "MyCards": my_deck, "OpponentCards": opp_deck,
            "StartUtc": t0.isoformat().replace("+00:00", "Z"),
            "EndUtc": (t0 + timedelta(seconds=dur)).isoformat().replace("+00:00", "Z"),
            "DurationMs": dur * 1000, "MessageCount": 400, "TurnCount": turns,
            "Loading": {"matchId": f"match-{9000000 + n}",
                        "opponent": {"username": OPPONENTS[n % 8], "stars": 0 if ai else opp_stars,
                                     "rank": 0 if ai else my_rank + random.randint(-200, 200)},
                        "me": {"username": "Joueur", "stars": my_stars, "rank": my_rank}},
        })
    (folder / "index.json").write_text(json.dumps(matches[::-1], ensure_ascii=False), encoding="utf-8")
    print(f"Demo creee dans {target} : {len(matches)} matchs, {len(cards)} cartes fictives.")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
