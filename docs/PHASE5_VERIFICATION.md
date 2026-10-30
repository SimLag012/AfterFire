# AfterFire — verifica e consegna Fase 5

Verifica del 29 ottobre 2026, Europe/Rome. Implementazione nel repository esistente, con conservazione delle modifiche precedenti. Nessun import globale, nessun reset dell’archivio, nessuna previsione ML. Le evidenze distinguono dati NASA reali, fixture controllate e limiti non validati.

## 1–8. Infrastruttura, misure, configurazione e sicurezza

**Causa verificata della lentezza.** La Fase 4 teneva aperta la POST durante discovery e controlli della cache; il suo rapporto documentava >120 s e 499 del proxy. Nella misura Fase 5 dello stesso evento/configurazione, il planner completo richiedeva 154,47 s: 147,38 s di verifica cache/piano, circa 6,05 s di parete per i due cataloghi CMR concorrenti (11,48 s sommando HTTP concorrente). Le letture/checksum di circa 3,89 GB di sorgenti dominavano il tempo: non era corretto attribuire tutto alla rete NASA.

**Architettura.** POST → job deterministico nella coda DB esistente → risposta 202 → worker con lease/heartbeat/fencing → piano persistito → GET/SSE. Nessuna submission remota o acquisizione scientifica nel planner. Due richieste uguali riusano l’ID; il reload non annulla il lavoro. TTL piano 6 ore; errori provider sono failed con retry esplicito, non “nessun dato”. Le quote vengono rivalutate dalla pipeline prima dell’acquisizione. [Contratto API e diagramma](ASYNC_PREFLIGHT.md).

**Tempi misurati.** Prima creazione asincrona reale: 0,293 s; richieste successive misurate circa 0,22–1,43 s (ultima 1,427757 s, durante altre verifiche). Questa è la latenza di restituzione dell’ID, non il tempo NASA. Nel benchmark separato sullo stesso piano, con cataloghi in cache e zero byte scientifici nuovi: primo popolamento dell’indice di integrità 99.83 s, riuso 33.25 s. Non è promesso un tempo fisso per richieste esterne. I confronti freddo/caldo descrivono esplicitamente condizioni diverse; il 499 storico non è un benchmark controllato della rete attuale. [Misure pianificazione](phase5-planning-benchmark.jsonl), [stati e latenza API](phase5-real-verification.json).

**Metadati e integrità.** Cache NASA dedicata con provenienza, timestamp, TTL 24 ore (1 ora per discovery recente), risultati vuoti validi e lock cross-process; gli errori non diventano risposte vuote. Controlli CMR/AppEEARS separati e prodotti validati senza POST task. Una verifica HDF è riutilizzata soltanto con stesso dispositivo/inode/dimensione/mtime/ctime/checksum/identità/versione validatore e TTL non scaduto; una modifica forza hash e validazione completi. La pipeline riusa direttamente una sorgente appena verificata, evitando il secondo passaggio nel downloader. Le classi QA e la georeferenziazione restano validate.

**Cleanup.** Inventario da filesystem, inode condivisi contati una volta, byte logici/allocati e volume libero distinti. LRU conservativa, lock esclusivo non bloccante contro lease condivisi di lettura/scrittura, controllo di generazione prima della cancellazione. Sono protetti risultati, PNG/GeoTIFF pubblicati, manifest, lock, temporanei e sorgenti con retention attiva. Il trigger è prima dell’acquisizione o CLI amministrativa, non l’avvio Docker. [Policy completa e dry-run](CACHE_MANAGEMENT.md).

**Spazio realmente recuperato.** Solo su volume temporaneo: 6,291,456 byte logici e 6,291,456 byte allocati (6 MiB). Dry-run senza rimozioni; lease attivo senza rimozioni; asset, manifest, hardlink e archivio di controllo conservati. [Evidenza filesystem](phase5-cache-verification.json). Non è stato eseguito un cleanup distruttivo del volume scientifico reale per gonfiare il risultato.

**Limiti conservati.** Rete/job 5 GiB; blocco 1 GiB; temporanei 1 GiB; risultati derivati 2 GiB; cache 10 GiB; riserva libera 1 GiB. Aggiunti TTL, soglie cleanup 85%→70%, token admin opzionale e limite 2.000.000 coppie cella/data per indice. Dati e percorsi amministrativi non sono pubblici: diagnostica richiede bearer token configurato; nessun endpoint pubblico di cancellazione. Il database FIRMS rimane fuori dalla directory gestita.

