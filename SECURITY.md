# Sécurité / Security

## Signaler un problème

Si tu trouves une faille (par exemple une donnée personnelle enregistrée ou affichée par erreur, ou
un moyen pour un site web d'agir sur l'application), **ne l'expose pas dans une issue publique**.
Utilise plutôt le bouton **"Report a vulnerability"** de l'onglet **Security** du dépôt GitHub
(signalement privé). Décris le problème et comment le reproduire, avec des données fictives.

## Ne publie jamais tes fichiers de jeu

Dans une issue, un message ou une capture, **ne joins jamais** :

- `index.json` ni les fichiers `.srpl` du dossier
  `%USERPROFILE%\AppData\LocalLow\Ticroco\Spam\replays\` : ils contiennent l'identifiant de ton
  compte (AccountId) et le **ticket de connexion** de tes matchs ;
- `spam.db`, `tracker.log` ou `settings.json` : ils contiennent ton historique de matchs et les
  pseudos de tes adversaires ;
- `Player.log` du jeu : il contient tes identifiants et ceux de tes amis.

Si une information de ces fichiers est nécessaire, recopie uniquement la ligne utile en remplaçant
les identifiants par `xxxx`.

---

## Reporting a problem

If you find a security issue (personal data stored or shown by mistake, a way for a web page to
control the app...), **do not open a public issue**. Use the **"Report a vulnerability"** button in
the repository's **Security** tab (private report), with steps to reproduce using fake data.

## Never post your game files

Never attach `index.json`, `.srpl` replays (they contain your AccountId and match connection
ticket), `spam.db`, `tracker.log`, `settings.json` or the game's `Player.log` to an issue. Copy
only the relevant line and replace identifiers with `xxxx`.
