# AfterFire — resoconto implementazione e verifica

Verificato il 28 ottobre 2026 sull'applicazione Docker esistente: frontend
http://localhost:3000/explorer, FastAPI e PostgreSQL/PostGIS. Il repository aveva
modifiche non committate: sono state preservate. Non sono stati creati commit.

## Risultato funzionale

La mappa apre tutta l'Italia, Sicilia e Sardegna comprese, con contesto mediterraneo.
Pan e zoom restano globali. Il cerchio è opzionale e può essere disegnato con due
clic, modificato numericamente e cancellato; “Return to Italy” lo elimina e conserva
periodo e sensore. Il filtro geografico usa la distanza geodetica PostGIS e non il
solo rettangolo circoscritto. La ricerca non avvia acquisizioni globali.

Gli aggregati visuali sono calcolati in SQL per celle Mercator/zoom e sensore,
sull'intero insieme filtrato, senza il precedente limite di 50.000 osservazioni.
Nella verifica della vista italiana: **31 aggregati, 802.234 osservazioni**.
Date, sensori e cerchio aggiornano query, conteggi e lista; un intervallo vuoto
rimuove i marker precedenti. Le zone prive di dati locali ricevono uno stato di
copertura esplicito, senza dedurre assenza di incendi.

La lista usa paginazione server e un indice persistente di **46.629 candidati reali
italiani**. Il raggruppamento scientifico è greedy per prossimità, 7 km e massimo
3 giorni di separazione, minimo 3 osservazioni; non è DBSCAN né un inventario
ufficiale. Gli ID dipendono dalla membership completa e rimangono stabili attraverso
i filtri. Se cambia la membership dopo un'importazione, può cambiare il candidato;
i vecchi record restano raggiungibili. L'indice corrente viene sostituito solo dopo
la persistenza dei nuovi gruppi. Gli aggregati della mappa non sono candidati.

La selezione evidenzia il candidato e apre l'URL analitico, valido anche dopo refresh.
La timeline usa il contesto prima/durante/dopo e non il filtro generale della mappa.
Recupero e ricorrenza restano non disponibili se mancano osservazioni adeguate;
non vengono costruiti NDVI, superfici bruciate o perimetri fittizi. La confidence
categorica VIIRS è mantenuta nella scala nativa, senza percentuali inventate.

## Acquisizione NASA realmente eseguita

