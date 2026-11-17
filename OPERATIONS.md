# Operations guide — Sottocosto Oggi

## Before enabling production

1. Revoke the Telegram token exposed in the public `sottocosto-oggi` repository using @BotFather. Generate a new token.
2. Update the `TELEGRAM_BOT_TOKEN` GitHub Actions secret in this repository. Never paste the token into issues, logs, frontend code or pull requests.
3. Verify `TELEGRAM_CHANNEL_ID`, `AMAZON_CREDENTIAL_ID`, `AMAZON_CREDENTIAL_SECRET`, `AMAZON_PARTNER_TAG` secrets.
4. Check CI results on the pull request and perform a manual smoke test before merging.
5. Configure GitHub Environment `telegram-publishing` and its approval rules for the manual publication workflow.

## Emergency pause

Set repository **Settings → Secrets and variables → Actions → Variables → New repository variable**:

- Name: `BOT_PAUSED`
- Value: `true`

The scheduled bot job will be skipped. Set it to `false` or remove the variable to resume. Already running jobs are not interrupted; cancel them from Actions if necessary. The separate manual publishing workflow is unaffected.

## Monitoring

- Check Actions → Sottocosto Oggi Bot for execution failures and unusual runtime.
- Inspect Telegram posts for invalid prices, duplicates and broken links.
- Cache-based `posted_deals.json` and `daily_stats.json` are **not a durable database**. Cache eviction, restoration failures, or simultaneous external triggers can lose history. Do not rely on this storage for financial-grade price history.
- The current dashboard's AI-assisted product discovery is **not a verified source of live Amazon prices**.
- The legacy Prime Day 2026 campaign dates are fixed in the code and must be updated before any future campaign.

## Next architecture milestone

Replace the cache-based state with a durable datastore and atomic deduplication, then separate offer collection, scoring, approval policy and publishing into independent jobs. Use authenticated server-side endpoints and official permitted product data sources. Add telemetry and failure alerts before increasing posting frequency.

## Nuova piattaforma: attivazione sul branch della PR

Non distribuire finché i test della PR (SQLite e PostgreSQL) non sono verdi.
I workflow di pubblicazione usano l'ambiente `telegram-publishing`: configurare le
regole di approvazione e i branch autorizzati. La dashboard non pubblica messaggi.

1. Revocare il vecchio token con BotFather, verificare amministratori e messaggi
   del canale; inserire il nuovo token esclusivamente nei Secrets dell'ambiente.
2. Creare un database PostgreSQL persistente, con backup automatici e TLS
   (`sslmode=verify-full` e CA del fornitore, oppure configurazione equivalente).
   Impostare `DATABASE_URL` nello stesso ambiente di bot e pubblicazione manuale.
   Tutti i publisher devono usare lo STESSO database. Il codice crea le tabelle;
   usare un utente dedicato con permessi sul solo schema applicativo.
3. Impostare `BOT_PAUSED=true` prima della migrazione. Recuperare l'ultimo
   `posted_deals.json` dalla cache del vecchio workflow in un ambiente fidato;
   con DATABASE_URL impostata eseguire `python state_admin.py import FILE`.
   L'importazione è transazionale e idempotente. Non cancellare il vecchio
   storico finché conteggi e ASIN campione non sono stati confrontati.
   Senza importazione il database vuoto non conosce le precedenti pubblicazioni.
4. Configurare `HEALTHCHECK_URL` (secret facoltativo) presso il servizio heartbeat
   scelto: successo e `/fail` sono inviati senza riportare URL nei log.
   Configurare presso il servizio una finestra Europe/Rome 07–23, un margine
   di almeno 30 minuti per ritardi Actions e un allarme per heartbeat assente.
   Attivare anche le notifiche GitHub per workflow falliti. Senza questo servizio
   il monitoraggio rimane nei run e nella dashboard, senza allarme esterno.
5. Impostare `MIN_DEAL_SCORE` (variabile, default 20). Il punteggio 0–100 è una
   somma documentata in `scoring.py`; il minimo è quello osservato nei 30 giorni,
   non un minimo storico del mercato. La selezione alterna categorie e mantiene
   il miglior punteggio all'interno di ciascuna categoria.
