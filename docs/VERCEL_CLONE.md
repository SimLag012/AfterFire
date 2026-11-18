# Clone statico AfterFire per Vercel Hobby

Il clone si trova in `public-demo/`. Riutilizza il frontend originale: stessa App, router, Explorer, pannello candidati, pulsante **Analyze candidate**, calendario, mappe, grafici e fogli di stile. Non esiste una seconda App o una schermata demo alternativa. Il frontend locale `frontend/` e il backend non vengono modificati.

Nel clone cambiano il trasporto delle risposte, l'etichetta di disponibilità dei dati e i controlli che richiedono elaborazioni/acquisizioni. Gli stessi componenti leggono pubblicazioni scientifiche statiche invece di FastAPI. La dicitura **PUBLIC DEMO** appare nel riepilogo originale delle osservazioni e nello stato della navigazione; Data & Sources descrive la copertura limitata.

## Dati disponibili

Lo snapshot preparato include cinque candidati già elaborati:

| Località originale | Osservazioni FIRMS del candidato |
| --- | --- |
| Ródos, Grecia | 21–22 luglio 2023 |
| Morphett Vale, Australia | 2–3 gennaio 2020 |
| Paradise, Stati Uniti | 1–3 agosto 2021 |
| Fouchana, Tunisia | 14 luglio 2026 |
| Iglesias, Italia | 16 luglio 2026 |

Contiene le cinque Recovery Story, le serie NDVI/EVI pubblicate, tre assessment Recovery Intelligence coerenti con le sorgenti e due pubblicazioni Reburn. Il candidato americano del 2021 include 81 osservazioni FIRMS e i compositi MODIS pre/post autentici già pubblicati; sostituisce nella selezione pubblica il candidato del 2012 privo di dati MOD13Q1. Le pubblicazioni locali originali restano invariate. Fouchana mantiene il proprio Before/After ottico autentico: non dispone di una coppia MODIS valida pre/post e le lacune non vengono riempite.

Sono inclusi tre studi Fire Activity: Ródos luglio 2023, Sardegna luglio 2021 e studio **parziale** Sardegna novembre 2000–novembre 2026. Un intervallo richiesto non significa copertura continua: null, finestre mancanti, qualità d'archivio, conteggi originali MODIS/VIIRS, calibrazione e anomalie restano quelli delle pubblicazioni locali.

Un assessment australiano con fingerprint della sorgente non più coerente viene escluso, esattamente come nell'API originale. L'omissione è registrata in `public-demo/public/demo/manifest.json`. Non si inventano analisi per completare la demo.

La dimensione dello snapshot è riportata in `manifest.json` (`total_bytes`). JSON e GeoJSON grandi sono compressi lossless in gzip, i PNG sono ottimizzati senza quantizzazione, e gli oggetti identici condividono lo stesso nome SHA256. Le serie delle celle Reburn sono suddivise in gruppi di 32 per caricarle su richiesta. I valori scientifici, le versioni, il QA e le provenienze sono conservati; non si modificano formule o algoritmi.

## Preparazione e avvio

Dal repository `afterfire`:

```bash
python scripts/prepare_vercel_clone.py
python scripts/export_vercel_demo_docker.py
python scripts/check_vercel_clone.py
npm --prefix public-demo ci
npm --prefix public-demo run build
python scripts/serve_vercel_clone.py
```

Aprire `http://127.0.0.1:4173`. Il server serve esclusivamente `public-demo/dist`, applica il fallback SPA e restituisce 404 per `/api/`. Non avvia FastAPI o worker. In alternativa, `npm --prefix public-demo run preview` usa il preview Vite.

`prepare_vercel_clone.py` copia i file frontend correnti e applica adattamenti espliciti a bootstrap, trasporto e disponibilità delle operazioni. Non riscrive il layout. `clone-source.json` registra gli hash di tutti i file sorgente e l'elenco degli adattamenti. Il controllo verifica che App, componenti mappa, grafici e tutti i CSS mantengano gli stessi byte degli originali. Se il frontend originale cambia, rieseguire la preparazione: se una modifica impedisce un adattamento sicuro, lo script si interrompe e richiede di rivedere quel punto.

