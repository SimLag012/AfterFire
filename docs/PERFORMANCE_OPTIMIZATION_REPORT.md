# AfterFire — ottimizzazione delle prestazioni

Misure di novembre 2026. Base Git: `1b582dca58b9cea6a56ffc68a07bce3f4246cf4b`.

## Ambito e metodo

Intervento su accounting della cache, persistenza dei checkpoint e contesto riproducibile delle pubblicazioni. Nessuna modifica alle formule, QA, griglie, soglie, baseline, attribuzione delle celle, metodologia ottica, Recovery Intelligence o Reburn. Nessuna modifica al frontend. Il worker predefinito resta uno.

Tutte le prove distruttive usano database e cache temporanei in container dedicati. I dati operativi sono stati letti per esportare input e misurare la latenza delle pubblicazioni; nessun database/cache operativo è stato cancellato, migrato o sottoposto a fault injection. Le modifiche e gli audit locali preesistenti non sono inclusi automaticamente nel commit.

Gli input sono congelati prima dei confronti: cataloghi realmente acquisiti, rilevamenti FIRMS, candidati concorrenti, configurazione, geometrie, provenienza e risposta ottica salvata. `performance/benchmark-context.json` conserva identità, checksum e contesto; lo snapshot completo rimane privato in `/tmp`. Il replay non esegue discovery live e sostituisce la risposta ottica con quella pubblicata: isola il costo locale, non misura una nuova acquisizione HLS. Il download MODIS viene proibito nei replay offline, e viene verificato `diagnostics.acquisition_failures == 0`.

Le distribuzioni di otto eventi sono campioni descrittivi, non stime affidabili del p95 di tutti gli incendi. I tempi di rete e le differenze di disponibilità dei provider non vengono attribuiti al codice. I primi esperimenti con un job sintetico senza `owner` erano incompleti e sono stati scartati prima della validazione: tutti i risultati finali devono passare anche il controllo sui granuli.

## Profiling iniziale

La baseline storica di 97,19 s di pipeline e 153,50 s request-to-result non viene usata come denominatore. Il codice corrente è stato profilato nuovamente.

- Cache operativa: 124.154 file fisici, 202.596.261 byte, con hardlink contati una volta. I blocchi allocati occupano 401.715.200 byte. L’inventario finale in sola lettura conferma lo stesso numero di file e byte (`performance/cache-volume.json`).
- Inventario completo: 10,631 s. Conteggio byte via `scandir`: 0,886 s.
- Import di `app.main` in runtime isolato: 1,363 s; non comprende l'inizializzazione della connessione DB o il preflight live. Misura completa su schema PostgreSQL vuoto isolato: import 1,021 s, lifespan (schema + seed metadati, demo disabilitata) 0,854 s, totale 1,876 s (`performance/startup.json`).
- `prune_sources()` eseguiva l'inventario anche sotto soglia; il piano ripeteva un conteggio completo.
- Ogni nuovo checkpoint chiamava `ensure_space()`, che ripercorreva l'intera cache sotto `quota.lock`. I download ripetevano anche la scansione dei `.part` per ogni blocco.
- Il salvataggio comprimeva e calcolava il checksum rileggendo il file, mantenendo il lock di quota per tutta l'operazione.
- La lettura di una pubblicazione era già veloce; non è stato introdotto un indice DB senza evidenza di necessità.

Dati: `performance/cache-profile-before.json`. I profili granulari dei replay registrano fasi, CPU del thread, lock, chiamate e durata di letture, checkpoint, raster e accounting. Le durate possono sovrapporsi: non vanno sommate indiscriminatamente.

## Cache prima e dopo

Prima: file scientifici, manifest ed evidenze di integrità separati; conteggio ripetuto del filesystem prima di ammettere una scrittura.

Dopo: gli stessi oggetti scientifici restano nella stessa struttura. Un indice SQLite ricostruibile, accanto alla directory satellite, conserva percorsi, inode, dimensioni e totali persistenti. I contatori sono transazionali, mai semplici contatori RAM. Le connessioni SQLite, al massimo otto per thread I/O, possono essere riutilizzate; i valori della quota vengono comunque letti dal DB.

