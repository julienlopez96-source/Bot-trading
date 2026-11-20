# Bot-trading — bot de day trading Forex (MetaTrader 5)

Bot de day trading autonome sur le marché Forex, connecté à MetaTrader 5. Il détecte des signaux, calcule la taille de position en fonction du risque, pose les ordres avec stop-loss / take-profit attachés, et applique des limites de perte strictes.

**Avertissement** : aucun bot ne garantit d'être profitable. Le day trading comporte un risque de perte pouvant aller jusqu'à la totalité du capital. Teste d'abord en backtest puis en compte démo (dry-run), avec un petit capital réel ensuite.

## Prérequis

- Python 3.10+
- Mode `live` : **Windows uniquement**, terminal MetaTrader 5 ouvert et connecté (compte démo recommandé au début)
- Mode `backtest` : fonctionne partout, aucune connexion broker nécessaire

```bash
pip install -r requirements.txt
cp .env.example .env   # puis remplir MT5_LOGIN / MT5_PASSWORD / MT5_SERVER (jamais commité)
```

## Modes de fonctionnement

| Commande | Description |
|---|---|
| `python main.py --mode backtest --data data/EURUSD_M5.csv` | Backtest sur données historiques CSV (colonnes `time,open,high,low,close,tick_volume`) |
| `python main.py --mode live --dry-run` | Paper trading : lit les prix réels via MT5 (compte démo), **n'envoie aucun ordre**, logue les signaux |
| `python main.py --mode live` | Trading réel (met `dry_run: false` dans la config ou omets `--dry-run`) |

## Structure

```
forex_bot/
├── config.py        # chargement + validation de config.yaml et des variables d'env
├── models.py        # Rate, Signal, Position, OrderResult, AccountInfo
├── indicators.py    # EMA, ATR (pur Python)
├── broker.py        # interface Broker
├── mt5_broker.py    # connecteur MetaTrader 5 (Windows)
├── paper_broker.py  # simulation d'exécution (spread + slippage + SL/TP)
├── strategy.py      # croisement EMA + filtre ATR + spread + séance
├── risk.py          # sizing, perte max journalière, drawdown, cooldown, kill switch
├── engine.py        # boucle principale : données -> signal -> risque -> ordre
├── backtest.py      # backtest + métriques (win rate, profit factor, drawdown...)
└── monitoring.py    # logs JSONL + alertes Telegram
```

## Gestion du risque (risk.py + config.yaml)

- **Risque par trade** : `risk_per_trade_pct` (ex. 1 %) → taille de lot calculée pour perdre au maximum ce montant si le stop-loss est touché.
- **Stop-loss / take-profit** : envoyés au broker avec chaque ordre (hard SL côté serveur).
- **Perte journalière max** : `max_daily_loss_pct` → plus aucun nouvel ordre jusqu'au lendemain.
- **Drawdown max** : `max_drawdown_pct` → arrêt du bot.
- **Cooldown** : après `max_consecutive_losses` pertes d'affilée, pause de `cooldown_minutes`.
- **Kill switch** : créer le fichier `state/KILL_SWITCH` pour bloquer immédiatement tout nouvel ordre (`touch state/KILL_SWITCH`).
- **Clôture forcée** : toutes les positions sont fermées à `force_close_hour` (pas de portage overnight).

## News en direct (news.py, news_strategy.py)

- **Calendrier économique Forex Factory** (XML, fuseau New York) + **flux RSS** quelconques (détection de la devise et de l'impact par mots-clés).
- **Blackout** : aucun nouvel ordre de `blackout_minutes_before` à `blackout_minutes_after` autour d'une news `high`/`medium` portant sur une devise de la paire (config `news:`).
- **Stratégie news** : dans les `news_window_minutes` suivant une news `high`, si `actual` vs `forecast` dépasse `news_surprise_threshold` (écart relatif), le bot prend une position dans le sens de la devise concernée (SL/TP basés sur l'ATR). Les news sans chiffre `actual` ne produisent aucun signal (sécurité).
- Les news sont rafraîchies toutes les `poll_seconds` secondes ; une panne de flux n'arrête pas le bot (les dernières news connues restent en cache).

## Données de backtest

Exporte les barres M5 depuis MT5 (Terminal > Boîte à outils > Historique) ou toute source CSV avec les colonnes `time,open,high,low,close,tick_volume` (`time` = timestamp Unix ou ISO).

## Sécurité

- Les identifiants MT5 et le token Telegram passent **uniquement** par variables d'environnement (`.env`, gitignoré). Ne jamais les écrire dans le code.
- Le bot ne transfère aucun fonds (pas de retrait), il ne fait que passer des ordres sur le compte connecté.
- Le `magic` (20250601) permet d'identifier dans MT5 les ordres passés par ce bot.

## Tests

```bash
python -m unittest discover -s tests -t . -v
```