Sul computer di preparazione può essere presente un collegamento locale `public-demo/node_modules` alle dipendenze di `frontend`; è ignorato da Git e Vercel. Il progetto pubblicato installa autonomamente le dipendenze con `npm ci`.

## Esportare nuovamente

`scripts/vercel_demo_selection.json` fissa esplicitamente coppie `event_id`/`source_job_id` e ID degli studi da includere. Per aggiungere candidati, elaborarli e verificarli prima nell'applicazione locale originale, poi aggiornare l'allowlist. Il clone non acquisisce o calcola nuove osservazioni. Con `require_before_after: true`, l’export e il controllo di integrità richiedono per ogni candidato una coppia MODIS NDVI/EVI pre/post con anteprime esportate, oppure una coppia ottica originale esportata con date prima e dopo l’evento. Il test browser controlla che le immagini siano effettivamente caricate.

Il wrapper Docker usa il container locale esistente `afterfire-clean-backend-1` e i suoi database/cache. Per un'installazione diversa:

```bash
python scripts/export_vercel_demo_docker.py --container NOME_BACKEND_LOCALE
```

Il wrapper rifiuta daemon Docker remoti: tutte le copie avvengono sul computer locale, senza upload esterni. Richiede solo Python standard e Docker sul computer; le dipendenze scientifiche sono quelle già installate nel container. Il container deve essere avviato per eseguire Python, ma l'exporter non usa il server HTTP e non avvia worker.

Per eseguire direttamente l'exporter nell'ambiente Python del backend:

```bash
PYTHONPATH=backend backend/.venv/bin/python scripts/export_vercel_demo.py \
  --selection scripts/vercel_demo_selection.json \
  --database-url "sqlite+aiosqlite:///$PWD/backend/afterfire.db" \
  --cache-dir "$PWD/.local-runtime/analysis-cache" \
  --output public-demo/public/demo
```

Per PostgreSQL si può impostare `DATABASE_URL` nell'ambiente locale invece di passarla sulla riga di comando. I vecchi database SQLite potrebbero non contenere le pubblicazioni selezionate: l'export fallisce senza sostituirle con seed o fixture.

L'esportazione usa PostgreSQL repeatable-read/read-only o SQLite `query_only`. Non importa lifespan/migrazioni, non scrive pubblicazioni e blocca le richieste HTTP dei provider. Le anteprime mancanti sono renderizzate dai checkpoint nativi già pubblicati dopo verifica checksum, con il renderer originale e senza scrivere nella cache scientifica. Le anteprime ottiche sono copiate solo se già disponibili localmente.

L'output viene validato in staging e sostituisce atomicamente soltanto una directory marcata come proprietà dell'exporter. Il limite predefinito è 80 MiB, modificabile con `--max-mb`. Sono esclusi database, cache complete, raw payload, credenziali, GeoTIFF nativi e metadati operativi privati (percorsi locali, token, task/project ID). Annotazioni riservate sconosciute interrompono l'export.

## Comportamento del clone

- L'Explorer originale mostra inizialmente i cinque candidati nel loro pannello, con i suoi normali pulsanti **Show on map** e **Analyze candidate**. Cambiando posizione, date, sensore o satellite si filtra soltanto il sottoinsieme statico.
- La ricerca geografica trova le località dei candidati esportati. La navigazione fuori dalla copertura resta possibile sulla mappa e restituisce zero dati del sottoinsieme; questo non dimostra assenza di incendi.
- Recovery usa la pubblicazione fissata nell'allowlist, con selezione NDVI/EVI, timeline, Before/After, raster, mappe e serie delle celle originali.
- Il calendario storico usa la sua selezione **Cached study**, i mesi e le statistiche originali; le nuove acquisizioni e la ripresa di finestre sono disabilitate.
- Nuove analisi, preflight, cambi di assessment che richiedono ricalcoli, importazioni CSV, amministrazione, nuove spiegazioni e generazione di report sono disabilitati. Le comparazioni sono disponibili solo se già pubblicate ed esportate; lo snapshot corrente non include comparazioni salvate.
- I link di download nativi non esportati restano disabilitati. La sezione originale dei download permette di scaricare il JSON scientifico pubblicato. I `.json.gz`/`.geojson.gz` vanno decompressi prima di usarli in strumenti esterni.
- Non esiste un fallback FastAPI. Tutte le istanze Axios, compresa la selezione originale dei candidati globali, usano il trasporto statico; il `fetch` del calendario è indirizzato allo stesso lettore. Gli stati terminali pubblicati non aprono stream.