Protocollo:

1. Acquisire il `quota.lock` condiviso fra processi e leggere i totali persistenti.
2. Verificare limite globale, spazio libero e sottolimiti applicabili, con un limite superiore conservativo sui byte in arrivo.
3. Committare `dirty=1` con WAL e `synchronous=FULL`, prima di mutare il filesystem.
4. Eseguire la scrittura atomica e sincronizzare le directory interessate.
5. Riconciliare solo i percorsi del bundle, calcolare il delta per inode, aggiornare i totali e committare `dirty=0`.

Un SIGKILL lascia l'indice sporco: il lettore successivo ricostruisce l'inventario sotto lock prima di consentire altre scritture. Un indice assente/corrotto, un puntatore di generazione mancante/corrotto o una directory cache sostituita viene ricostruito; la corruzione riconosciuta da SQLite viene conservata a parte. Un piccolo puntatore atomico seleziona la generazione attiva: un indice WAL aperto non viene rinominato o eliminato. Le connessioni vecchie possono chiudersi e sincronizzare soltanto i propri file, senza toccare i sidecar della generazione sostitutiva. Sono testate anche pagine dati corrotte con schema ancora leggibile e una connessione aperta in un altro processo. Gli errori I/O non sono convertiti in una quota vuota. Gli hardlink contano una volta nel totale globale e una volta nel sottolimite risultati quando un riferimento appartiene a `results/`.

Il controllo ordinario dello spazio non percorre più tutti i file. L'inventario completo rimane disponibile per amministrazione ed eviction realmente necessaria. Il lease `usage.lock` continua a impedire l'eliminazione dei file usati dalle analisi. Le pubblicazioni, i metadati e le sorgenti protette dalla configurazione conservano la politica precedente. L'eviction rimane possibile anche se la quota è già superata; il suo audit amministrativo vive accanto alla cache, per essere salvabile in questa condizione.

L'indice e i suoi sidecar WAL sono overhead amministrativo esterno al limite dei file scientifici satellite; lo spazio libero del volume li comprende. Dimensioni e limiti operativi sono riportati separatamente, senza presentarli come storage gratuito. L'indice non sostituisce checksum e validazione scientifica delle sorgenti. Se la quota impedisce di salvare una nuova evidenza di integrità opzionale, una sorgente i cui byte e validatore sono appena stati verificati resta un cache hit: non viene quarantinata o riacquisita per questo motivo. La verifica completa viene ripetuta al prossimo uso se non è stato possibile memorizzare l'evidenza.

Nel profilo source-warm, `prune_sources` passa da una mediana di 16,360 s a 0,000909 s. Le letture/checksum dei checkpoint restano circa 0,14 s cumulati per evento. La persistenza degli asset differiti aumenta invece da circa 0,829 s a 2,823 s mediani: ora comprende accounting e durabilità prima assenti. Il miglioramento complessivo non nasconde questo costo.

L'indice attivo misurato occupa 39.714.816 byte (37,88 MiB), oltre al piccolo puntatore. WAL e SHM possono aumentare temporaneamente l'overhead durante la ricostruzione. Le generazioni precedenti conservate durante gli esperimenti non sono storage scientifico nuovo; `accounting-storage.json` separa indice attivo e vecchi indici. La cattura iniziale di overhead includeva anche WAL e generazione sperimentale precedente. Non viene implementata una cancellazione automatica degli indici storici, per non interferire con connessioni ancora aperte.

## Checkpoint prima e dopo

Restano NPZ compressi, con la stessa identità scientifica `modis-recovery-3.0.0`, gli stessi array, trasformazioni, totale pixel e provenienza. Gli oggetti immutabili validi continuano a essere riutilizzati. Nessuna conversione di dtype, arrotondamento, perdita di QA o modifica della selezione delle celle.

La compressione e il checksum vengono calcolati una volta in memoria, fuori dal lock globale; sotto lock si pubblicano solo byte già serializzati e sidecar. `fsync` dei dati, checksum, rename atomico e sincronizzazione delle directory sono mantenuti. I riferimenti pubblicati continuano a essere hardlink ai dati immutabili. Hardlink e manifest di un asset differito vengono contabilizzati nella stessa mutazione, evitando due transazioni separate per asset.

