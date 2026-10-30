# AfterFire — verifica e consegna Fase 4

Verifica su dati NASA reali del 28–29 ottobre 2026. Il codice è integrato nella pagina evento esistente. Non sono stati introdotti dati scientifici dimostrativi, né eliminati database o record FIRMS. Il repository conteneva già modifiche e file della Fase 3: sono stati conservati.

## 1. Causa e correzione del limite

La pipeline precedente sommava `expected_bytes` dei granuli CMR completi prima di controllare la cache e confrontava questa somma con `AFTERFIRE_ANALYSIS_MAX_JOB_GB=5`. Anche sorgenti già presenti erano quindi conteggiate come nuovi download; il successivo controllo del consumo comprendeva anch'esso sorgenti riutilizzate. Per una piccola AOI, il catalogo descriveva tile regionali intere, non i byte necessari al territorio. Il test controllato di 70 sorgenti da 100 MiB già in cache riproduce il rifiuto precedente pur richiedendo zero byte di rete.

Il limite resta **5.368.709.120 byte (5 GiB)**. Ora limita i byte scientifici nuovi effettivamente trasferiti, inclusi trasferimenti falliti e tentativi precedenti dello stesso job. Volume del catalogo, cache riutilizzata, nuovi trasferimenti e risultati derivati sono distinti. Non viene ridotto automaticamente l'intervallo richiesto.

Il preflight reale precedente alla nuova acquisizione, salvato in [phase4-real-plan.json](phase4-real-plan.json), comprendeva 168 sorgenti e **13.308.448.615 byte** di tile complete, oltre il limite. Con 51 sorgenti già disponibili (**3.890.398.220 byte**), la strategia cache → subset nativo è risultata fattibile; la dimensione remota è stata lasciata sconosciuta fino alla disponibilità dei bundle NASA.

## 2. Acquisizione, provider e limiti

AppEEARS è implementato e verificato tramite API ufficiale. Le risposte prodotto effettive sono conservate in [MOD13Q1.061](phase4-appeears-MOD13Q1.061.json) e [MCD64A1.061](phase4-appeears-MCD64A1.061.json). I layer obbligatori sono validati dinamicamente prima della prima richiesta:

| Prodotto | Layer richiesti |
| --- | --- |
| MOD13Q1.061 | `_250m_16_days_NDVI`, `_250m_16_days_EVI`, `_250m_16_days_VI_Quality`, `_250m_16_days_pixel_reliability` |
| MCD64A1.061 | `Burn_Date`, `Burn_Date_Uncertainty`, `QA`, `First_Day`, `Last_Day` |

L'autenticazione AppEEARS usa username/password Earthdata sul backend e un proprio token effimero. Il token del downloader HDF non viene riutilizzato. Il frontend non riceve credenziali. Gli output vengono scaricati da destinazioni HTTPS NASA/S3/CloudFront validate.

Le richieste sono annuali, limitate alle bande necessarie e alla piccola geometria provvisoria dell'analisi: **84,5533 km²**, con un margine nativo di 500 m per includere interamente le celle sul bordo. Le statistiche usano invece la geometria scientifica finale delle celle bruciate (**20,1779152898568 km²**). CRS sinusoidale nativo, dimensioni del pixel, trasformazione affine, quantizzazione, fill e classi QA sono controllati. Non si interpolano classi o valori scientifici.

Manifest con chiave deterministica, task ID e SHA-256 consentono ripresa e riuso offline degli output completi. La ricerca del nome deterministico sul server copre anche l'interruzione tra POST NASA e salvataggio locale. I checkpoint delle finestre elaborate dipendono da revisione della sorgente, geometria e versione scientifica, non dalla data finale richiesta. La baseline viene ricalcolata sull'insieme completo delle osservazioni precedenti.

| Risorsa | Limite predefinito |
| --- | ---: |
| Nuovi trasferimenti per richiesta | 5 GiB |
| Singolo blocco nuovo | 1 GiB |
| File temporanei | 1 GiB |
| Risultati derivati | 2 GiB |
| Cache complessiva | 10 GiB |
| Riserva spazio libero | 1 GiB |
| Concorrenza download configurata | 2 |

Il provider HDF originale resta disponibile, con fallback solo entro i limiti. L'indisponibilità del subset non autorizza un download illimitato. I file `.part` vengono rimossi su errore; sorgenti complete e checkpoint restano disponibili. Non è stata attivata un'evizione indiscriminata dei risultati.

## 3. Misure reali confrontabili

