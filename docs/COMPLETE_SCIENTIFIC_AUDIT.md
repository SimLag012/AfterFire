# AfterFire — complete scientific engine audit

## Verifica del 13 novembre 2026

Abbiamo verificato 59 candidati distinti. Per i 56 candidati FIRMS MODIS dei manifesti congelati abbiamo riletto le pubblicazioni per ID di job, confrontato integralmente il JSON e rieseguito i calcoli su raster e serie conservati. Per tre nuovi candidati FIRMS VIIRS S-NPP abbiamo eseguito anche discovery e acquisizione sul worker operativo. Entrambi i gruppi hanno pubblicazioni del motore 3.2.0. Le correzioni locali 3.2.1 e Reburn 6.0.3 sono state applicate in replay.

| Misura | MODIS (56) | VIIRS (3) | Totale |
|---|---:|---:|---:|
| Pubblicazioni ottenute | 56 | 3 | 59/59 (100.0%) |
| Combustione mappata e associata | 48 | 2 | 50/59 (84.7%) |
| MODIS pre/post sullo stesso indice | 53 | 3 | 56/59 (94.9%) |
| Baseline post-evento disponibile | 51 | 3 | 54/59 (91.5%) |
| Assessment territoriale valutabile | 51 | 3 | 54/59 (91.5%) |
| Combustione mappata e assessment valutabile | 44 | 2 | 46/59 (78.0%) |
| Almeno una cella con Recovery Intelligence supportata | 53 | 3 | 56/59 (94.9%) |
| Confronto ottico pre/post | 7 | 1 | 8/59 (13.6%) |
| Pubblicazioni con limitazioni | 56 | 3 | 59/59 (100.0%) |
| Errori tecnici terminali | 0 | 0 | 0/59 (0.0%) |

Le categorie ricalcolate sono 48 combustione con vegetazione pre/post, 9 vegetazione del candidato, 2 evidenza limitata, 0 osservazioni insufficienti e 0 errori tecnici. La valutabilità richiede almeno tre anomalie supportate su un indice. Non dimostra il ritorno sostenuto degli indici o il ripristino ecologico.

Il secondo manifesto comprende 44 candidati ordinati deterministicamente prima delle analisi. Abbiamo limitato la nuova acquisizione a tre job seriali oltre i 56 verificati. Le altre 41 selezioni e i cinque viewport con risposta troncata sono registrati nel JSON. Le frequenze descrivono questo campione. [Dati per evento, selezioni, controlli e telemetria](complete-scientific-audit/verification-20261113.json).

### Nuovi eventi acquisiti

| ID e regione | Data | Celle associate | NDVI pre/post | EVI pre/post | Baseline NDVI/EVI | Ottico | Recovery NDVI/EVI | Durata richiesta |
|---|---|---:|---:|---:|---:|---|---|---:|
| global-435e6b4d3977258e6a0ae49f81a1bb40 · brazil | 2024-08-20 | 0 | 30/10 | 30/10 | 9/9 | Sentinel_2 | within_reference_range / within_reference_range | 169.57 s |
| global-3a79f990e04241bb29902b9c0e52d541 · southern_africa | 2022-08-15 | 20 | 35/17 | 35/17 | 17/17 | not_needed | persistent_negative_anomaly / within_reference_range | 151.29 s |
| global-3a2123962b74975c2d07e601be24570e · australia | 2019-09-15 | 65 | 33/18 | 33/18 | 14/14 | not_needed | below_reference / within_reference_range | 176.52 s |

### Difetti riprodotti e impatto misurato