Fonte annuale ufficiale: [indice FIRMS dei file per paese](https://firms.modaps.eosdis.nasa.gov/data/country/yearly_summary_files.txt).
Sono stati acquisiti i 48 file annuali italiani disponibili: MODIS 2000–2025,
Suomi-NPP 2012–2025, NOAA-20 2018–2025. L'API FIRMS, con la chiave già configurata,
ha coperto 451 finestre aggiuntive secondo la disponibilità dichiarata: prodotti SP
e poi NRT non sovrapposti, incluse le osservazioni NOAA-21 dal 2023-03-01 e il 2026.
Le richieste API usano finestre di massimo 5 giorni. Le credenziali non sono nei
report o nelle ricevute. Le versioni originali dei file annuali MODIS sono conservate;
non sono state reinterpretate come una collezione scientifica non verificata.

| Misura | Risultato |
|---|---:|
| Nuove osservazioni italiane persistite | 801.642 |
| Osservazioni italiane reali finali | 802.234 |
| Osservazioni reali italiane preesistenti conservate | 592 |
| Totale righe lette nei checkpoint unici | 882.919 |
| Righe fuori dal confine italiano escluse | 80.879 |
| Duplicati esatti riconosciuti | 398 |
| Righe non valide | 0 |
| Dati demo italiani inclusi nei risultati reali | 0 |
| Record demo preesistenti conservati nel database | 1.522 |

Periodo effettivamente osservato: **2000-11-02 → 2026-10-27**. Ultimo aggiornamento
d'importazione: **2026-10-28 10:31:00 UTC**, ore **11:31:00 Europe/Rome**.
I cinque record reali preesistenti fuori Italia sono conservati; l'importazione
nuova è filtrata sul poligono italiano Natural Earth 5.1.2, isole comprese.

| Prodotto/dataset effettivamente presente | Osservazioni italiane | Date osservate |
|---|---:|---|
| `FIRMS_MODIS_ANNUAL` | 131,700 | 2000-11-02 → 2025-12-30 |
| `FIRMS_MODIS_C61` | 5,338 | 2026-01-05 → 2026-10-27 |
| `FIRMS_MODIS_NRT` | 53 | 2026-08-02 → 2026-10-21 |
| `FIRMS_VIIRS_NOAA20_375M` | 212,004 | 2018-04-01 → 2026-10-27 |
| `FIRMS_VIIRS_NOAA21_375M` | 86,998 | 2023-03-01 → 2026-10-27 |
| `FIRMS_VIIRS_SNPP_375M` | 365,602 | 2012-01-20 → 2026-10-27 |
| `FIRMS_VIIRS_SNPP_NRT` | 539 | 2026-07-03 → 2026-10-27 |

Le due sorgenti legacy NRT restano intatte. Sono state eliminate solo 398 nuove
copie identiche agli originali, previa verifica degli attributi scientifici,
versione, satellite e assenza di riferimenti pubblicati, con backup completo.
Revisioni/versioni differenti sono conservate. Il job è ripetibile per hash e
checkpoint: **499 input già completi al secondo passaggio**, senza nuovi inserimenti.
Gli input corrispondono a 498 checkpoint unici perché due finestre MODIS avevano
contenuto identico. Le ricevute mantengono provenienza, hash, contatori e date.

Questi risultati attestano i file e le finestre acquisiti. **La completezza
indipendente dell'intero archivio NASA rimane `not_assessed`**; le date min/max
non dimostrano continuità o completezza delle rilevazioni.

## Verifiche eseguite

- **30 test backend SQLite superati**, con database temporaneo isolato.
- **Gli stessi 30 test PostgreSQL/PostGIS superati**, in un database di test dedicato;
  il reset dei test non può usare il database dell'archivio.
- Build TypeScript/Vite e immagini Docker backend/frontend riuscite. Rimane
  l'avviso Vite sul bundle JavaScript principale superiore a 500 kB.
- API reali verificate: somma aggregati, sensori/date, cerchio, copertura parziale,
  area internazionale vuota, paginazione e storia completa di un ID stabile.
  Evidenza: [snapshot API](explorer-api-verification.json), verificato 2026-10-28T11:40:41.410899+00:00.
- **Suite UI CUA superata**, 7 gruppi di verifiche: vista iniziale,
  date vuote, cerchio e marker, estero/ritorno, lista e scheda, timeline, dati
  mancanti e distinzione demo. A 390×844 px: mappa 350×546.6 px,
  documento 384 px; nessun overflow orizzontale.
  Evidenza: [risultati UI](explorer-ui-verification.json) e [screenshot](afterfire-explorer.jpg).
- Rerun reale dell'importatore concluso con exit 0 e 499 input già completi.
- Controlli Python compileall e `git diff --check` superati.

Le fixture dei test spaziali sono sintetiche e isolate. I conteggi sopra provengono
invece dalle API del PostgreSQL popolato con NASA FIRMS. La suite UI è riproducibile
con `scripts/verify_explorer_ui.mjs` in una sessione CUA; non richiede nuove dipendenze.
L'audit dettagliato e la procedura sono in [EXPLORER_VERIFICATION.md](EXPLORER_VERIFICATION.md).

## Limiti ancora presenti

FIRMS rileva anomalie termiche: un hotspot o un gruppo non conferma un incendio
boschivo. I candidati non sono perimetri ufficiali. Il confine cartografico ha
incertezza costiera. I nuovi candidati globali non hanno serie reali MOD13Q1 o
MCD64A1 assegnate: la scheda lo dichiara e non produce recupero quantitativo.
Gli adattatori vegetazionali non sono stati verificati come downloader regionali
live. Dove esistono serie valide, il baseline è una media pre-evento, non una
correzione stagionale; NDVI non dimostra recupero ecologico.

## File e componenti interessati

Il seguente inventario descrive lo stato finale non committato, incluse modifiche
preesistenti completate o mantenute; non attribuisce all'intervento ogni riga della
diff. Dati scaricati e backup sono esclusi da Git e dall'immagine Docker.

- `.env.example`
- `.gitignore`
- `README.md`
- `backend/.dockerignore`
- `backend/README.md`
- `backend/app/analysis/harmonization.py`
- `backend/app/analysis/recovery_engine.py`
- `backend/app/analysis/recurrence_engine.py`
- `backend/app/api/routes/analysis.py`
- `backend/app/api/routes/areas.py`
- `backend/app/api/routes/burned_area.py`
- `backend/app/api/routes/comparison.py`
- `backend/app/api/routes/datasets.py`
- `backend/app/api/routes/detections.py`
- `backend/app/api/routes/events.py`
- `backend/app/api/routes/explorer.py`
- `backend/app/api/routes/health.py`
- `backend/app/api/routes/italy.py`
- `backend/app/api/routes/reports.py`
- `backend/app/api/routes/vegetation.py`
- `backend/app/core/config.py`
- `backend/app/db/database.py`
- `backend/app/jobs/seed_data.py`
- `backend/app/main.py`
- `backend/app/models/__init__.py`
- `backend/app/models/dataset.py`
- `backend/app/models/event.py`
- `backend/app/models/fire.py`
- `backend/app/models/import_metadata.py`
- `backend/app/providers/firms.py`
- `backend/app/schemas/burned_area.py`
- `backend/app/schemas/events.py`
- `backend/app/schemas/explorer.py`
- `backend/app/schemas/fire.py`
- `backend/app/services/explorer_query.py`
- `backend/app/services/italy_coverage.py`
- `backend/app/tests/conftest.py`
- `backend/app/tests/test_api_endpoints.py`
- `backend/app/tests/test_italy_coverage_explorer.py`
- `backend/app/tests/test_scientific_engine.py`
- `backend/data/natural_earth_5_1_2_italy.geojson`
- `compose.yaml`
- `docs/EXPLORER_VERIFICATION.md`
- `docs/SCIENTIFIC_METHODOLOGY.md`
- `docs/explorer-api-verification.json`
- `docs/explorer-ui-verification.json`
- `frontend/.dockerignore`
- `frontend/src/api/client.ts`
- `frontend/src/app/App.tsx`
- `frontend/src/components/charts/RecoveryChart.tsx`
- `frontend/src/components/common/DemoBanner.tsx`
- `frontend/src/components/layout/Navbar.tsx`
- `frontend/src/components/map/LeafletMap.tsx`
- `frontend/src/components/timeline/TimelineBar.tsx`
- `frontend/src/pages/ComparePage.tsx`
- `frontend/src/pages/DatasetsPage.tsx`
- `frontend/src/pages/EventAnalysisPage.tsx`
- `frontend/src/pages/ExplorerPage.tsx`
- `frontend/src/pages/RecoveryPage.tsx`
- `frontend/src/pages/RecurrencePage.tsx`
- `frontend/src/pages/TerritoryPage.tsx`
- `frontend/src/styles/index.css`
- `frontend/src/types/index.ts`
- `frontend/vite.config.ts`
- `scripts/import_firms_archive.py`
- `scripts/import_italy_fire_history.py`
- `scripts/index_fire_events.py`
- `scripts/verify_explorer_api.py`
- `scripts/verify_explorer_ui.mjs`

I percorsi principali sono `ExplorerPage.tsx`, `LeafletMap.tsx`,
`EventAnalysisPage.tsx`, `api/routes/explorer.py`, `services/explorer_query.py`,
`services/italy_coverage.py` e i tre script di importazione/indicizzazione.
I comandi operativi sono documentati in `backend/README.md`.