| Verifica | Sorgenti complete | Subset scientifici |
| --- | ---: | ---: |
| Stesse tre date MOD13Q1 del 2021 e stesso mese MCD64A1 | **251.010.527 byte** di HDF verificati su disco | **61.104 byte** delle stesse bande/date/celle |
| Richiesta pluriennale 2019–2026 | **13.308.448.615 byte** dichiarati dal catalogo per tutte le tile | **3.292.870 byte** effettivamente trasferiti nella prima esecuzione, oltre alla cache esistente |
| Ripetizione della stessa richiesta | 168 sorgenti disponibili in cache | **0 byte** scientifici nuovi |

Il primo confronto riduce i byte dei file scientifici del **99,9757%**. Per il secondo, la cache iniziale copriva già 3.890.398.220 byte; i restanti 9.418.050.395 byte di tile catalogate non sono stati scaricati integralmente. I 3.292.870 byte sono il conteggio effettivo del trasferimento dei TIFF, non una stima ottenuta dal rapporto delle aree. Escludono risposte JSON di controllo, overhead HTTP/TLS e la prova di equivalenza separata. I bundle annuali possono contenere compositi aggiuntivi ai bordi: questi non entrano automaticamente nella serie richiesta.

La prova indipendente di acquisizione ha trasferito 77.597 byte in totale: 65.734 per quattro compositi VI restituiti dal servizio e 11.863 per burned area. Il confronto puntuale sopra usa solo le tre date VI presenti in entrambe le sorgenti, quindi 61.104 byte. Evidenza: [phase4-subset-transfer.json](phase4-subset-transfer.json), [phase4-equivalence.json](phase4-equivalence.json).

## 4. Serie pluriennale e regressione scientifica

Evento: `event-4a728489ea44ea85eab6a978870e0b06`, Sicilia, 11–12 agosto 2021, 262 rilevamenti FIRMS associati. Configurazione: 2 anni precedenti, massimo 10 successivi, cutoff esplicito **2026-10-28**, buffer 1.000 m, acquisizione automatica. Periodo richiesto e conservato: **2019-08-11–2026-10-28**.

Job verificato: `2abc3a98d03cd3f51f4c4491f555813afb97fe474ee6b21b590cb0e56eee90b3`.

| Risultato | Valore verificato |
| --- | ---: |
| Sorgenti elaborate | 168: 51 HDF in cache + 117 record da subset |
| Compositi attesi | 166, ciascuno con NDVI ed EVI: 332 righe |
| Osservazioni NDVI valide | **154** |
| Osservazioni EVI valide | **154** |
| Righe escluse per QA/copertura | 22, cioè 11 compositi per entrambi gli indici |
| Righe del periodo ancora incompleto | 2, composito del 16 ottobre 2026 |
| Ultimo composito valido | **30 settembre–15 ottobre 2026** |
| Celle bruciate confermate dall'algoritmo | **94**, nessuna cella ambigua |
| Superficie delle celle | **20,1779152898568 km²** |
| Errori di acquisizione dopo retry | **0** |
| Byte nuovi nel retry | **0** |
| Volume delle sorgenti riutilizzate nel retry | **3.893.173.170 byte** |
| Tempo del retry misurato dal job | **88,61 s** (ultimo retry dal browser; primo retry 84,74 s) |

Lo stato resta `partial` perché le osservazioni escluse o incomplete sono mantenute come lacune esplicite. Non indica più una sorgente fallita. Nel primo risultato mancava il composito del 1 gennaio 2023 per un `ConnectError`; il retry lo ha recuperato dai file completi già in cache. Evidenze prima/dopo: [primo risultato](phase4-first-published-result.json), [preflight cache](phase4-cache-replay-plan.json), [verifica finale](phase4-real-verification.json).

Ultimo NDVI: 0,6358; anomalia stagionale +0,054625; stato operativo «near baseline». Ultimo EVI: 0,3821; anomalia +0,06145; stato «above baseline». Questi stati degli indici non dimostrano recupero ecologico completo.

**Equivalenza indipendente HDF/GeoTIFF:** tutte le bande necessarie, QA e coordinate delle celle selezionate coincidono esattamente su tre compositi VI e un mese burned area. Per VI sono 376 celle native per data; per burned area 94 celle. Sul composito del 29 agosto 2021: 364/376 pixel validi, mediana NDVI 0,2521 ed EVI 0,1285 in entrambe le pipeline. Tolleranza delle statistiche: zero; offset griglia: 1e-5 pixel; area per cella: 1e-9 km² per precisione della trasformazione affine. Gli inviluppi raster possono differire per righe/colonne vuote sul bordo; il confronto è sulle stesse coordinate native selezionate, non sugli indici di una matrice con diverso inviluppo.

**Regressione sul risultato Fase 3:** 96 righe del periodo precedente confrontate per valore, pixel validi/totali, baseline e anomalia: identiche entro 1e-12; restano le stesse 94 celle bruciate. La verifica comprende anche le righe esplicitamente mancanti, non soltanto quelle valide.

## 5. Persistenza e ripresa