Le tile Esri, l'eventuale overlay NASA GIBS e i font/CSS pubblici già usati dall'originale rimangono dipendenze browser esterne, con le attribuzioni originali. Non richiedono backend o account cloud a pagamento. La disponibilità del basemap non modifica le misure e i raster scientifici statici. Non vengono copiate o esportate le cache delle tile.

## Impostazioni Vercel

Il push Git resta a cura dell’utente. La pubblicazione iniziale e gli aggiornamenti esplicitamente richiesti sono eseguiti sul progetto statico Vercel indicato sotto, senza collegamento Git automatico.

| Impostazione | Valore |
| --- | --- |
| Piano | Hobby, entro quote e condizioni del piano |
| Root Directory | `public-demo`, nel repository `afterfire` |
| Include source files outside Root Directory | Disattivato |
| Framework Preset | Vite |
| Node.js | 22.x |
| Install Command | `npm ci` |
| Build Command | `npm run build` |
| Output Directory | `dist` |
| Variabili d'ambiente | Nessuna |
| Database, Functions, worker, storage cloud | Nessuno |

Se il repository importato contiene `afterfire` come sottocartella, Root Directory diventa `afterfire/public-demo`. Non copiare `.env`, chiavi NASA/Earthdata/Google o URL del database. Su Vercel non si esegue l'export: basta il clone con lo snapshot già preparato.

`public-demo/vercel.json` include il rewrite SPA per navigazione e refresh di `/explorer`, `/events/:id`, `/events/:id/reburn`, `/datasets` e delle rotte originali. `/api/`, `/demo/` e `/assets/` sono esclusi dal fallback: le risorse mancanti restano 404. Gli oggetti SHA256 sono immutabili; il manifest viene rivalidato.