**Ulteriore affidabilità.** La prova browser ha riprodotto un 502 con API diretta funzionante: Nginx conservava l’IP precedente del backend ricreato. `frontend/nginx.conf` usa il resolver Docker con rinnovo DNS; frontend e proxy sono stati verificati dopo ricreazione. La diagnostica LP DAAC ora descrive correttamente l’acquisizione on-demand, senza dichiarare una connessione live non verificata dal health endpoint.

## 9–15. Indicatori e risultati scientifici

Implementati cambiamento iniziale (prima osservazione, minimo e minima anomalia nei primi 90 giorni), anomalia stagionale, trend Theil–Sen su mediane mensili, sequenze negative persistenti, ritorno sostenuto alla fascia di riferimento e supporto osservativo separato per NDVI/EVI. Nessun recovery score arbitrario, nessun p-value IID, nessuna probabilità di recupero. [Formule, QA, soglie e limiti](RECOVERY_ASSESSMENT_METHODOLOGY.md).

Regole principali: riferimenti esclusivamente pre-evento, distanza stagionale circolare su calendario bisestile, almeno 3 compositi e 2 anni; anomalia = osservato−mediana stagionale. Fascia = mediana ± max(0,05; 1,4826×MAD), descrittiva e non intervallo di confidenza. Persistenza = almeno 3 punti consecutivi e 32 giorni, sotto la fascia e anomalia ≤−0,05; lacune o salti >32 giorni interrompono la sequenza. Ritorno sostenuto usa il medesimo supporto dentro la fascia, senza chiamarlo recupero ecologico completo.

### Dati NASA reali utilizzati

| Evento candidato | Intervallo FIRMS | Serie sorgente | NDVI/EVI validi | Celle MCD64A1 | Celle VI / sufficienti |
|---|---|---|---:|---:|---:|
| `event-4a728489ea44ea85eab6a978870e0b06` | 2021-08-11–2021-08-12 | 2019-08-11–2026-10-28 | 154 / 154 | 94 | 376 / 376 |
| `event-de3698dc41cec7c190a85fa55f460c46` | 2021-08-12–2021-08-13 | 2019-08-12–2022-02-28 | 55 / 55 | 5 | 20 / 20 |
| `event-d9b6a6bd767ce916648e712722e888c0` | 2026-10-02–2026-10-04 | 2023-10-02–2026-10-29 | 65 / 65 | 0 | 438 / 0 |

**Riferimento Sicilia.** Stessa pubblicazione sorgente Fase 4: 168 sorgenti, 154 osservazioni valide per indice, 94 celle bruciate, 20,177915 km². Ultimo NDVI 0,6358 e anomalia +0,054625; EVI 0,3821 e +0,06145. Fingerprint completo della pubblicazione conservato: `4c8c61e3c1a1227882fd6197ba0e54b537b6116123394b6ed251a8352d35597f`. Il catalogo descrive 13.308.448.615 byte di tile; la pubblicazione riporta 0 byte scientifici nell’ultimo retry e 3.292.870 nei tentativi precedenti. Il piano verifica 3.893.173.170 byte di sorgenti riusabili: quantità distinte, non traffico aggiuntivo.

Per il riferimento: prima anomalia NDVI −0,21565 ed EVI −0,1547 il 13 agosto 2021. Sono individuate 8 sequenze storiche negative NDVI e 4 EVI. Prima evidenza sostenuta nella fascia: NDVI 9 maggio 2023 (4 compositi, 48 giorni), EVI 17 novembre 2021 (4 compositi, 45 giorni); possono seguire nuove anomalie. Trend descrittivi sull’intero periodo sorgente: +0,033888/anno NDVI e +0,023713/anno EVI. Supporto post-evento: 112/120 compositi (93,33%), massimo intervallo fra validi 48 giorni. La classificazione finale è nella fascia per NDVI e sopra fascia per EVI: discordanza esplicitamente visibile.