Il picco aggiuntivo è un buffer compresso per checkpoint: le acquisizioni restano limitate per AOI/pixel e non vengono scaricate scene complete. Un checkpoint corrotto viene rifiutato e rigenerato dalle sorgenti valide. Non vengono cancellati dati pubblicati durante la riparazione.

## Riproducibilità

Ogni nuova pubblicazione contiene `attribution_context` con schema/versione, rilevamenti del target, footprint, geometria del target, punti/date/geometrie dei candidati concorrenti nell'ordine effettivamente usato, regole e parametri di attribuzione, versione del motore e SHA-256 del contesto. Configurazione, sorgenti, checksum e provenienza continuano a far parte del payload.

La metodologia e l'ordine di attribuzione non vengono cambiati. Il contesto descrive quella specifica esecuzione: un retry con candidati diversi produrrà un contesto diverso e tracciabile. Le pubblicazioni precedenti non sono retroattivamente arricchite. Non viene promessa una ricostruzione del contesto storico che non era stato registrato. La selezione di una pubblicazione già esistente mantiene l'idempotenza precedente.

## Benchmark e risultati

Confronto finale sequenziale, senza altri benchmark concorrenti: otto esecuzioni per versione, una per evento. Quantili con interpolazione lineare, senza eliminare outlier.

| Metrica source-warm con checkpoint | Prima | Dopo |
|---|---:|---:|
| Pipeline p50 | 19,227 s | 3,484 s |
| Pipeline p95 campionario | 21,446 s | 6,767 s |
| CPU per job p50 | 18,942 s | 2,109 s |
| CPU per job p95 | 21,163 s | 4,570 s |
| RSS massimo del processo | 555,24 MiB | 182,70 MiB |
| Byte NASA acquisiti | 0 | 0 |
| Risultati scientifici/array identici | 8/8 | 8/8 |

Il RSS è un high-water mark del processo, non una misura istantanea per evento. Una serie precedente di 16 esecuzioni ottimizzate ha registrato p50 3,691 s e p95 7,505 s. Baseline e variante partono da due copie della medesima cache, con hardlink preservati. La creazione iniziale dell'indice (11,571 s) è misurata separatamente e non è compresa nella tabella warm. I dati comprendono anche i picchi di latenza non eliminati.

Con sorgenti disponibili ma tutti i checkpoint da creare, l'evento piccolo passa da 66,849 s a 7,721 s complessivi. I checksum scientifici e degli array sono identici. Per 68 salvataggi, il tempo cumulato dentro `save_checkpoint` scende da 45,480 s a 1,327 s (CPU da 44,706 s a 0,504 s). Non coincide con l'intera pipeline.

Otto pubblicazioni già salvate: 24 letture API, p50 0,049 s, p95 0,219 s e massimo 0,284 s. Un controllo ripetuto sul solo evento piccolo, letto tramite l'API operativa in sola lettura: 30 richieste, p50 circa 0,035 s e massimo 0,097 s per circa 231 kB. La lettura era già veloce; non è un miglioramento introdotto da questo commit.

Dati dettagliati: `performance/baseline-final.json`, `performance/delivery-sourcewarm.json`, `performance/optimized-final.json`, `performance/baseline-create-checkpoints.json`, `performance/optimized-create-checkpoints.json` e `performance/publication-warm.json`. I replay source-warm hanno sorgenti locali e database di prova senza pubblicazioni. I file di vecchi risultati restano nella copia della cache per riprodurne il carico di filesystem, ma non vengono consultati come pubblicazioni del database di prova.

Campione: evento piccolo HLS S30 (5,50 km²), medio (20,05 km²), grande California (609,46 km² e 1.911 celle), costa Tunisia (10,37 km²), Sardegna (15,56 km²), Grecia (194,65 km²), Australia (47,29 km²), evento a due tile (173,75 km²). Tutti derivano dal campione scientifico reale già conservato.