Riferimenti: [Vercel per Vite](https://vercel.com/docs/frameworks/frontend/vite), [configurazione dei rewrite](https://vercel.com/docs/project-configuration/vercel-json).

## Verifiche e aggiornamento

```bash
python scripts/test_vercel_export.py
python scripts/check_vercel_clone.py
npm --prefix public-demo run build
python scripts/serve_vercel_clone.py
```

Con Playwright/Chromium installati come strumenti esterni:

```bash
PLAYWRIGHT_MODULE=/percorso/playwright/index.mjs \
AF_CHROMIUM_EXECUTABLE=/percorso/chromium \
node scripts/verify_vercel_clone_browser.mjs
```

Il browser usa `http://afterfire.test:4173`, risolto da Chromium sul server di test locale, per verificare che nessuna URL di backend/localhost sia richiesta. Non intercetta né simula le osservazioni. La prova copre i controlli originali, i cinque candidati attraverso **Analyze candidate**, filtri, mappe/celle, Before/After, calendario storico, navigazione, refresh SPA e schermate a 375/768/1440 px. Report e screenshot: `/tmp/afterfire-vercel-clone-browser`, modificabile con `AF_CLONE_EVIDENCE`. Per ripetere la prova senza backend, fermare temporaneamente backend/worker locali e riavviarli dopo il test.

`scripts/verify_vercel_sources.py DIRECTORY_EXPORT`, eseguito nell'ambiente del backend con `PYTHONPATH=backend`, confronta fingerprint e valori esportati con le pubblicazioni originali in transazione read-only.

Per aggiornare il sito: verificare i nuovi risultati nell'app locale, aggiornare l'allowlist, rieseguire preparazione/export/controlli/build e infine pubblicare personalmente il solo progetto `public-demo`. Le modifiche locali indipendenti alla documentazione e al progetto principale restano separate dal clone.

## API originali e corrispondenza statica

Il namespace originale è `/api/v1`. Il clone non espone un server con queste route: il trasporto restituisce i file statici usando gli stessi contratti dati.

| API usata dalla UI originale | Nel clone |
| --- | --- |
| `/global/hotspots`, `/explorer/hotspots`, `/explorer/events`, `/explorer/clusters`, `/explorer/search`, `/italy/coverage` | Filtro locale dei candidati e delle osservazioni esportate, conteggi reali del sottoinsieme, ricerca nelle località pubblicate |
| `POST /global/events/:id/select`, `GET /events/:id` | Selezione in sola lettura e dettaglio autentico dell'ID già esportato |
| `/events/:id/analysis/status`, `/analysis/result`, `/analysis/assets/:job/:name`, `/analysis/optical-preview` | Pubblicazione fissata nell'allowlist e anteprime PNG statiche |
| `POST /events/:id/analysis`, `/analysis/preflight`, stream | Nessuna nuova analisi, preflight o stream; controlli disabilitati |
| `/events/:id/recovery-assessment/result`, `/map`, `/cells/:cell`, `/recovery-assessments` | Summary pubblicato, layer per indice/data e serie native; la proiezione della data è la stessa presentazione della route originale |
| `POST /events/:id/recovery-assessment`, relativi asset GeoTIFF e stream | Nuovi assessment e download non esportati disabilitati |
| `/reburn-sources`, `/events/:id/reburn-analysis/status`, `/result`, `/reburn-map`, `/reburn-cells/:cell` | Storie, mappe e serie delle celle già pubblicate |
| Nuovo Reburn/preflight, acquisizione mancante, stream | Disabilitati |
| `/fire-activity/studies`, `/studies/:id`, `/status`, `/months/:month`, `/sources` | Studi storici esportati, statistiche e osservazioni originali; disponibilità dichiarata come snapshot, senza probe NASA |
| Creazione/pausa/ripresa Fire Activity, export CSV dinamico | Disabilitati; calendario/provenienza JSON statici disponibili |
| `/datasets`, `/health`, `/status`, `/areas` | Catalogo metadati, stato esplicito PUBLIC_DEMO e sole aree associate alle pubblicazioni esportate |
| Nuovi `/reports`, spiegazioni AI, `/import/firms-csv`, `/admin/satellite-cache`, nuove comparazioni | Disabilitati, senza fallback backend |


## Esito della verifica locale · 17 novembre 2026

- Build di produzione del clone superata; lockfile verificato con `npm ci --dry-run`.
- Controllo sorgenti: 44 file originali registrati, 30 identici byte per byte; 14 adattamenti a trasporto/disponibilità. App/router, componenti mappa, grafici e tutti i CSS originali sono invariati. `git diff -- frontend` non mostra modifiche al progetto originale.
- Snapshot: 5 candidati, 3 studi, 858 oggetti; 6.014.545 byte di dati/asset. Esportazione locale Docker ripetuta con successo.
- Cinque test exporter superati per numeri/null, metadati privati, rifiuto di annotazioni riservate, compressione/deduplicazione e limite dimensionale.
- Confronto read-only con il database: 12 pubblicazioni con fingerprint invariati e valori scientifici/mappe/serie originali uguali dopo la rimozione dei soli metadati operativi privati.
- Test Chromium con backend e worker fermi: **PASS**, 808 richieste, zero chiamate API/localhost, zero risorse statiche fallite, zero errori JavaScript. Backend e worker sono stati riavviati.
- Tutti i cinque candidati sono stati aperti tramite il pulsante originale **Analyze candidate**, con verifica di NDVI/EVI, Before/After, timeline e mappe/celle disponibili; verificati anche filtri, salvataggio/ripristino vista, calendario storico e collegamento Recovery, Data & Sources e refresh SPA.
- Screenshot a 375, 768 e 1440 px senza overflow orizzontale, in `/tmp/afterfire-vercel-clone-browser`. La parità dei sorgenti/CSS è verificata; non viene dichiarato un confronto pixel-per-pixel con una baseline a dati identici né una certificazione WCAG completa.
- Alla conclusione della verifica locale del 17 novembre non erano stati eseguiti push, deploy o upload esterni.

## Pubblicazione verificata · 18 novembre 2026

URL pubblico: **[afterfire-public-demo.vercel.app](https://afterfire-public-demo.vercel.app)**.

Su autorizzazione esplicita dell'utente, è stato creato il progetto Vercel `afterfire-public-demo` nel team `simlag012s-projects` e pubblicato il deployment di produzione `dpl_HYkEDhNrPfWRSVK3xW4QPZ8hCdAh`, stato **READY**. È stato caricato via API soltanto il pacchetto già compilato e verificato: 881 file, 7.542.369 byte, inclusa la configurazione Vercel. Nessun collegamento Git, push, backend, database, worker o credenziale caricato.

Questa prima pubblicazione usa il preset **Other** (`framework: null`) e nessun comando di installazione/build remoto: i file Vite erano già compilati localmente. Per le future build dai sorgenti restano valide le impostazioni Vite/Node 22/npm/dist sopra documentate, usando la directory `public-demo`.

- Accesso HTTPS pubblico verificato senza autenticazione; `/api/health` restituisce 404.
- Verificati gli SHA-256 di tutti gli 880 file pubblici confrontandoli con il pacchetto locale; `vercel.json` è configurazione di deploy.
- Header CSP e `X-Content-Type-Options: nosniff` presenti; cache immutabile per gli oggetti e rivalidazione del manifest configurate.
- Test Chromium sull'URL pubblico: **PASS**, 813 richieste, zero chiamate backend/localhost, zero errori JavaScript/CSP o risorse statiche fallite. Verificati i cinque candidati, Recovery, calendario storico, filtri, Before/After, refresh SPA e layout a 375/768/1440 px.
- Evidenze locali: `/tmp/afterfire-vercel-production-browser/report.json` e `.local-runtime/vercel-release/production-http-report.json`. Questi percorsi di verifica non vengono pubblicati.
- README aggiornato localmente con il link pubblico; il push resta a carico dell'utente.

## Aggiornamento Before/After · 18 novembre 2026

La selezione pubblica sostituisce il candidato di Paradise del 2012, senza osservazioni MOD13Q1 valide, con il candidato autentico `global-a67a52521ea9434f0783e0677b664c42` del 1–3 agosto 2021 (81 rilevamenti FIRMS). La pubblicazione locale `4d7ebffb9755e7ffb7f9dee17d993a203551d93685c2d0a8fd46a70a7deffbda` offre 29 compositi pre-evento e 14 post-evento validi per ciascuno degli indici NDVI/EVI. Nessun ricalcolo scientifico, acquisizione o modifica alle pubblicazioni originali.

Il controllo `require_before_after` ora blocca l'export di candidati senza confronti visivi autentici esportabili. I test browser richiedono il caricamento effettivo delle immagini, anziché consentire un Before/After assente. Fouchana conserva la propria coppia ottica originale; questo non implica la disponibilità di compositi MODIS post-evento validi.

- Snapshot corrente: 5 candidati, 3 studi, 10 pubblicazioni scientifiche, 962 oggetti e 5.259.314 byte di dati/asset.
- Sette test exporter superati; confronto read-only delle 10 pubblicazioni e dei valori scientifici superato; build e parità dei sorgenti/CSS originali superate.
- Deployment produzione `dpl_8tQ13N1eh4V1kLhEQBDuqmgBzrqy`: **READY**, stesso [URL pubblico](https://afterfire-public-demo.vercel.app). Pacchetto esclusivamente statico di 985 file, 6.769.945 byte inclusa configurazione.
- Verificati online tutti i 984 file pubblici tramite SHA-256; API assente (404), accesso senza autenticazione e header di sicurezza presenti.
- Chromium sul sito pubblico: **PASS**, 824 richieste, zero backend/localhost, zero errori JavaScript/CSP o risorse statiche fallite. Tutti i candidati hanno immagini Before/After caricate, MODIS o coppia ottica originale dove disponibile.
- Evidenze locali: `/tmp/afterfire-before-after-production/report.json`, screenshot `/tmp/afterfire-before-after-production/before-after-us.png`, `.local-runtime/vercel-release/before-after-production-http-report.json`.
- Nessun push Git eseguito.