**Secondo evento storico.** Selezione prima di esaminare gli indici: maggiore candidato di durata 1–2 giorni e almeno 50 rilevamenti nel settore siciliano considerato, escluso il riferimento (69 rilevamenti associati). Acquisizione circoscritta a 2019-08-12–2022-02-28, 61 sorgenti; nuovi file scientifici trasferiti: 392,577 byte. Cinque celle MCD64A1 e 20 celle VI. Ultime anomalie: NDVI −0,07015 ed EVI −0,0399 il 2 febbraio 2022. Una sequenza persistente storica per indice; la classificazione finale NDVI resta sotto il riferimento, EVI nella fascia. [Selezione, piano e sorgente](phase5-historical-comparison-source.json).

**Controllo di insufficienza.** Evento del 2–4 ottobre 2026: esistono osservazioni precedenti, ma nessuna osservazione post-evento valida nel cutoff. Tutte le 438 celle sono correttamente insufficienti per assessment post-incendio; nessuna data di ritorno/trend viene inventata. Il confronto con questo evento restituisce insufficient_data.

**Validazione numerica.** Fixture con valori attesi per anomalie positive/negative, consecutività/durata, ritorno sostenuto, oscillazioni, lacune, pochi punti, QA insufficiente, baseline insufficiente, outlier, discordanza NDVI/EVI, assenza post-evento, finestre selezionate e confronti non compatibili. Equivalenza scalare/vettoriale per conteggi, anni, baseline e fascia. Su 16 celle NASA deterministiche ×166 compositi: scalare 5.7453 s, vettoriale 0.8066 s, errore massimo baseline 0.0; stesso cubo e parametri, sola porzione di calcolo baseline. [Benchmark riproducibile](phase5-baseline-benchmark.json).

**Limiti scientifici.** Due candidati storici vicini nel tempo e nella stessa regione non validano trasferibilità globale, ecosistemi o cause. Il controllo recente è un test reale dell’insufficienza, non un terzo confronto conclusivo. Le prove di anni/stagioni differenti sono fixture controllate. Le soglie sono convenzioni operative documentate; nessuna validazione ecologica sul terreno, modello predittivo o ML supervisionato è rivendicata.

## 16–20. Spatial Intelligence

Quattro layer derivati dalle celle dei raster reali: anomalia stagionale per data, persistenza, trend e disponibilità. Baseline per pixel, mai mediana dell’evento assegnata a tutti. CRS sinusoidale, risoluzione reale 231,656358 m (nominale 250 m), offset e nodata verificati. Le mappe visualizzano le impronte native e condividono data/indice con Recovery Story. AOI e celle bruciate sono sovrapposte; basemap satellitare Esri con data non storicamente attribuita.

Connected components a quattro vicini, minimo 3 celle, area da impronte native. Sono riportati area, numero celle, anomalia mediana, persistenza e supporto. Nessun cluster attualmente persistente nei due casi storici con le soglie predefinite: non vengono creati cluster per rendere la mappa interessante. La fixture spaziale verifica invece cluster positivi, connettività, area e distinzione nodata.

GeoTIFF nativi multibanda: valore/baseline/anomalia per data più trend, completezza, durata e classe. Il riferimento ha 502 bande per indice; asset e risultati pubblicati sono protetti. Le API della mappa restituiscono soltanto piccoli layer di celle per la data selezionata, non enormi matrici raster JSON. [Dettagli spaziali](SPATIAL_RECOVERY_ANALYSIS.md), [evidenza reale](phase5-real-verification.json).

## 21–25. Confronto

Confronto dei due eventi storici, per NDVI ed EVI; allineamento = giorni dall’ultima rilevazione FIRMS /30,436875. L’anomalia usa la propria baseline stagionale. Intersezione comune delle osservazioni supportate: 0,5257–5,6839 mesi dall’incendio, durata 5,1582 mesi (`comparison-5.0.2`). Anche trend, persistenza, prima/ultima anomalia e supporto nelle schede sono ricalcolati su questo orizzonte, evitando il confronto di pendenze su durate diverse.

Esito **caution** per supporto limitato nella finestra condivisa; il riferimento completo ha cinque anni post-evento, il secondo circa sei mesi. I null non vengono interpolati, ogni evento conserva la propria geografia e non esiste ranking del “recupero migliore”. Differenze di versione/prodotto o assenza di dati producono insufficienza; parametri o supporti geografici diversi sono segnalati. Il controllo 2026 verifica l’esito insufficient_data. [Confronto persistito e ragioni](phase5-real-verification.json).

