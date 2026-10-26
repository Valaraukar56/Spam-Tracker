# SPAM Tracker

*[Version française](README.md)*

Match tracker for the card game **SPAM** (Ticroco, Steam), for Windows: results, decks, opponents,
rank and leaderboard position, in a desktop app.

> **Unofficial fan project.** SPAM Tracker is not affiliated with or endorsed by Ticroco. The game,
> card names, card data and illustrations belong to **Ticroco** and their artists. **No game content
> is distributed in this repository**: card names and illustrations are extracted on your own
> computer, from your own installation of the game.

![Home: last match, record and progression](docs/screenshots/home.png)

*Screenshots made with fully fictional demo data (made-up players, cards and artwork). The
interface is in French.*

## Features

- **Records every match** as soon as it ends: result, mode (Casual, Ranked...), both decks, turns,
  duration, opponent, rank.
- **Keeps your whole history** in a local database. The game itself only keeps your last 10 matches.
- **Home**: last match face-off, record, current streak, recent form and leaderboard position chart.
- **History**: all your games, filtered by All / Casual / Ranked. Click a game to see its details: who
  started, how it ended, damage, healing and kills of each card, talents, in-game purchases and the HP
  chart of both players.
- **Decks**: your decks (grouped by starting cards, even when a card transforms during the game), win
  rate when you start or not, matchups against each opposing deck, and average stats per card.
- **Opponents**: the cards that beat you most often and the players you met. Games against the AI
  are kept separate.
- **Card art**: after clicking "Préparer les cartes" (Prepare cards), cards show their name and
  illustration.
- Closing the window keeps it running in the **notification area**. It can also start with Windows.

| Decks | Opponents | Settings |
|---|---|---|
| ![Decks](docs/screenshots/decks.png) | ![Opponents](docs/screenshots/opponents.png) | ![Settings](docs/screenshots/settings.png) |

## Installation

Step-by-step guide for beginners: **[docs/INSTALLATION.en.md](docs/INSTALLATION.en.md)**.

In short: download `SPAM-Tracker.exe` from the [**Releases**](https://github.com/Valaraukar56/Spam-Tracker/releases/latest) page, put it in its own folder (for
example `Documents\SPAM Tracker`), run it, then click **Réglages > Préparer les cartes**.

## How it works (and what it does not do)

- **It only reads files the game writes to your disk**: after each match, SPAM writes a summary to
  `%USERPROFILE%\AppData\LocalLow\Ticroco\Spam\replays\...\index.json`. SPAM Tracker watches this
  file and adds new matches to its database.
- **"Prepare cards"** reads your game installation files (`SPAM_Data\resources.assets`...)
  read-only. It makes a temporary working copy, extracts names and thumbnails, then deletes the copy.
- **No outgoing network connection.** The interface is served by a small local server only reachable
  from your PC (`127.0.0.1:8765`). It rejects requests from other websites.
- **It does not modify the game**, inject anything, **read its memory** or intercept its traffic.
- **Privacy**: your account identifier (AccountId) and the connection ticket found in the game's
  files are **never stored or displayed**. The game's `.srpl` replays are not copied.
- **All data stays in the app folder**: `spam.db` (your matches), `catalog.json` and `cards\`
  (cards), `settings.json`, `tracker.log` and `webview-cache\`.

## Build it yourself

If you prefer not to trust the published exe, rebuild it from source.

Requirements: Windows 10 or 11, [Python 3.13](https://www.python.org/downloads/windows/).

```powershell
git clone https://github.com/Valaraukar56/Spam-Tracker.git
cd Spam-Tracker
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
powershell -ExecutionPolicy Bypass -File build.ps1
```

Output in `dist\`: `SPAM-Tracker.exe` and `SHA256SUMS.txt`. You can also run without building:
`.\.venv\Scripts\python.exe app.py`.

Extra tools: `python tracker.py stats`, `python tracker.py decks`,
`python extract_catalog.py --images` and `python tools\make_demo.py <folder>` (fictional data).

## Known limitations

- **The game only keeps your last 10 matches.** SPAM Tracker must be running while you play, or at
  least started before you play 10 new games, otherwise older ones are lost. Enable "start with
  Windows" so you don't have to think about it.
- **Card extraction may break after a game update.** The internal card format was decoded by hand
  for game version **1.26**. The app warns you if the version changes. Without a catalog it still
  works and cards are shown by their identifier.
- **Windows only** (10 and 11).
- **Not decoded**: move-by-move replay content (`.srpl`), ability descriptions, and one numeric card
  value whose meaning is unknown.
- **Rank** is derived from the Ranked mode data the game records at the start of each match. It
  does not change in Casual games.
- Preparing cards needs about **2.5 GB of temporary free space** on the app's drive, and a few minutes.

## Troubleshooting

**Matches are not detected**: make sure SPAM Tracker is running (notification area icon). A match
appears only **after it ends**. The "Aucun match SPAM trouvé" banner means the game has not created
its replays folder yet: play a full game. Check `tracker.log` in the app folder.

**Card images are missing**: go to **Réglages > Préparer les cartes**, and do it again after each game
update. If the game is not found, set its folder in **Réglages > Dossier du jeu** (Steam: right
click SPAM > Manage > Browse local files). On failure, the message and `tracker.log` explain why.

**Antivirus blocks the exe**: unsigned PyInstaller executables are sometimes flagged by mistake.
Check the SHA-256 checksum (see the installation guide), then allow the file, or build it yourself.

**"WebView2 est absent" message**: the window uses Microsoft Edge WebView2 (built into Windows 11 and
most Windows 10). Without it, the dashboard opens in your browser and everything still works.
Install "Microsoft Edge WebView2 Runtime" from Microsoft to get the built-in window.

## License

- Code: **MIT** license (see [LICENSE](LICENSE)). It does not cover game content.
- SPAM, its cards and illustrations: © Ticroco and their artists.
- Security and personal data: see [SECURITY.md](SECURITY.md). Never post your `index.json`, `.srpl`
  files or `spam.db`.