### Acquisizione cold

Cache di raster e checkpoint vuota all’inizio di ogni serie. Gli otto eventi sono stati eseguiti nello stesso ordine con cataloghi e contesto congelati. I metadati di griglia possono essere riusati fra eventi, anche fra Tunisia e Sardegna. Le acquisizioni native e il fallback ottico HLS del primo evento usano il provider live.

| Evento | Prima (s) | Dopo, primo tentativo (s) |
|---|---:|---:|
| Piccolo HLS | 44,62 | 54,82 |
| Medio | 40,57 | 37,77 |
| California | 366,99 | 603,76 (timeout) |
| Tunisia | 22,57 | 24,27 |
| Sardegna | 26,00 | 22,60 |
| Grecia | 201,05 | 192,19 |
| Australia | 70,24 | 63,51 |
| Due tile | 243,35 | 240,36 |

Al primo tentativo sono arrivati a risultato 8/8 eventi prima e 7/8 dopo. Includendo il timeout, la latenza dei tentativi passa da 57,43 a 59,16 s al p50 e da 323,72 a 476,57 s al p95. Questi numeri descrivono i tentativi, compreso quello fallito. Il campione non dimostra un miglioramento cold.

In California il provider ha impiegato 9,57 s per il burned area e 245,39 e 347,05 s per due gruppi di 32 date VI. Al gruppo successivo il budget era esaurito. La ripresa separata sulla stessa cache parziale ha completato il calcolo in 67,72 s e ha acquisito soltanto gli ultimi 1.354.752 byte. I 22.107.232 byte precedenti sono stati riusati. Entrambe le serie, includendo la ripresa, hanno decodificato 50.936.412 byte. I contatori misurano il budget SDK esplicito e i byte decodificati. Traffico sul filo e retry interni dell’SDK restano non osservati. Fonte: `all-cold-*.json`, `cold-provider-failure.json` e `resume-after-provider-timeout.json` nella directory dei dati.

Tutti gli otto risultati completati corrispondono ai checksum scientifici e agli array di riferimento. Nel caso HLS live il confronto esclude dalla risposta ottica durata, contatori di richieste e cache e dimensioni di risposta. I precedenti esperimenti `live-cold-*.json` congelavano la risposta ottica e sono conservati separatamente.

## Worker e database

Il benchmark dedicato usa davvero `claim_job`, fencing/ownership, heartbeat, progressi, upsert dei granuli e pubblicazione transazionale in PostgreSQL/PostGIS isolato. Soltanto catalogo/provider e contesto degli eventi sono congelati. Il tempo request-to-result del benchmark della coda parte dopo l'inserimento del batch di job: esclude il POST HTTP iniziale, il controllo live di disponibilità e il polling/frontend. I tempi di lettura HTTP pubblicata sono misurati separatamente. Una e due lane vengono confrontate sugli stessi input; non si aumenta il default senza evidenza stabile anche sul provider live.

| Otto job source-warm su PostgreSQL | Un worker | Due worker |
|---|---:|---:|
| Intero batch | 58,47 s | 44,93 s |
| Job completati/min | 8,21 | 10,68 |
| Dalla fine dell’accodamento alla pubblicazione p50 / p95 | 30,89 / 53,75 s | 26,01 / 42,09 s |
| Attesa in coda p50 / p95 | 26,95 / 42,81 s | 15,90 / 31,07 s |
| Singola pipeline p50 / p95 | 5,92 / 12,59 s | 10,31 / 12,51 s |
| RSS massimo processo | 196,21 MiB | 225,19 MiB |
| Query / commit | 7.908 / 2.619 | 7.909 / 2.619 |
| Tempo cumulato query / commit | 3,74 / 12,96 s | 6,10 / 14,51 s |

Entrambi i batch hanno pubblicato otto risultati scientificamente identici al primo tentativo. Due worker riducono l’attesa in coda e aumentano la mediana della singola pipeline e il consumo di memoria. Il default rimane uno. La frequenza dei commit di avanzamento rimane un costo misurabile. Non è stata misurata la concorrenza live di due worker su Earth Engine.