6. Dopo CI e migrazione, eseguire una verifica controllata con token nuovo e
   canale di prova; solo dopo autorizzare il rilascio e togliere BOT_PAUSED.
   Questa PR non cambia main né invia un messaggio di prova automaticamente.

### Persistenza e invii incerti

GitHub Actions richiede DATABASE_URL: nessun ripiego silenzioso su cache o file.
Per un server con volume permanente si può usare
`DATABASE_URL=sqlite:////percorso/assoluto/deals.sqlite3`; non condividere SQLite
su filesystem di rete. PostgreSQL usa blocchi di riga; SQLite una transazione
IMMEDIATE. Un ribasso di almeno 5% consente la ripubblicazione entro 14 giorni.

La riserva viene confermata prima della rete. `pending` e `unknown` non scadono:
un crash dopo l'invio potrebbe aver consegnato il messaggio. Nessun retry o
fallback fotografico dopo un timeout. Le immagini Amazon restano disponibili;
la generazione di immagini brandate resta un modulo offline, fuori dall'invio.
Il conteggio giornaliero nella vecchia etichetta del messaggio conta ASIN unici;
la dashboard conserva ogni pubblicazione, inclusi i ribassi dello stesso ASIN.

Per riconciliare: `python state_admin.py status`, controllare prima il canale,
poi `python state_admin.py resolve ASIN --outcome sent --price 12.34` oppure
`--outcome not-sent` solo dopo aver escluso la consegna. Per messaggi speciali
usare la chiave completa `_am:AAAA-MM-GG`. Evitare esecuzioni concorrenti della
riconciliazione; nessuna modifica di stato è esposta via HTTP.

### Dashboard privata

Il repository Publisher contiene ora solo HTML/CSS/JS senza credenziali, AI,
proxy, prezzi sintetici o invio Telegram. Per vedere i dati occorre servirlo
insieme all'app WSGI del bot, sulla stessa origine:

- installare `requirements.txt` e `requirements-dashboard.txt`;
- `DASHBOARD_DIR`: percorso assoluto al checkout Publisher;
- `DASHBOARD_USER` e `DASHBOARD_PASSWORD`: credenziali dedicate, password casuale
  di almeno 20 caratteri, esclusivamente sul server;
- stessa DATABASE_URL dei worker; preferire un ruolo di lettura per la dashboard
  dopo aver creato le tabelle con il ruolo di migrazione;
- avviare `gunicorn --bind 127.0.0.1:8000 dashboard:application` dietro proxy HTTPS;
  fidarsi degli header forwarded SOLO dal proxy locale. Il proxy deve imporre
  limiti ai tentativi di autenticazione e alle richieste. Non esporre la porta
  applicativa direttamente su Internet. Nessun CORS pubblico.

Tutte le risorse e `/api/status`, `/healthz` richiedono autenticazione.
`/healthz` restituisce 503 per run falliti, vecchi di oltre un'ora o invii sospesi;
fuori fascia oraria tale stato è atteso. `DASHBOARD_ALLOW_HTTP=true` è solo per
sviluppo locale. GitHub Pages mostra la struttura, ma non fornisce il backend.
Nessun token Telegram o database deve essere inserito nel browser.

### Backup, conservazione e rollback

Osservazioni prezzi: 30 giorni; run: 90 giorni; pubblicazioni e riserve: conservate
per audit. Valutare volume e retention prima di carichi elevati. Usare backup
PostgreSQL del fornitore con recupero puntuale; provare il ripristino su un DB
separato, confrontando pubblicazioni e riserve prima di riattivare gli invii.
Non caricare dump negli artifact pubblici o nel repository.

Rollback: BOT_PAUSED=true, fermare i publisher, ripristinare il commit applicativo
precedente compatibile con il database. Non ripartire dal vecchio workflow su
cache: perderebbe le riserve e la deduplicazione. Dopo ripristino DB, riconciliare
sempre i messaggi successivi all'ultimo backup prima di riattivare il bot.

Il Creator rimane separato e usa ancora una cache per il proprio offset: questo
non controlla gli invii offerte; la sua migrazione persistente è un seguito.
Ora richiede ADMIN_ID esplicito e rispetta BOT_PAUSED nel workflow.