## 26–32. API, frontend, file, test e consegna

**API.** Preflight POST ora 202, GET/SSE stato/piano; POST assessment locale, GET stato/SSE/risultato/mappa/cella/insight/GeoTIFF; elenco assessment paginato; POST/GET confronto persistente; diagnostica cache amministrativa read-only. Contratti, parametri e errori sono descritti in [Recovery Intelligence](RECOVERY_INTELLIGENCE.md) e OpenAPI. Il cambio del contratto preflight è esplicito.

**Frontend.** Integrazione in EventAnalysisPage, RecoveryIntelligencePanel, RecoveryComparisonPanel nella ComparePage esistente e ResourceDiagnostics in Datasets. Conservati Explorer, Recovery Story, playback, grafici, Before/After e SSE. La mappa mantiene lo spazio e la basemap durante il caricamento di un nuovo indice/data, senza mostrare celle di una data precedente come attuali.

**File principali nuovi/modificati della Fase 5.** `analysis/recovery_assessment.py`, `analysis/recovery_comparison.py`, `services/spatial_recovery.py`, `services/recovery_jobs.py`, `services/planning_jobs.py`, `services/planning_metrics.py`, `services/catalog_cache.py`, `services/cache_management.py`, estensioni a satellite_cache/acquisition_plan/post_fire_pipeline/analysis_jobs/analysis_progress/analysis_worker, modelli satellitari e route event_analysis/recovery_intelligence/health; configurazione, Compose e .env.example; componenti/API/tipi frontend citati, nginx.conf e Dockerfile; test Fase 5 e adattamento del contratto del test Fase 4; verificatori `verify_phase5_*`, `benchmark_phase5_*`, `prepare_phase5_comparison_event.py`, CLI cache e supporto prefisso della verifica browser Fase 4. Il diff Git complessivo contiene anche fasi precedenti, quindi non viene attribuito interamente alla Fase 5.

**Test backend finali.** **89 test superati su SQLite e 89 su PostgreSQL/PostGIS**, senza fallimenti; rispettivamente 34,23 s e 41,63 s. Consultare [SQLite container](phase5-tests-container-sqlite.log) e [PostgreSQL/PostGIS](phase5-tests-postgres.log) per gli output completi. Build Docker backend/worker/frontend riuscito; anche la successiva rifinitura delle etichette del grafico è compilata e verificata nel browser. Database dedicato `afterfire_test_phase5`; guardia che rifiuta database non-test. Le prove HDF native sono eseguite con Python 3.12 del container.

**Browser.** [Evidenza Fase 5](phase5-ui-verification.json): Explorer → evento, dati pluriennali, celle caricate, click cella, quattro layer, NDVI/EVI, data sincronizzata, preflight/reload, selezione 2022-01-01–2023-12-31 e ripristino esplicito dell’assessment completo dalla cache, confronto/reload, desktop/mobile, nessun pageerror e tile satellitari effettivamente caricate. [Regressione Recovery Story/Before-After/playback](phase5-story-ui-verification.json). Screenshot: [Intelligence desktop](phase5-intelligence-desktop.png), [mobile](phase5-intelligence-mobile.png), [Compare](phase5-comparison-desktop.png). La compilazione da sola non è considerata una prova browser.

**Persistenza e archivio.** [Fingerprint prima/dopo ricreazione](phase5-persistence-verification.json) per pubblicazioni sorgente, assessment, mappe, GeoTIFF e confronti. Conteggio atteso invariato: 803.761 rilevamenti totali, 802.234 marcati Italia. Verificatore finale: **equal=true**, dopo ricreazione di backend, worker e frontend con mantenimento dei volumi. Sorgenti, assessment, mappe, GeoTIFF e confronti sono invariati.

