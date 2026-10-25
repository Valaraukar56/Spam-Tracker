# SPAM Tracker 1.0.0

Première version publique. / First public release.

## Français

Suivi de tes parties de **SPAM** (Ticroco) sur Windows, dans une application de bureau.

**Nouveautés**
- Enregistrement automatique de chaque match terminé : résultat, mode, decks, tours, durée,
  adversaire et rang. L'historique est conservé au-delà des 10 matchs gardés par le jeu.
- Accueil avec le dernier match en face-à-face, le bilan, la série, la forme récente et l'évolution
  de la position au classement.
- Onglets Decks (taux de victoire, meilleures cartes) et Adversaires (cartes qui te battent, joueurs
  rencontrés). Les parties contre l'IA sont mises à part.
- **Préparer les cartes** : extraction locale des noms et illustrations depuis ta propre
  installation du jeu, avec barre de progression. Les fichiers temporaires sont supprimés ensuite.
- Détection automatique du jeu (AppID 2902720) dans toutes les bibliothèques Steam, ou choix manuel
  du dossier.
- Avertissement si la version du jeu change (extraction vérifiée pour la version 1.26).
- Zone de notification, lancement au démarrage de Windows, fenêtre sombre.

**Confidentialité** : aucune connexion réseau sortante, aucune lecture de la mémoire du jeu, aucun
fichier du jeu modifié. L'AccountId et le ticket de connexion ne sont ni enregistrés ni affichés.

**Installation** : télécharge `SPAM-Tracker.exe` et `SHA256SUMS.txt`, vérifie l'empreinte, puis suis
le [guide d'installation](docs/INSTALLATION.md). Windows SmartScreen peut afficher un avertissement,
car l'exe n'est pas signé : "Informations complémentaires" puis "Exécuter quand même".

**Limites** : Windows uniquement. Le jeu ne garde que 10 matchs, donc laisse l'application tourner
quand tu joues. La préparation des cartes peut ne plus fonctionner après une mise à jour du jeu.

Projet de fan non affilié à Ticroco. Aucun contenu du jeu n'est inclus.

## English

Match tracker for **SPAM** (Ticroco) on Windows, as a desktop app.

- Automatic recording of every finished match (result, mode, decks, turns, duration, opponent,
  rank), with history kept beyond the game's 10 most recent matches.
- Home, Decks and Opponents views. Games against the AI are kept separate.
- **Prepare cards**: local extraction of card names and artwork from your own game installation,
  with a progress bar. Temporary files are deleted afterwards.
- Automatic game detection (AppID 2902720) across all Steam libraries, or manual folder selection.
- Warning when the game version changes (extraction verified for version 1.26).
- No outgoing network connection, no memory reading, game files never modified. AccountId and
  connection ticket are never stored or displayed.

Download `SPAM-Tracker.exe` and `SHA256SUMS.txt`, verify the checksum and follow the
[installation guide](docs/INSTALLATION.en.md). SmartScreen may warn because the exe is unsigned:
"More info", then "Run anyway".

Unofficial fan project, not affiliated with Ticroco. No game content is included.

**SHA-256** (`SPAM-Tracker.exe`) : `6e3697b4ed2b95fb55e56f8b104a8048e1234a4b399ebcc74abbdc88dbd6e889`