I piani `EXPLAIN (ANALYZE, BUFFERS)` sono conservati nei dati grezzi. La query della coda sul piccolo database di prova è nell'ordine dei centesimi di millisecondo. Un sequential scan su sette/otto righe non giustifica nuovi indici né dimostra le prestazioni su un archivio grande. Sui dati operativi reali, in sola lettura, caricamento evento + geometria + query candidati richiedono mediana 0,023 s e massimo 0,128 s. La sola query dei candidati: mediana 0,010 s e massimo 0,043 s inclusi ORM/connessione; EXPLAIN ANALYZE riporta 0,100–0,234 ms per gli otto casi. I piani sono in `performance/database-profile.json`: nessuna evidenza per aggiungere indici. Non sono state modificate transazioni di pubblicazione, indici PostGIS o regole di lease.

## Regressioni e fault injection

- 245 test SQLite e 245 PostgreSQL/PostGIS passati in runtime isolati.
- Build TypeScript/Vite completata, senza modifiche al frontend.
- Concorrenza fra processi: due writer da 60 byte sotto una quota dati di 100 byte ammettono uno solo dei writer; un lettore con connessione già aperta vede il commit dell'altro processo.
- SIGKILL durante una mutazione: ricostruzione prima della successiva ammissione; i byte parziali sono conteggiati.
- Indice corrotto e directory sostituita: accounting ricostruito senza perdere sorgenti.
- Eccezione durante una scrittura, cache incompleta, checkpoint corrotto, sottolimiti temporanei/risultati, hardlink, symlink e rimozioni verificati.
- Suite esistenti: ownership/lease scaduti, ripartenza, richieste simultanee/idempotenza, 429/5xx, errori del provider, indisponibilità DB durante la pubblicazione, rollback senza perdere la pubblicazione precedente, lease contro eviction e cancellazione dei task I/O.
- Scientifici indipendenti: QA, griglie native, mediana/baseline/anomalie, recupero, Reburn e fixture NASA reale Tunisia.

Un worker è stato inoltre realmente terminato con SIGKILL al 50% e riavviato: lease reclamato con nuovo owner, secondo tentativo, checkpoint riusato, zero nuove richieste di sorgenti, pubblicazione atomica e zero ghost job (`performance/worker-sigkill-restart.json`).

Gli errori DB/provider sono iniettati nelle suite controllate: non è stato arrestato il database operativo. Le prove SIGKILL sull'indice e quelle del worker sono distinte e non vengono presentate come interruzioni di un'acquisizione NASA operativa.

## Identità scientifica

Per ciascun evento si confrontano strutture scientifiche e SHA-256 degli array nativi, dtype, shape, trasformazione e numero di pixel. Il confronto separa nomi degli asset, identificativo job, tempo, cache hit e telemetria. La configurazione, geometria, celle e associazioni, QA aggregata, NDVI/EVI, baseline/MAD/anomalie, supporto, ricorrenza e intera evidenza ottica salvata restano nel confronto strutturato.

Le due verifiche offline hanno ricalcolato recupero areale e spaziale per tutti gli otto eventi, con hash identici delle valutazioni, dei raster nativi (incluse le bande QA), dei file TIFF e dei conteggi per cella. Su 16.024 serie cella/indice, la verifica indipendente ha controllato 1.766 baseline supportate per versione e confrontato trend e persistenza. I confronti escludono il riferimento al job generatore. I dati sono in `performance/recovery-before.json` e `performance/recovery-after.json`. Reburn e Recovery Gap restano coperti dalle suite esistenti. Non è stata eseguita una nuova campagna live dedicata a queste due metodologie.

### Ripetere il confronto

Nel runtime backend impostare `PYTHONPATH=backend`. Esportare con un account DB di sola lettura. Per ogni variante preparare una copia privata della cache con hardlink preservati sotto `/tmp`, impostare `AFTERFIRE_ANALYSIS_CACHE_DIR` su quella copia e `DATABASE_URL` su un database SQLite temporaneo distinto (`sqlite+aiosqlite:////tmp/...`). Usare lo stesso snapshot privato ed eseguire la baseline con il codice applicativo del commit iniziale. I driver di misura vengono dalla versione di questo rapporto.