**Tentativi falliti risolti / limiti di ambiente.** In sviluppo sono stati corretti shadowing di una variabile di misura CMR, isolamento dei job di fixture, fixture con date incoerenti e attese browser premature. L’ultima ripetizione ha individuato un difetto del layer di contorno delle zone persistenti: intercettava i click sulle celle. Il layer è ora non interattivo; il test porta la mappa al centro, usa click ordinari e verifica la selezione anche nella finestra con zone persistenti. L’intervallo assessment è sempre visibile, anche dopo reload. Il plugin browser non aveva il proprio Chrome; le prove usano Chromium di sistema tramite Playwright già installato. La precedente venv host Python 3.15 mancava di pyhdf e due prove HDF fallivano lì; dopo il ripristino del disco DATA il suo eseguibile restituisce inoltre Exec format error. La verifica canonica usa Python 3.12 nel container e include entrambe le prove HDF nella suite completa. Il mount read-only iniziale senza scripts impediva la raccolta di un test esistente; il comando riproducibile monta anche scripts. Questi tentativi non vengono conteggiati come superati.

**Problemi/limiti ancora aperti.** Bundle principale misurato 1.015,40 kB minificati / 289,56 kB gzip, contro circa 996 kB documentati prima (incremento indicativo circa 19 kB, 1,9%; non è una compilazione A/B isolata). Valutato il code splitting: resta aperto per il routing condiviso, senza caricare raster pluriennali nel browser. Permane il warning Vite, deprecazioni delle dipendenze, nessun monitoraggio delle prestazioni sotto carico massivo. Il cleanup è conservativo: non elimina temporanei orfani o asset pubblicati senza una gestione esplicita dei riferimenti; se i file protetti occupano la quota, il job fallisce in modo controllato. Il primo hash dopo cambiamento/scadenza resta costoso. Non è validata una rete di ecosistemi/anni/stagioni reali diversi, né il valore ecologico delle soglie. Sono limiti dichiarati, non risultati inventati.

**Sintesi delle evidenze.** [Esiti finali in JSON](phase5-test-results.json). Dati NASA: due eventi storici e controllo recente, mappe native e confronto. Fixture: soglie numeriche, cluster positivi, stagioni/anni differenti, concorrenza e cleanup distruttivo su volume temporaneo. Non validati: generalizzazione ecologica, accuratezza sul terreno e comportamento sotto carico massivo.

**Documenti.** Creati RECOVERY_INTELLIGENCE, RECOVERY_ASSESSMENT_METHODOLOGY, SPATIAL_RECOVERY_ANALYSIS, ASYNC_PREFLIGHT, CACHE_MANAGEMENT e questo rapporto. Aggiornati README, SCIENTIFIC_METHODOLOGY, POST_FIRE_RECOVERY, SATELLITE_DATA_PIPELINE, ANALYSIS_CACHE, RECOVERY_STORY e SATELLITE_SUBSETTING con collegamenti e cambi del contratto, lasciando i rapporti precedenti come evidenze storiche.

## Riproduzione

```bash
# Nessun reset dell’archivio; i fixture usano database temporanei/dedicati.
docker compose run --rm --no-deps -v "$PWD/scripts:/scripts:ro" -v "$PWD/backend:/app:ro" backend python -m pytest app/tests -q --disable-warnings -p no:cacheprovider
# Per PostGIS usare il database dedicato già creato afterfire_test_phase5.
docker compose run --rm --no-deps -e AF_TEST_DATABASE_URL=postgresql+asyncpg://afterfire:afterfire@db:5432/afterfire_test_phase5 -v "$PWD/scripts:/scripts:ro" -v "$PWD/backend:/app:ro" backend python -m pytest app/tests -q --disable-warnings -p no:cacheprovider
python3 scripts/verify_phase5_real.py
VERIFY_ASSESSMENT_WINDOW=1 node scripts/verify_phase5_browser.mjs
docker compose run --rm --no-deps -e PYTHONPATH=/app -v "$PWD/scripts:/scripts:ro" -v "$PWD/docs:/app/docs" backend python /scripts/verify_phase5_cache.py
```

Le prove `verify_phase5_real.py` richiedono i tre job reali documentati e accodano solo assessment locali, senza nuovi download; il preflight è read-only. `prepare_phase5_comparison_event.py` avvia invece esplicitamente un’acquisizione limitata dopo un piano fattibile. Il verificatore persistenza ha modalità capture/verify da eseguire prima/dopo la ricreazione. I benchmark baseline/planning leggono le sorgenti esistenti dentro il container. Per la regressione Story impostare PLAYWRIGHT_MODULE al modulo installato e VERIFICATION_PREFIX=phase5-story, così non si sovrascrivono le evidenze Fase 4.