Sei task annuali NASA sono stati salvati, ripresi dopo il riavvio del worker e riutilizzati nel retry. Gli ID sono elencati nel JSON finale. Il risultato è rimasto accessibile dopo il riavvio della macchina e la ricreazione dei container sui volumi persistenti. La ripetizione ha mantenuto gli stessi sei task ID senza nuovi trasferimenti. Le osservazioni sono pubblicate atomicamente con identità job/data/indice, evitando duplicati.

Le prove SQLite e PostGIS usano database dedicati; il fixture rifiuta nomi PostgreSQL che non iniziano con `afterfire_test_`. Non viene resettato il database dell'archivio. Durante la verifica era presente anche un altro job attivo: è stato lasciato al proprio worker; il worker temporaneo usato per il retry è stato fermato al termine.

## 6. Recovery Story e verifica browser

La pagina evento comprende configurazione e preflight, stessa telemetria SSE persistente, selettori anno/data, slider, navigazione precedente/successiva, riferimenti all'incendio, mappa datata, dettagli scientifici, confronto A/B e grafico sincronizzato. Un solo `selectedDate` governa timeline, mappa e grafico. Le immagini vengono caricate su richiesta e il prefetch è limitato al prossimo composito.

Il confronto utilizza una sola mappa Leaflet e due pane con clipping complementare: centro, zoom e proiezione sono comuni. Entrambi i lati sono tagliati, così i nodata di B non mostrano pixel di A. Date A/B, statistiche, copertura, scala fissa e differenza delle mediane sono esplicite. La posizione del divisore non modifica la geografia. Le date non hanno necessariamente lo stesso inviluppo raster: questo non implica disallineamento delle celle native.

Il playback usa soltanto osservazioni valide, aspetta il caricamento del frame, offre 4/2/0,8 secondi, si ferma alla fine e può essere messo in pausa. Le date senza pixel validi mostrano uno stato esplicito senza conservare la vecchia immagine. Gli altri raster mantengono trasparenza sui pixel esclusi; null non diventa zero.

La verifica Chromium automatizzata controlla pixel PNG effettivamente caricati, tile Esri World Imagery, cambio data e indice, un'unica mappa nel confronto, clipping e coordinate stabili spostando il divisore, click sul grafico, playback, stato mancante, ricarica e viewport mobile 390×844 senza overflow orizzontale. Il browser integrato non era disponibile nell'ultima sessione, quindi il controllo finale usa Chromium locale con Playwright installato. Gli screenshot mostrano dati NASA reali, non mock. Script: `scripts/verify_phase4_browser.mjs`; evidenza: [phase4-ui-verification.json](phase4-ui-verification.json).

![Confronto reale desktop](phase4-before-after-desktop.png)

![Confronto reale mobile](phase4-before-after-mobile.png)

## 7. Test e riproducibilità

- Evidenza riepilogativa: [phase4-test-results.json](phase4-test-results.json).
- Suite backend completa: **63 test passati su SQLite**, **63 su PostgreSQL/PostGIS** nel database dedicato `afterfire_test_phase4`.
- Frontend: `npm run build` e build Docker superate. Rimane l'avviso Vite sul bundle principale di circa 996 kB minificati (284 kB gzip); nessun errore TypeScript.
- Test aggiunti: cache oltre il vecchio limite, cache di sorgente singola oltre il limite blocco, piano subset con dimensione sconosciuta, identità task/geometria/bande, ripresa senza POST duplicato, redirect/download/checksum/corruzione, GeoTIFF nativo e griglia spostata, fill/scale/QA, checkpoint, preflight senza enqueue, autenticazione rifiutata, provider 503, task fallito, budget rete e quota cache con pulizia dei temporanei.
- Prove reali separate: catalogo, task NASA, confronto scientifico indipendente, estensione della serie, riavvio, recupero del blocco e replay senza rete.
- Rimangono warning di deprecazione delle dipendenze NumPy/affine e del loop fixture pytest-asyncio; non sono fallimenti scientifici.

Replay della verifica numerica, con un risultato Fase 3 salvato come riferimento:

```bash
backend/.venv/bin/python scripts/verify_phase4_real.py \
  --event event-4a728489ea44ea85eab6a978870e0b06 \
  --job 2abc3a98d03cd3f51f4c4491f555813afb97fe474ee6b21b590cb0e56eee90b3 \
  --reference /tmp/phase4-reference.json \
  --output docs/phase4-real-verification.json
```