```sh
python scripts/export_performance_snapshot.py --audit "$AUDIT_JSON" --output /tmp/snapshot.json
python scripts/benchmark_performance_replay.py --snapshot /tmp/snapshot.json --label before --output /tmp/before.json
python scripts/verify_performance_identity.py --snapshot /tmp/snapshot.json --label before --output /tmp/check-before.json
python scripts/benchmark_performance_replay.py --snapshot /tmp/snapshot.json --label after --output /tmp/after.json
python scripts/verify_performance_identity.py --snapshot /tmp/snapshot.json --label after --expected /tmp/check-before.json --output /tmp/check-after.json
python scripts/summarize_performance.py --root docs/performance
```

Cambiare versione applicativa e cache prima di eseguire la seconda coppia di comandi. Per il cold partire da una cache vuota, configurare il provider e aggiungere `--live --live-optical`. Per misurare la ripresa usare la stessa cache parziale e selezionare `--event ID` con un’etichetta distinta. Per la coda configurare un nuovo PostgreSQL/PostGIS di prova con nome `afterfire_test_...` per ciascuna prova ed eseguire `python scripts/benchmark_performance_workers.py --snapshot /tmp/snapshot.json --lanes 1 --output /tmp/worker1.json`, poi ripetere con due lane su un secondo DB vuoto. I log JSON conservano anche fasi sovrapposte e tentativi falliti. La correzione finale di ammissione riserva spazio anche per la geometria serializzata dei metadati nativi, con regressione su un poligono di 20.000 vertici.

## Esercizio e rollback

I container operativi non sono stati aggiornati durante il benchmark. Prima di adottare il nuovo accounting, fermare tutti i writer della vecchia versione, senza eliminare cache o database. Vecchi e nuovi writer non devono condividere la stessa directory: il codice vecchio non aggiorna l'indice. Con la nuova versione, eseguire una riconciliazione amministrativa (`PYTHONPATH=backend python scripts/satellite_cache_admin.py --rebuild-index`) e poi avviare API/worker.

Dopo import, ripristino o modifica manuale dei file, fermare i writer e ricostruire l'indice. Non considerare l'indice una promessa di rilevamento immediato di qualsiasi modifica esterna arbitraria al filesystem. Tutti i writer dell'applicazione satellite sono integrati nel protocollo. Storage NFS/distribuito non è validato per questi `flock`/WAL; la prova riguarda volumi locali condivisi sullo stesso host.

Rollback: fermare i writer nuovi e ripristinare il codice precedente; i formati delle sorgenti e dei checkpoint sono compatibili. L'indice amministrativo può restare conservato. Prima di riadottare la nuova versione, ricostruirlo se writer vecchi o strumenti esterni hanno modificato la cache. Nessun force push né riscrittura della cronologia.

## Scelte scartate e limiti

- Packing/CAS/compressione delle sorgenti: non introdotti senza un vantaggio dimostrato ulteriore rispetto all'eliminazione delle scansioni; aumenterebbero il rischio di migrazione dei dati conservati.
- Indice con journal rollback e molte transazioni piccole: la contesa `fsync` peggiorava alcune latenze; variante scartata. Il confronto dei journal e i risultati respinti sono conservati separatamente.
- Contatori solamente RAM: esclusi per sicurezza fra processi e dopo crash.
- Aumento indiscriminato dei worker o parallelismo EE: nessuna modifica delle quote/budget e nessun default aumentato sulla base di un replay offline.
- Nessun indice DB o riscrittura scientifica speculativa.
- L'indicizzazione iniziale e quella successiva a un crash hanno ancora un costo proporzionale ai file; il costo è eccezionale e documentato, non nascosto nelle latenze warm.
- La rete, Earth Engine e i cataloghi restano fonti di variabilità. Il target cold di 30–60 s non è una garanzia.
- La numerosità limitata e le fixture ottiche congelate non dimostrano il p95 di una dimostrazione live completa né una campagna cold di tutti i 56 incendi.