| Priorità e componente | Prima | Correzione e verifica |
|---|---|---|
| P1 · copertura API e frontend | Indonesia aveva 45 celle associate, Alaska 132. Il frontend dichiarava la combustione non confermata per entrambi. Il fallback ottico promuoveva inoltre il caso indonesiano a vegetazione candidata. | Il motore classifica entrambi come evidenza limitata, conserva la misura della combustione e il supporto ottico separati. Il frontend legge la conferma MCD64A1 anche sui vecchi JSON. Due nuovi casi di test e verifica browser sulle due pubblicazioni più la Tunisia. |
| P1 · QA MCD64A1 | Una BurnDate positiva con codice speciale per celle non bruciate poteva superare i filtri evento e ricostruzione episodi. | Maschera esplicita dei bit 5–7 in modis_science e reburn. Oracolo indipendente su tutti i 256 byte. Replay su 51.784 campioni di 186 finestre granulo/evento, 7.107 feature riprodotte incluse le ambigue. Zero campioni reali con data positiva e flag speciale. [Specifica NASA Collection 6.1](https://ladsweb.modaps.eosdis.nasa.gov/filespec/MODIS/61/MCD64A1) |
| P1 · Recovery Gap | La freschezza dipendeva dall’ordine delle righe in ingresso. | Selezione per data finale del composito. Le 251 date Chips/Dixie, 226 celle condivise, 16 richieste EE e 10.280.960 byte decodificati danno la stessa classificazione e gli stessi valori anche in ordine inverso. |
| P1 · antimeridiano | Centro e ampiezza del candidato potevano spostare di migliaia di km il punto mostrato. | Calcolo della longitudine su un intervallo continuo nel cluster, API dettaglio, indice e bounds Leaflet. Verificato su punti controllati, ricerca e dettaglio SQLite/PostGIS. Nessun incendio reale a cavallo del meridiano nel campione. |
| P2 · indice e performance raster | Una query bounds per candidato. Geometria rasterizzata a ogni data e trasformatore ricostruito per cella. | Una query aggregata per pagina, maschera riusata su stesso affine e dimensioni nel singolo assessment, cache limitata dei trasformatori. Su 500 celle il tempo di proiezione in due processi è passato da 0,490 a 0,180 s con SHA-256 WKB identico. Misura del solo kernel. |
| P2 · provenienza su mobile | Il job ID visibile allargava la pagina Chips/Dixie a 626 px su viewport da 390 px. | Il testo va a capo conservando l’identificatore completo. Browser reali su build locale a 390 e 1440 px con controlli su serie, mappe, valori API e assenza di overflow. |

### Verifiche operative

Tunisia, 14 luglio 2026. Le due pubblicazioni versionate sono state ricontrollate sui raw. Nessun composito post-evento raggiunge la copertura territoriale. Nove celle su 255 hanno evidenza locale per indice. Il nuovo prelievo HLS dà dNBR 0,03907087 su 9.627 centri comuni, con scarto di 0,00000209 dal valore EE. I due TIFF serviti dall’API hanno 156 bande ciascuno, zero bande vuote e valori identici alle bande conservate dei file originali. Il confronto ottico descrive l’area candidata. MCD64A1 non conferma la combustione.

Sui 59 eventi il replay temporale indipendente ha verificato 2696 punti baseline. La ricostruzione nativa ha valutato 25642 celle NDVI e altrettante EVI, senza asset mancanti. I sette riferimenti storici sono stati riaperti per otto pubblicazioni versionate. Le cinque storie Reburn includono due versioni Chips/Dixie e una storia senza sorgenti.

Tre SIGKILL e riavvii Docker isolati ai progressi 50/90/99 hanno prodotto un secondo tentativo, riuso del checkpoint, zero nuove richieste e zero job fantasma. Suite complete del workspace con tutte le modifiche locali: 260 SQLite e 260 PostgreSQL/PostGIS. Sul solo contenuto del commit: 251 per database. La differenza sono nove test locali preesistenti fuori dal commit. Build TypeScript/Vite, Chromium, controlli API e scansione dei segreti eseguiti.

I tre nuovi job hanno richiesto 151–177 s, mediana 169,57 s. Le tre ripetizioni hanno restituito lo stesso job in 21–38 ms. I byte acquisiti sono array decodificati. Il campione istantaneo del worker era di 629,9 MiB e 96,65% CPU. Cache su disco circa 406 MiB e database operativo 168.629.039 byte. Le distribuzioni cold/warm storiche sono documentate più sotto. Il JSON conserva tempi e contatori disponibili per fase. Preflight, memoria di picco e traffico HTTP per singolo evento non sono stati strumentati in questa estensione.

Riproduzione del burn mask: dal runtime backend impostare PYTHONPATH=backend ed eseguire python scripts/verify_burn_quality_replay.py docs/complete-scientific-audit/verification-20261113.json /percorso/cache/satellite. Il comando usa i job versionati e i sottoinsiemi MCD64A1 originali.

### Chiusura sulla revisione corrente

La ripresa ha verificato il commit cfa8cb5 in una nuova immagine backend costruita dalle dipendenze dichiarate. Il contenuto interamente committato passa **260 test SQLite e 260 PostgreSQL/PostGIS**, con zero errori, fallimenti o skip. I 251 test citati sopra descrivono il precedente commit parziale 74250d5. Sono riuscite la build frontend e le verifiche Chromium desktop/mobile su Explorer, Recovery Story e Chips/Dixie.

Nuovo controllo API dei 56 JSON congelati, tutti identici. Il replay indipendente della maschera MCD64A1 sui 59 eventi riproduce 7.107 feature da 51.784 campioni in 186 finestre sorgente. I due GeoTIFF Tunisia mantengono 156 bande utili ciascuno. Le verifiche usano il codice corrente e le pubblicazioni operative versionate. L’attivazione delle nuove immagini nei servizi operativi resta da eseguire.

[Esiti della revisione corrente e impronte dei test](complete-scientific-audit/final-revision-verification-20261113.json).

## Campagna dell’11 novembre 2026


Verifica del 11 novembre 2026. Base Git `6dda3c3`. Il lavoro locale precedente è stato preservato. Questo rapporto distingue esecuzioni reali, replay di osservazioni originali, test controllati e limiti non dimostrati. Gli artefatti pubblicabili sono metadati e fixture derivate; credenziali, database, cache e raster rimangono fuori da Git.

## Risposta misurata

Su **56 candidati reali** estratti dall’Explorer:

| Misura | Casi | Percentuale |
|---|---:|---:|
| Pipeline terminata con pubblicazione | 56/56 | 100,00% tecnico |
| Celle MCD64A1 associate senza ambiguità | 48/56 | 85,71% |
| MODIS pre/post dello stesso indice | 53/56 | 94,64% |
| Almeno un confronto post-evento con baseline stagionale | 51/56 | 91,07% |
| Assessment temporale descrittivo valutabile | 51/56 | 91,07% |
| Combustione mappata **e** assessment valutabile | **44/56** | **78,57%** |
| Intelligence con almeno una cella supportata | 53/56 | 94,64% |
| Coppia ottica supportata nel fallback eseguito | 7/56 | 12,50% |
| Pubblicazioni parziali con lacune dichiarate | 56/56 | 100,00% |
| Errori tecnici terminali | 0/56 | 0,00% |

Le cinque categorie scientifiche restituiscono 46 `burn_and_vegetation_supported`, 9 `candidate_vegetation_supported`, 1 `partial_evidence`, 0 `insufficient_observations`, 0 `technical_error`. Una categoria con BA+VI richiede osservazioni pre/post, non necessariamente una baseline sufficiente. Per questo 46 BA+VI non equivalgono a 46 analisi del recupero supportate. La valutabilità è definita da `assess_index`: almeno tre anomalie post-evento supportate, sullo stesso indice, rispetto al riferimento pre-evento. Nel campione, tutti i 51 assessment valutabili e tutte le 51 baseline supportate lo sono per entrambi gli indici NDVI/EVI. Il ritorno sostenuto richiede inoltre la durata e consecutività documentate; non viene dedotto dalla sola valutabilità.

**Questi conteggi non dimostrano recupero ecologico**, né rappresentano tutti gli incendi globali. Sette valutazioni temporali supportate riguardano soltanto vegetazione candidata, senza BA confermata. Tutti i casi conservano almeno una limitazione o lacuna. Il denominatore ottico include eventi per i quali il fallback non è necessario: non misura il successo del catalogo ottico su tutti gli eventi.

Dati riproducibili: [summary finale](complete-scientific-audit/after-summary.json), [CSV finale dei 56 eventi](complete-scientific-audit/after-cases.csv), [risultati finali](complete-scientific-audit/after-enriched.json), [supplemento finale](complete-scientific-audit/supplement/after-enriched.json). Il [primo passaggio](complete-scientific-audit/summary.json) rimane distinto.

## Campionamento e risorse

Seme `afterfire-complete-audit-20261111-v1`; primi cinque candidati per ordinamento SHA-256 di seme+ID in ciascuna finestra geografica e temporale predefinita, prima di richiedere le analisi. Le dodici finestre iniziali hanno restituito 46 candidati, tutti conservati. Sono state quindi congelate due finestre supplementari, Zambia e Brasile, producendo altri dieci candidati senza consultarne gli esiti. I manifesti separati documentano esattamente questa estensione; non è una selezione retroattiva dei casi favorevoli.

Il campione comprende 14 finestre in Sudamerica, Africa, Oceania, Asia, Nordamerica ed Europa; periodi 2019–2026; 3–168 osservazioni FIRMS per candidato; aree analizzate 0,644–403,558 km²; casi costieri, Indonesia, Alaska, Siberia, California e territori agricoli/savana. Il discovery del campione usa FIRMS MODIS; la normalizzazione VIIRS è coperta dai test provider e dai riferimenti precedenti, ma non è stato eseguito un secondo campionamento casuale bilanciato per VIIRS. Le etichette di regione sono geografiche: non è stata effettuata una classificazione indipendente del bioma o dell’uso del suolo. Non si rivendica un campionamento stratificato statisticamente rappresentativo di tutti i biomi, rilievi o storie di reburn. Gli eventi di riferimento 2012–2024 e il caso tunisino obbligatorio sono verifiche aggiuntive separate.

Un solo worker, acquisizioni e budget nativi esistenti, nessun archivio globale, nessuna nuova submission AppEEARS e nessun download automatico di scene HDF complete. Due client seriali accodano al medesimo worker; le latenze conservano le rispettive attese. Sette casi hanno riutilizzato una pubblicazione esistente, 49 hanno eseguito la pipeline. I controlli indipendenti sono processi distinti e possono influenzare CPU e I/O. Nessun candidato selezionato è stato eliminato. Il campione non è esteso a 100: si evita di raddoppiare acquisizioni e pressione sulle quote dopo aver superato il requisito minimo.

Il candidato tunisino casuale del manifesto (`global-5fcb…`) è a circa 9,646°E e **non è** il caso obbligatorio a 10,174°E; il secondo rimane una regressione autonoma. I manifesti conservano coordinate e membership, evitando di confondere incendi nella stessa regione/data.

## Audit delle funzionalità

| Funzionalità | Verifica eseguita | Esito e limiti |
|---|---|---|
| FIRMS, date, deduplicazione, cluster e identità | Query reali Explorer; manifesti congelati; test viewport, sensori, UTC, duplicati e membership | 56 candidati persistiti e analizzati; candidati termici, non perimetri o conferme di combustione |
| Geometria e griglie | Calcolo metrico AEQD, centri MODIS, CRS e area nativa nei raster originali; test confini/tile/antimeridiano | Nessun nuovo errore di griglia MODIS osservato; nessuna pubblicazione reale all’antimeridiano rivendicata |
| MCD64A1 | Lettura indipendente QA, BurnDate, incertezza, data/evento, area e celle native | 48 candidati del campione con BA non ambigua; QA rifiutato mai promosso a burn |
| MOD13Q1 NDVI/EVI | Tutte le 65.536 parole QA confrontate con decoder indipendente; raw range/scaling/copertura su sorgenti trattenute | Maschera stretta e ×0,0001 invariati; 144 righe rifiutate nel caso tunisino spiegate dai raw |
| Baseline e anomalie | Calendario indipendente, mediana, MAD, anni e assenza di leakage; test metamorfico su ordine e valori futuri | 2.500 punti con baseline verificati nel primo passaggio e 2.504 nel replay; tutte le verifiche temporali 56/56 passate |
| Motore multisensore | QA specifico, limiti pixel, scene reali HLS; probe Landsat 7 del 2012; cataloghi eleggibili | Indici ottici separati da MODIS; nessuna baseline multisensore inventata; non tutti gli adattatori hanno nuove scene live in questa campagna |
| NBR/dNBR | Griglia intera, supporto congiunto, mediana esatta, confronto raw indipendente | Corretto il falso rifiuto di tile allineati; CRS/shift frazionari incompatibili restano indisponibili |
| Recovery Story | Serie/API e classificazioni per indice, gap e baseline; controlli browser rappresentativi | 51 valutazioni descrittive; solo 44 anche con BA mappata; nessuna percentuale di recupero ecologico |
| Intelligence | Ricostruzione locale di entrambe le storie native per tutti i 56 casi | 28.507 celle per indice nel primo passaggio, 25.199 dopo il contesto completo; supporto per pixel distinto dal composito territoriale |
| Persistenza/trend | Theil–Sen indipendente su mediane mensili, run, lacune, ritorno sostenuto | Nessuna interpolazione; eventi senza supporto restano insufficienti nelle metriche pertinenti |
| Reburn/Recovery Gap | Cinque storie reali trattenute, ricostruzione indipendente episodi e celle condivise; test temporali/limiti | Non prova di causalità o mancato recupero; nessuna nuova acquisizione pluridecennale per ogni candidato casuale |
| Cache | Checksum, corruzione/ripristino, hardlink, lease; classificazione sorgenti API | Corretto il trattamento dei TIFF API come metadati non eliminabili; manifesti e pubblicazioni protetti |
| Worker e DB | Retry HTTP/trasporto, transazioni, vecchio risultato, duplicate request, SIGKILL/restart isolati | Pubblicazione atomica e ripresa checkpoint verificate; nessun arresto distruttivo dei dati operativi |
| API/UI/raster | Valori reali, identità scene, semantica di data/periodo e contenuto GeoTIFF | Corretto colore neutro e scope; nessun redesign |

## Regressione obbligatoria: Tunisia, 14 luglio 2026

ID `global-8ab308b435230781004c8e0d80c7dba6`; tre osservazioni FIRMS; 36,717°N, 10,174°E; area candidata 13,6077826756 km². Fixture permanente: `backend/app/tests/fixtures/tunisia_20260714.json`, ricavata da pubblicazioni autentiche e verificata con un calcolo indipendente delle baseline dei nove pixel supportati per indice.

### MODIS: non è una geometria vuota

255 centri MOD13Q1 nell’area; 75 granuli vegetativi completi trattenuti; 152 righe indice/data attese, di cui sei accettate solo prima dell’evento, 144 rifiutate per QA/copertura e due nell’ultimo periodo incompleto. I sei periodi post-evento completi hanno rispettivamente **85, 1, 63, 13, 0, 0** pixel NDVI validi su 255. Nessuno raggiunge 128 pixel, necessari per copertura ≥50%. L’ultimo periodo non è usato perché oltrepassa `as_of`.

Nei 19.125 campioni sorgente NDVI ispezionati, le classi land/water sono 10.428 land, 7.910 coast e 787 shallow inland water. Conteggi di rifiuto sovrapposti: reliability 14.882, MODLAND 9.722, usefulness 10.233, land/water 8.697, adjacent cloud 7.327, mixed cloud 1.885, shadow 1.563, high aerosol 408, raw range 108, snow 0. Non si sommano come partizione: un pixel può fallire più controlli.

MCD64A1 ha 191/192 campioni con QA di mapping valido nei tre granuli, ma **zero celle associate** all’evento. Quindi non si attribuisce lo zero alla semplice assenza del prodotto o a una mappa tutta nodata. Nessuna soglia QA è stata abbassata. [Diagnostica raw](complete-scientific-audit/tunisia-independent-native.json).

### HLS: scene distinte e griglia condivisa

Le dodici righe hanno dodici ID differenti. Stessa data può significare due tile (`T32SNF`, `T32SPF`) della medesima acquisizione, oppure orari differenti (`100029`, `100701`). Sono mantenute separate, con identità e timestamp; le loro mediane non vengono aggregate o pesate come osservazioni indipendenti. Il frontend mostra l’ID breve nella tabella e l’ID completo nella provenienza.

La coppia del 13/18 luglio usa EPSG:32632, vettori pixel 30/−30 m e origini X 600.000/499.980 m: differenza **3.334 pixel interi**. Sono la stessa griglia infinita con estensioni differenti. Il confronto ora specifica il CRS e l’affine pre-evento e sottrae NBR soltanto sul supporto QA congiunto; nessuna interpolazione.

Il riduttore mediano predefinito EE forniva circa 0,0399962 con approssimazione a istogramma. Con `maxRaw` pari al budget massimo di pixel, dNBR è **0,03906878099**. Calcolo indipendente NumPy sui raw B8A/B12/Fmask/B4/B2: **0,03907087331** su 9.627 centri comuni di 15.110 (63,7128%). Differenza **0,0000020923**, entro la tolleranza predefinita 0,0001 per la differenza tra centri locali e pesatura delle celle di bordo EE. Trasferiti 2.143.152 byte di array decodificati, non una scena completa. La riduzione EE usa 15.109 campioni territoriali; lo scarto di un centro al confine resta dichiarato.

Questo è **cambiamento spettrale descrittivo**; non conferma combustione, severità o recupero. Gli shift frazionari, pixel diversi e CRS differenti continuano a dare indisponibilità. Il selettore verifica anche coppie alternative supportate nella finestra, senza combinare tile sovrapposti.

### Intelligence: 9/255 non contraddice lo zero territoriale

L’assessment territoriale usa sette slot post-evento; nessuno è accettato. Le storie native ereditano il QA dei singoli pixel, che possono essere validi anche in un composito territoriale rifiutato per copertura. Nove pixel per indice hanno almeno tre anomalie post-evento con baseline locale valida; gli altri 246 rimangono insufficienti. La verifica delle date e baseline delle nove storie usa solo campioni pre-evento. La classificazione riguarda l’intervallo post-evento, mentre la mappa anomalia può mostrare una singola data. API e frontend esplicitano la differenza: nessun recupero dell’intera area è dimostrato.

### GeoTIFF: contenuto reale, esportazione ridotta

I due asset originali hanno 232 bande, griglia sinusoidale 27×21, pixel 231,656358 m; dimensioni 52.662 e 52.904 byte. **76 bande per asset sono completamente nodata**. Le altre contengono valori pixel, baseline, anomalie e bande statiche, anche quando il composito dell’intera area è rifiutato.

Il nuovo exporter produce 156 bande, 44.972/45.220 byte nel replay controllato. Gli asset effettivamente pubblicati e scaricati via API occupano 45.200/45.448 byte, includendo i tag completi di geometria e periodo; [controllo dei download](complete-scientific-audit/tunisia-published-asset-verification.json). Ogni banda rimasta è confrontata con la corrispondente descrizione dell’originale: stessi valori e nodata, affine e CRS identici. Nuovi tag dichiarano supporto per cella, periodo delle osservazioni, periodo di classificazione, geometria e zero compositi territoriali supportati. L’API fornisce le descrizioni delle bande effettive; nessun consumer deve inferire una posizione fissa 3×date+4. Una storia senza alcun valore finito non genera un asset di soli zeri statici. Le vecchie pubblicazioni restano disponibili e non sono riscritte.

[Ispezione originale](complete-scientific-audit/tunisia-raster-inspection.json), [confronto export](complete-scientific-audit/tunisia-export-after.json). Esito scientifico: vegetazione candidata osservata otticamente; combustione non confermata e recupero territoriale non valutabile.

## Difetti riprodotti e corretti

| Gravità | Causa prima | Correzione e prova dopo |
|---|---|---|
| P1 scientifica | Pre NDVI + post EVI soddisfacevano il gate generico pre/post | Intersezione degli indici in `coverage.py` e nel gate ottico della pipeline; test prima fallito, ora `partial_evidence` e fallback ammesso |
| P2 scientifica | Confronto letterale degli oggetti Projection rifiutava tile HLS sulla stessa griglia | Confronto CRS/vettori/offset intero; coppie alternative; regressione Tunisia e probe Landsat 7 reale |
| P2 numerica | Mediana ottica predefinita poteva diventare approssimata senza indicarlo | Riduzione esatta entro budget invariato; confronto raw indipendente fino a 2,1×10⁻⁶ |
| P2 asset | Export all-nodata o con sole bande statiche sembrava un prodotto informativo; bande vuote mantenute | Nessun export senza valori; sole bande finite, metadati espliciti; test negativo e uguaglianza delle bande Tunisia |
| P2 UI scientifica | `within_reference` non corrispondeva all’enum backend `within_reference_range` | Celle nel riferimento usano il colore neutro dichiarato, anziché nodata |
| P2 interpretazione | “Same date as Story” appariva anche sulle classificazioni di periodo | Etichetta distinta per data anomalia/periodo; supporto per cella e territoriale dichiarati in JSON/UI/export |
| P2 cache | `api-subsets/native.tif` classificato come metadata protetto | Categoria `subsets`, rendicontazione e dry-run LRU corretti; manifesti protetti e nessuna cancellazione operativa durante la prova |
| P2 isolamento test | Database temporaneo ma directory cache ereditabile dal deployment | Tutte le cache provider/scientifiche redirette alla directory temporanea dei test |

Per la cache, la fixture prima classificava 2.050 byte tutti come metadata; dopo distingue 2.048 byte di array e due byte di manifest. Il dry-run seleziona soltanto l’array, conservando entrambi i file durante la prova. [Evidenza](complete-scientific-audit/cache-classification-regression.json).

Le versioni nuove sono `modis-recovery-3.2.0`, `optical-evidence-3`, `assessment-5.0.2`; il checkpoint MODIS resta `modis-recovery-3.0.0` perché calibrazione e QA non sono cambiati. Le pubblicazioni vecchie non vengono aggiornate retroattivamente. La suite include anche 300 trasformazioni casuali riproducibili: traslazioni di pixel interi preservano la griglia, mentre spostamenti di un quarto di pixel sono rifiutati. Le correzioni sono concentrate in `coverage.py`, `post_fire_pipeline.py`, `optical_evidence.py`, `spatial_recovery.py`, `cache_management.py`, schemi/versioni e i due componenti UI interessati; test e fixture in `test_complete_scientific_audit.py`.

## Replay completo e dipendenza dal contesto dei candidati

Il replay `modis-recovery-3.2.0` è terminato su **56/56** casi, senza nuovi array MODIS acquisiti. Restano 46 BA+VI, nove VI candidata e un risultato limitato; 48 con BA, 51 assessment valutabili, 44 anche con BA. Le verifiche indipendenti temporali e spaziali del replay passano su tutti i 56. Un worker aggiuntivo è stato usato temporaneamente; i job sono stati preaccodati e le cache erano calde. Il servizio è tornato a un solo worker, senza job attivi residui al controllo finale.

**Non tutti i numeri prima/dopo sono identici**: le celle burned area osservate, date, QA e incertezze sono identiche in 56/56; geometria di analisi e serie MODIS sono identiche in 54/56. Quattro payload burned area hanno differenze di associazione/provenienza, una delle quali soltanto l’ordine degli ID concorrenti.

La prima campagna persisteva ogni candidato soltanto prima della sua analisi. Registrando successivamente altri candidati vicini in California, il contesto di associazione è aumentato. Nel replay tutti erano già presenti:

| Candidato | Area prima km² | Area dopo km² | Ambigue prima/dopo | Causa verificata |
|---|---:|---:|---:|---|
| `global-de962de3f998e4976373e018b1aa0a0d` | 4,722491 | 1,717269 | 0 / 14 | Due candidati concorrenti ora registrati |
| `global-7d39d5f32e51ecf008a57c5f6238fcb2` | 403,558306 | 229,040804 | 31 / 844 | Altri tre candidati concorrenti ora registrati |

Le aree di burn osservate restano rispettivamente 4,722491 e 410,212725 km². Cambia la frazione associabile senza ambiguità al singolo candidato, che definisce il territorio della vegetazione. Le serie sono quindi ricalcolate su quelle geometrie, senza alterare QA o sorgenti. I cinque candidati coinvolti non condividono ID FIRMS (verificate tutte le dieci intersezioni); ciò esclude duplicati letterali delle osservazioni, ma non dimostra cinque incendi fisici indipendenti. La regola resta una scelta conservativa di associazione fra candidati, non una delimitazione indipendente degli incendi.

Una nuova verifica raw indipendente è passata su **tutte e quattro le pubblicazioni** dei due eventi (prima e dopo): maschere geometriche, conteggi, scaling, mediane e baseline corrispondono alle rispettive aree. Le vecchie pubblicazioni non sono state riscritte. La dipendenza dai candidati già registrati è un limite metodologico: la cache è una fotografia pubblicata del contesto disponibile, non una garanzia che nuovi candidati non possano cambiare una futura attribuzione. Non si considera questo passaggio un A/B controllato con input di associazione identici.

Il runner è corretto: registra **l’intero manifesto congelato prima della prima analisi**, così l’ordine di esecuzione non amplia il contesto durante le campagne future. Si conserva la traccia del difetto della campagna iniziale; non si riscrive retroattivamente il primo passaggio. [Confronto completo](complete-scientific-audit/before-after-comparison.json), [differenze](complete-scientific-audit/context-differences.json), [membership FIRMS](complete-scientific-audit/context-membership.json), [raw prima/dopo](complete-scientific-audit/context-independent-raw.json).

Tempi del replay, separati: pipeline mediana 31,715 s, p95 58,388 s; zero byte MODIS nuovi. Le latenze del collector includono job già completati dal preaccodamento e **non sono** un benchmark di velocizzazione del codice rispetto al primo passaggio.

## Prestazioni e limiti operativi

Primo passaggio, con un worker: richiesta→risultato mediana **153,498 s**, p95 interpolato **311,785 s**; pipeline: mediana **97,190 s**, p95 **272,778 s**. Sette richieste erano cache di pubblicazioni (<1 s), le altre 49 nuove pipeline hanno mediana richiesta **162,855 s**. Ripetizione dopo pubblicazione: stesso job in **56/56**, mediana **0,028 s**. Non si confronta il replay caldo con il primo passaggio come prova di accelerazione del codice.

Array acquisiti e decodificati: **153.641.308 byte**; traffico di rete completo, overhead SDK, autenticazione e traffico interno EE non sono misurati. I contatori Docker includono tutto il container e l’attività precedente: non sono byte acquisiti per evento.

Outlier: `global-7d39…` California, 460,347 s, area 403,558 km², 371,215 s in acquisizione batch EE; `global-ae03…` California, 367,015 s, due tile, 227,116 s acquisizione e 92,769 s salvataggio checkpoint; `global-c8c5…` Alaska, 342,020 s, 244,291 s acquisizione. Il campione conserva questi casi. Il guard nativo ha escluso il fallback ottico dell’evento California `global-a67a…` per budget, pur mantenendo MODIS disponibile.

La scansione completa della cache prima dei job costa mediana 12,471 s; i salvataggi checkpoint mediana 36,139 s complessivi per evento. Sono costi residui reali del filesystem e dell’accounting esatto della quota. Un tentativo `scandir` misurato sullo stesso cache non ha mostrato un miglioramento stabile e **non è stato mantenuto**. Non si introducono contatori di quota non sincronizzati per ottenere benchmark favorevoli. Il bug confermato della classificazione delle sorgenti API è invece corretto. Le ottimizzazioni ulteriori richiedono una riserva quota transazionale condivisa fra tutti gli scrittori, fuori da questa modifica scientifica.

Snapshot operativi: backend con verificatore indipendente circa 1,084 GiB/98% di un core; worker inattivo dopo la campagna circa 862,5 MiB; PostgreSQL circa 198 MiB. Sono campioni, **non picchi attribuibili a un singolo evento**. Cache misurato 178.821.263 byte in 91.033 file fisici distinti, con hardlink contati una volta; il database operativo non è stato cancellato o ricreato. I dettagli temporali per fase e l’RSS dell’auditor sono conservati nei JSON per evento.

## Affidabilità

- Test isolati di HTTP 408/429/500/502/503/504: `Retry-After=120` rispettato, tre tentativi massimo; trasporto, timeout e risposte incomplete coperti anche dalle suite provider esistenti.
- Errore di commit al 50%, 90%, 99%: vecchio risultato conservato, aggiornamento job annullato nella stessa transazione, ripubblicazione successiva riuscita.
- Tre container temporanei **senza rete**, ciascuno con SQLite/cache propri: SIGKILL reale, riavvio dello stesso filesystem, lease scaduto reclamato con owner nuovo, tentativo 2, checkpoint verificato riusato, zero nuove richieste sorgente, risultato atomico e nessun job fantasma. Il lease di prova è abbreviato esplicitamente a tre secondi; non è la durata produttiva.
- Due richieste concorrenti dello stesso evento, owner scaduto, stale publication, DB indisponibile durante publish e ripresa sono testati senza operare distruttivamente sul database scientifico.
- Checkpoint corrotto viene rifiutato e rigenerato; nessun valore corrotto diventa osservazione.

[Restart 50](complete-scientific-audit/restart-50.json), [90](complete-scientific-audit/restart-90.json), [99](complete-scientific-audit/restart-99.json). Non è stato spento il daemon Docker né interrotta la rete del database produttivo. I test non provano tolleranza a ogni combinazione di guasti simultanei o outage prolungato del provider.

## Suite, riferimenti e fonti

Le suite finali passano **232 test su SQLite e 232 su PostgreSQL/PostGIS**: includono test scientifici/provider/API/worker/cache/resilienza e non disabilitano test. La build TypeScript/Vite e le tre immagini Docker sono riuscite. [JUnit SQLite](complete-scientific-audit/sqlite.xml), [JUnit PostgreSQL](complete-scientific-audit/postgres.xml). Il database PostgreSQL dedicato è `afterfire_test_complete_20261111`, con PostGIS 3.3.4. I primi tentativi Docker mancavano di script/dati nel layout di test e sono stati corretti riproducendo il layout del repository; non erano difetti scientifici. Il test di conteggio bande preesistente è aggiornato al contratto esplicito: bande presenti + bande vuote omesse = inventario originario; verifica inoltre che ogni banda esportata contenga valori finiti.

I riferimenti Rodi `global-d77c…`, Jasper `global-89d6…`, Kangaroo `global-b8c4…`, Chips/Dixie `global-5191…`, Sardegna `global-3667…`, Canada HLS `global-0836…` e Tunisia `global-8ab3…` sono mantenuti. La verifica indipendente iniziale su 53 pubblicazioni e cinque storie Reburn ha controllato 3.199.012 campioni QA grezzi, 7.586 compositi e 3.923 celle burned area. La verifica finale è poi passata su **tutte le 100 pubblicazioni** dopo il campionamento: **6.841.340** controlli QA raw, **13.924** compositi, **10.495** celle burned area e le cinque storie Reburn. [Evidenza finale](complete-scientific-audit/independent-final.json). È una nuova verifica dei file originali trattenuti, non un nuovo download HDF. Il probe Landsat 7 del 2012 sui pixel dell’evento Chips offre 11 scene supportate su 12 e dNBR descrittivo 0,379461 sul 72,01% congiunto; resta fuori dalle percentuali del campione.

La conservazione mediante SHA-256 confronta i payload interi: tutte le 51 pubblicazioni iniziali, dieci assessment e cinque storie Reburn restano identici dopo la campagna. Le nuove analisi non sostituiscono questi record.

Browser reale del frontend aggiornato: Tunisia mobile 390×844 (12 identità scene, anteprime reali 512 px, dNBR 0,039, zero compositi post, 9/255 celle e 156 bande); Brasile casuale desktop 1440×1000 (140 celle bruciate, 12 compositi post per indice, 560/560 pixel supportati, cambio NDVI/EVI); Chips/Dixie (quattro episodi, 228 celle ripetute e Recovery Gap sulle 226 celle condivise). Nessun overflow rilevato. I valori sono confrontati con pubblicazioni/API e verifiche indipendenti. Chrome DevTools non trovava Chrome stable: è stato usato il browser Chromium integrato, senza mock API. [Evidenza browser](complete-scientific-audit/browser.json).

Fonti primarie consultate per le correzioni:

- [HLS S30: bande, Fmask e prodotto](https://developers.google.com/earth-engine/datasets/catalog/NASA_HLS_HLSS30_v002).
- [Riduttore mediano e soglia maxRaw](https://developers.google.com/earth-engine/apidocs/ee-reducer-median).
- [reduceRegion: CRS, scala e affine](https://developers.google.com/earth-engine/apidocs/ee-image-reduceregion).
- [Proiezioni Earth Engine](https://developers.google.com/earth-engine/guides/projections).
- [HLS User Guide v2](https://lpdaac.usgs.gov/documents/1698/HLS_User_Guide_V2.pdf).

I conteggi dei controlli raw/compositi/celle nelle 100 pubblicazioni sono operazioni di verifica per indice e pubblicazione: possono rileggere lo stesso pixel in risultati differenti e non costituiscono campioni indipendenti o aree da sommare. I 56 ID del campione sono candidati distinti; frammenti spaziali di uno stesso incendio possono essere correlati.

I limiti vanno separati: un errore software è una classificazione/operazione sbagliata; assenza di burn mapping, poche osservazioni post-evento, QA costiero e nubi sono limiti osservativi; pixel misti e risoluzione sono limiti del sensore; il ritorno degli indici non dimostra ripristino ecologico. Nessuno di questi casi viene riempito con dati sintetici.

## Tabella completa dei 56 candidati

Tabella delle pubblicazioni finali del replay; s = durata effettiva della pipeline, non attesa del collector. BA = celle univoche MCD64A1; pre/post sono compositi validi per indice; baseline N/E = numero di anomalie post-evento supportate; Recovery N/E = classificazione temporale valutabile, non recupero dimostrato. Problemi specifici, configurazioni, classificazioni, tempi per fase, bytes e supporto EVI sono nel CSV/JSON collegati sopra.

| Event ID | Regione / data | FIRMS | BA celle | NDVI pre/post | EVI pre/post | Baseline post N/E | Ottico | Recovery N/E | Celle supportate NDVI | Stato | s |
|---|---|---:|---:|---|---|---|---|---|---|---|---:|
| `global-75e84782b376558619c389da8e6fc716` | brazil / 2024-08-21 | 25 | 140 | 28/12 | 28/12 | 10/10 | not_needed | sì/sì | 560/560 | BA + VI | 26.570 |
| `global-1da33a9eb741c54ede92a99dd7bcec3b` | brazil / 2024-08-22 | 5 | 37 | 16/8 | 16/8 | 6/6 | not_needed | sì/sì | 96/148 | BA + VI | 26.310 |
| `global-064accfd021b4683dc3aba56b06de7fd` | brazil / 2024-08-20 | 44 | 125 | 27/13 | 27/13 | 10/10 | not_needed | sì/sì | 500/500 | BA + VI | 26.060 |
| `global-66cbb1d3ab8865c663719a9cf3287fd6` | brazil / 2024-08-20 | 10 | 21 | 23/9 | 23/9 | 7/7 | not_needed | sì/sì | 84/84 | BA + VI | 20.880 |
| `global-f626c357cf56a84c532365e622c257da` | brazil / 2024-08-21 | 3 | 3 | 30/12 | 30/12 | 12/12 | not_needed | sì/sì | 12/12 | BA + VI | 21.700 |
| `global-18f50185ddfea0a5b9e83c23d27e0d70` | southern_africa / 2022-08-15 | 3 | 11 | 35/18 | 35/18 | 17/17 | not_needed | sì/sì | 44/44 | BA + VI | 27.550 |
| `global-4e355c2147307573902bfda62fc7ed69` | southern_africa / 2022-08-15 | 9 | 122 | 38/17 | 38/17 | 17/17 | not_needed | sì/sì | 488/488 | BA + VI | 30.490 |
| `global-e6ef6f62f38984d41744412b16a31563` | southern_africa / 2022-08-15 | 6 | 18 | 34/16 | 34/16 | 15/15 | not_needed | sì/sì | 72/72 | BA + VI | 21.170 |
| `global-ac7c9cdea11c4c4d67d83f55068a8d1d` | southern_africa / 2022-08-15 | 3 | 18 | 34/18 | 34/18 | 17/17 | not_needed | sì/sì | 72/72 | BA + VI | 38.100 |
| `global-ff6d763ce384d2d79be0260c41560c1d` | southern_africa / 2022-08-17 | 6 | 37 | 34/17 | 34/17 | 14/14 | not_needed | sì/sì | 148/148 | BA + VI | 34.870 |
| `global-e0ee6acc85dc19bdec7fb4730e0fc23a` | australia / 2019-09-15 | 4 | 7 | 37/18 | 37/18 | 17/17 | not_needed | sì/sì | 28/28 | BA + VI | 32.210 |
| `global-1ca9b13efea381d35aad976a47e337cd` | australia / 2019-09-15 | 19 | 125 | 41/21 | 41/21 | 21/21 | not_needed | sì/sì | 500/500 | BA + VI | 21.210 |
| `global-0dd9b9d40589368dd479050d3d712f4b` | australia / 2019-09-15 | 5 | 28 | 38/18 | 38/18 | 17/17 | not_needed | sì/sì | 112/112 | BA + VI | 31.740 |
| `global-2c9edb4c5b549bc9ef91ce283b92c436` | australia / 2019-09-15 | 4 | 26 | 32/19 | 32/19 | 14/14 | not_needed | sì/sì | 104/104 | BA + VI | 42.210 |
| `global-3260eea6dc85e332b61a3c023b8f1800` | australia / 2019-09-15 | 6 | 16 | 34/20 | 34/20 | 18/18 | not_needed | sì/sì | 64/64 | BA + VI | 31.690 |
| `global-926d0f8dfe6563451f7e9c7b3f25fbc3` | siberia / 2021-07-16 | 5 | 3 | 12/4 | 12/4 | 3/3 | not_needed | sì/sì | 4/12 | BA + VI | 38.690 |
| `global-9709bff093c7ccab50d2ecdc3c235e6e` | siberia / 2021-07-16 | 8 | 0 | 15/7 | 15/7 | 6/6 | HLS_S30 | sì/sì | 161/169 | VI candidata | 49.120 |
| `global-be5478484e497710b3b4bd18a18cc445` | siberia / 2021-07-15 | 20 | 0 | 12/5 | 12/5 | 4/4 | partial_vegetation_observations | sì/sì | 435/575 | VI candidata | 55.200 |
| `global-7979a92ec3524e523ee8bb35539ef03e` | siberia / 2021-07-15 | 18 | 35 | 10/5 | 10/5 | 3/3 | not_needed | sì/sì | 84/140 | BA + VI | 23.220 |
| `global-f3d3c4014edc70644b64c7c963e8a668` | siberia / 2021-07-15 | 15 | 26 | 10/5 | 10/5 | 4/4 | not_needed | sì/sì | 104/104 | BA + VI | 21.540 |
| `global-febf57e02ba47a52868adecbabde8687` | canada_west / 2023-05-21 | 7 | 8 | 20/5 | 20/5 | 4/4 | not_needed | sì/sì | 32/32 | BA + VI | 34.640 |
| `global-dd1f007922be49d30908018cf1dae028` | canada_west / 2023-05-20 | 86 | 144 | 23/11 | 23/11 | 8/8 | not_needed | sì/sì | 576/576 | BA + VI | 35.040 |
| `global-4bc6ed9108d9e2b29d5f6af3e3f6b198` | canada_west / 2023-05-20 | 10 | 106 | 22/10 | 22/10 | 8/8 | not_needed | sì/sì | 424/424 | BA + VI | 24.130 |
| `global-b872c5e27c461e9c4ae724060b788cd0` | canada_west / 2023-05-21 | 3 | 0 | 22/6 | 22/6 | 4/4 | HLS_S30 | sì/sì | 99/104 | VI candidata | 38.050 |
| `global-52af204a40bf9f82a228e9f54085fe7f` | canada_west / 2023-05-20 | 14 | 34 | 20/9 | 20/9 | 7/7 | not_needed | sì/sì | 136/136 | BA + VI | 22.770 |
| `global-5fcb2781ec1c584d2d7f8f18aeef7c8f` | tunisia_coast / 2026-07-14 | 5 | 13 | 42/5 | 42/5 | 5/5 | not_needed | sì/sì | 52/52 | BA + VI | 40.500 |
| `global-730fd3db3b65e67698840df5cf924b77` | sardinia / 2026-07-16 | 8 | 11 | 39/6 | 39/6 | 6/6 | not_needed | sì/sì | 44/44 | BA + VI | 32.310 |
| `global-de962de3f998e4976373e018b1aa0a0d` | california / 2021-08-01 | 4 | 8 | 28/14 | 28/14 | 13/13 | not_needed | sì/sì | 32/32 | BA + VI | 176.080 |
| `global-7d39d5f32e51ecf008a57c5f6238fcb2` | california / 2021-08-01 | 168 | 1067 | 32/15 | 32/15 | 15/15 | not_needed | sì/sì | 3704/4268 | BA + VI | 180.670 |
| `global-a67a52521ea9434f0783e0677b664c42` | california / 2021-08-01 | 81 | 0 | 29/14 | 29/14 | 13/13 | resource_limit | sì/sì | 3669/4170 | VI candidata | 42.480 |
| `global-c7ee1b9b32c94d91d766449a656285b6` | california / 2021-08-01 | 4 | 0 | 33/16 | 33/16 | 15/15 | HLS_L30 | sì/sì | 244/246 | VI candidata | 57.870 |
| `global-ae03e27d2d3aa866064ac98758faefa8` | california / 2021-08-01 | 51 | 348 | 28/13 | 28/13 | 13/13 | not_needed | sì/sì | 1132/1392 | BA + VI | 31.150 |
| `global-6c75f44c7f2e9a434486e8107a60adb2` | greece / 2023-07-20 | 85 | 388 | 42/22 | 42/22 | 22/22 | not_needed | sì/sì | 1396/1552 | BA + VI | 25.650 |
| `global-05eef89441827b78e719e46b3f40b50e` | greece / 2023-07-20 | 4 | 22 | 44/22 | 44/22 | 22/22 | not_needed | sì/sì | 88/88 | BA + VI | 22.890 |
| `global-62ee07984b5efdae659f0c6833ffba02` | greece / 2023-07-20 | 3 | 9 | 36/15 | 36/15 | 14/14 | not_needed | sì/sì | 36/36 | BA + VI | 23.550 |
| `global-febdc594c5df5e2bf5dfec7d81928ae0` | indonesia / 2019-09-15 | 37 | 109 | 13/4 | 13/4 | 3/3 | not_needed | sì/sì | 164/436 | BA + VI | 26.390 |
| `global-0c2dc52b8a01d3a7e95094d034bb6a83` | indonesia / 2019-09-16 | 4 | 45 | 7/0 | 7/0 | 0/0 | HLS_L30 | no/no | 0/180 | VI candidata | 38.210 |
| `global-d56dcf74acebb75218956e8968fd287b` | indonesia / 2019-09-15 | 20 | 68 | 2/1 | 2/1 | 0/0 | not_needed | no/no | 0/272 | BA + VI | 24.480 |
| `global-f0b63a3b789d0bce4d37114895897a41` | indonesia / 2019-09-15 | 3 | 25 | 8/2 | 8/2 | 0/0 | not_needed | no/no | 0/100 | BA + VI | 34.860 |
| `global-651546575cc3b6de39a347934a39b86d` | indonesia / 2019-09-15 | 18 | 120 | 16/5 | 16/5 | 4/4 | not_needed | sì/sì | 472/480 | BA + VI | 31.690 |
| `global-3243956ef2081a9309a7816b972b1d84` | india / 2024-04-12 | 3 | 71 | 20/7 | 20/7 | 5/5 | not_needed | sì/sì | 248/284 | BA + VI | 35.640 |
| `global-b084df31bd082c102aa46f75500039df` | alaska / 2022-06-25 | 31 | 13 | 14/9 | 14/9 | 8/8 | not_needed | sì/sì | 52/52 | BA + VI | 35.310 |
| `global-a16ee17f6317e3ea1a3fad05fe319246` | alaska / 2022-06-25 | 127 | 364 | 14/3 | 14/3 | 3/3 | not_needed | sì/sì | 1004/1456 | BA + VI | 39.430 |
| `global-c8c510abed54e5586d3251499b603334` | alaska / 2022-06-25 | 26 | 506 | 17/8 | 17/8 | 8/8 | not_needed | sì/sì | 2024/2024 | BA + VI | 39.730 |
| `global-c4cb538b3d82199edf1c7dcf6d26c824` | alaska / 2022-06-25 | 25 | 132 | 0/0 | 0/0 | 0/0 | partial_vegetation_observations | no/no | 124/528 | Limitata | 56.130 |
| `global-1019de824d50e36fab75e0f0e6b4e3df` | alaska / 2022-06-25 | 57 | 114 | 17/6 | 17/6 | 6/6 | not_needed | sì/sì | 456/456 | BA + VI | 41.220 |
| `global-7ead7debdedf61ac872d0b7259ef9c4b` | zambia_supplement / 2022-08-16 | 3 | 0 | 26/13 | 26/13 | 10/10 | HLS_S30 | sì/sì | 162/162 | VI candidata | 36.870 |
| `global-8ae345b003214a6997149edf8cb48929` | zambia_supplement / 2022-08-16 | 4 | 25 | 25/13 | 25/13 | 9/9 | not_needed | sì/sì | 100/100 | BA + VI | 26.750 |
| `global-42e4ea7aff90536deb96d88362ca5b14` | zambia_supplement / 2022-08-15 | 3 | 7 | 22/11 | 22/11 | 8/8 | not_needed | sì/sì | 28/28 | BA + VI | 28.770 |
| `global-c668d3d84858a7514b928bd17bd2d59b` | zambia_supplement / 2022-08-15 | 5 | 52 | 26/9 | 26/9 | 8/8 | not_needed | sì/sì | 208/208 | BA + VI | 29.370 |
| `global-36b964695d5e97ccc0b3de58842798fb` | zambia_supplement / 2022-08-16 | 3 | 0 | 27/13 | 27/13 | 9/9 | Sentinel_2 | sì/sì | 137/137 | VI candidata | 59.940 |
| `global-b252eeaaa9bbcac23453e85678427701` | brazil_supplement / 2024-08-20 | 60 | 117 | 25/8 | 25/8 | 8/8 | not_needed | sì/sì | 468/468 | BA + VI | 22.970 |
| `global-28556be7c339e95f273a62e728c9f33a` | brazil_supplement / 2024-08-21 | 38 | 59 | 28/7 | 28/7 | 7/7 | not_needed | sì/sì | 236/236 | BA + VI | 22.850 |
| `global-22937829c0cc24d0f67f7152b0339a33` | brazil_supplement / 2024-08-21 | 39 | 70 | 25/10 | 25/10 | 7/7 | not_needed | sì/sì | 280/280 | BA + VI | 29.310 |
| `global-236132ce9280db59ca82d5c98e249887` | brazil_supplement / 2024-08-21 | 3 | 0 | 0/0 | 0/0 | 0/0 | Sentinel_2 | no/no | 1/108 | VI candidata | 55.440 |
| `global-3e96de345373a7fa1ede2ade992745b4` | brazil_supplement / 2024-08-21 | 6 | 29 | 28/8 | 28/8 | 7/7 | not_needed | sì/sì | 116/116 | BA + VI | 23.410 |

## Riproduzione

Richiede il runtime backend configurato, accesso NASA già autorizzato e le sorgenti/cache originali per i replay indipendenti. Nessuna credenziale è inclusa negli artefatti. Gli script salvano incrementalmente in `/tmp`, senza eliminare casi falliti:

1. Eseguire prima `complete_scientific_campaign.py --select-only` per entrambi i manifesti, usando `--supplement --output /tmp/complete-scientific-supplement` per le finestre aggiuntive. Poi eseguire `--register-only` su entrambi prima di avviare `--phase baseline`: in questo modo anche un campione distribuito su più manifesti ha tutto il contesto registrato prima delle analisi. Non cancellare il manifesto per cercare un campione migliore.
2. `enrich_scientific_campaign.py --watch` verifica serie e celle conservate; ripetere con il path del supplemento.
3. Dopo l’attivazione della versione nuova, eseguire `--phase after` sui medesimi manifesti; il comparatore `compare_complete_scientific_audit.py` confronta i campi scientifici effettivi.
4. `verify_recovery_independent.py` verifica le pubblicazioni trattenute, inclusi raw QA, baseline e Reburn. `audit_publications.py` acquisisce fingerprint/ispezione; conservare il primo fingerprint prima dell’upgrade.
5. `verify_tunisia_native.py` confronta HLS grezzo con dNBR; `verify_published_tunisia_assets.py` scarica i due asset API e confronta tutte le bande conservate con gli originali. I file snapshot richiesti sono prodotti dalla prima ispezione; non sono sostituiti con fixture sintetiche.
6. `verify_isolated_worker_restart.py` va eseguito soltanto in container temporanei `--network none`, con database/cache esattamente `/tmp/audit-state/test.db` e `/tmp/audit-state/cache`; lo script rifiuta altre configurazioni. Terminare il container soltanto dopo il marker READY, poi riavviare lo stesso container.
7. Test completi: dal backend `PYTHONPATH=.:../scripts python -m pytest app/tests -q`; per PostgreSQL impostare `AF_TEST_DATABASE_URL` esclusivamente su un database `afterfire_test_*`. Le fixture reindirizzano database e cache. Frontend: `npm run build`. Secret scan: `python scripts/check_secrets.py --all`; prima del commit/push anche scansione dello staging.
8. Copiare soltanto i metadati autorizzati da `/tmp` nel report; `summarize_complete_scientific_audit.py` ricostruisce summary, CSV e tabella. File DB, cache e raster non si aggiungono a Git.