Per equivalenza HDF utilizzare Python del container, che include pyhdf, con `scripts/verify_phase4_equivalence.py --help`. Per il browser impostare `PLAYWRIGHT_MODULE` al modulo Playwright installato, ed eventualmente `CHROMIUM_PATH`, quindi eseguire `node scripts/verify_phase4_browser.mjs`. Aggiungere `REPLAY_ANALYSIS=1` per includere preflight e retry esplicito della stessa richiesta dal browser. I verificatori scientifici leggono risultati reali. Il verificatore browser, con `REPLAY_ANALYSIS=1`, esegue esplicitamente il retry della stessa richiesta dopo il preflight e verifica il riuso dei dati; non genera fixture o osservazioni sintetiche.

## 8. File interessati dalla Fase 4

| Ambito | File principali |
| --- | --- |
| Provider e adapter | `backend/app/providers/appeears.py`, `backend/app/analysis/appeears_science.py`, dispatch in `modis_science.py` |
| Piano e incrementalità | `backend/app/services/acquisition_plan.py`, `vegetation_checkpoint.py`, `post_fire_pipeline.py`, `satellite_cache.py`, `satellite_rasters.py` |
| API, job, configurazione | `api/routes/event_analysis.py`, `services/analysis_jobs.py`, `services/analysis_progress.py`, `schemas/satellite_analysis.py`, `core/config.py`, `compose.yaml`, `.env.example` |
| UI | `frontend/src/pages/EventAnalysisPage.tsx`, `components/map/EventSatelliteMap.tsx`, `components/charts/RecoveryChart.tsx`, `api/satellite.ts`, `types/satellite.ts`; riuso di `SatelliteBasemap.tsx` |
| Test | `backend/app/tests/test_phase4_acquisition.py`, fixture isolati in `conftest.py` e correzione dell'isolamento del job nel test HTTP di `test_post_fire_recovery.py` |
| Verificatori | `scripts/verify_phase4_equivalence.py`, `verify_phase4_real.py`, `verify_phase4_ui.mjs`, `verify_phase4_browser.mjs` |
| Documentazione | `README.md`, `docs/POST_FIRE_RECOVERY.md`, `SATELLITE_DATA_PIPELINE.md`, `SCIENTIFIC_METHODOLOGY.md`, `ANALYSIS_CACHE.md`, `RECOVERY_STORY.md`, `SATELLITE_SUBSETTING.md`, questo rapporto e le evidenze `phase4-*` |

## 9. Limiti e problemi aperti

- La verifica reale copre un evento sufficientemente rappresentativo e i due prodotti richiesti. Non è una validazione globale di ogni tile, collezione o tipo di incendio. Le AOI grandi vengono protette dai limiti; non è stata eseguita un'acquisizione reale deliberatamente sovraquota.
- La cache deduplica richieste identiche e HDF condivisi. Non ricerca automaticamente subset con geometrie diverse ma parzialmente sovrapposte. Una modifica dell'ultimo anno incompleto può richiedere un nuovo task annuale; le finestre scientifiche già elaborate restano riutilizzabili.
- Il preflight deve ricontattare CMR: la disponibilità e la latenza NASA possono richiedere un nuovo tentativo. Due anteprime dal browser hanno risposto HTTP 200; una ripetizione successiva ha superato i 120 secondi del verificatore ed è stata chiusa dal client (HTTP 499 nel proxy). Non è un errore di quota e non viene conteggiata come controllo superato. Il retry avviato dopo il precedente piano valido è stato pubblicato correttamente.
- Un task NASA terminalmente fallito viene conservato e segnalato, senza un ciclo automatico di nuove submission. Timeout e problemi di rete riprendono il task salvato. Credenziali valide e autorizzazione Earthdata rimangono necessarie.
- La cache completa dei subset e degli asset non viene eliminata automaticamente; una quota esaurita richiede gestione esplicita. Gli HDF conservano la policy di evizione già presente.
- Le immagini storiche sono layer scientifici NDVI/EVI, chiaramente etichettati. Non è stato aggiunto un mosaico storico RGB GIBS: la basemap Esri ha date variabili e non viene presentata come fotografia del giorno selezionato.
- Non è implementata una mappa di differenza pixelwise; B−A è la differenza delle mediane. QA e stagionalità possono cambiare i pixel confrontabili.
- QA rigoroso e latenza del catalogo lasciano lacune: l'ultimo composito valido termina il 15 ottobre, pur mantenendo il cutoff richiesto al 28 ottobre. Non sono prodotti frame interpolati.
- MODIS ha pixel misti da 250/500 m, i compositi non indicano l'istante esatto di ogni pixel e il gruppo FIRMS non è un perimetro ufficiale. «Near baseline» non equivale a ecosistema completamente recuperato.
- La prima acquisizione NASA pluriennale è stata avviata tramite API/worker. Dal browser è stato verificato il percorso Explorer → evento → preflight → retry della stessa richiesta, concluso senza nuovi trasferimenti; la pubblicazione è stata controllata anche tramite API. La successiva verifica dei controlli visuali riutilizza quel risultato persistito.
