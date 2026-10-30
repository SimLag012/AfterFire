# Gestione della cache satellitare

[Preflight](ASYNC_PREFLIGHT.md), [pipeline](SATELLITE_DATA_PIPELINE.md), [verifica](PHASE5_VERIFICATION.md).

`cache_management.inventory` interroga il filesystem della sola directory satellitare. Riporta byte dei file, byte allocati, volume totale/usato/libero, quota e classi sources, subsets, results, processed, temporary, metadata e quarantine. Inode `(device,inode)` condivisi vengono contati una volta; symlink non vengono seguiti. Volume del catalogo, dimensione locale e traffico di rete restano quantità separate.

## Policy

La pulizia viene valutata prima delle nuove acquisizioni, mai automaticamente all’avvio Docker. Default: attivata, soglia 85% della quota, obiettivo 70%, riserva libera esistente 1 GiB. Si conservano i limiti esistenti: rete/job 5 GiB, blocco e temporanei 1 GiB, risultati 2 GiB, cache 10 GiB. Fonte di verità: Settings e relative variabili Compose, senza duplicare le quote.

Il cleanup acquisisce il lock esclusivo **non bloccante** `usage.lock` e il lock quota. Tutti i piani/verificatori scientifici e le pipeline attive mantengono un lease condiviso. Se esiste un lettore/scrittore scientifico, la pulizia non rimuove niente. Il controllo è cross-process, non un flag in memoria. Prima di cancellare si ricontrollano inode e generazione del file.

Sono sempre protetti risultati pubblicati, GeoTIFF/PNG derivati, manifest/JSON di provenienza, lock e `.part` ancora potenzialmente in scrittura. I file con più hardlink vengono protetti. Le sorgenti HDF restano protette con `AFTERFIRE_ANALYSIS_KEEP_SOURCE_GRANULES=true` oppure policy `retain` (default esistenti). Per consentirne l’evizione servono entrambi retention disattivata e policy `lru_sources`. I candidati sostituibili sono subset TIFF completi, checkpoint NPZ, sorgenti quando esplicitamente consentite e file satellitari in quarantena. Selezione per ultimo accesso disponibile nel filesystem. I temporanei senza lease attivo diventano candidati dopo 24 ore; quelli recenti rimangono protetti. Gli asset pubblicati non più referenziati e le pubblicazioni equivalenti vengono segnalati dalla diagnostica amministrativa, ma restano conservati in assenza di una strategia esplicita di rigenerazione.

I manifest restano conservati dopo l’evizione di una sorgente. Le verifiche di esistenza/checksum trasformano la futura acquisizione in cache miss; non si dichiara un file disponibile soltanto perché un vecchio manifest dice complete. Gli asset pubblicati rimangono consultabili anche se una sorgente deve essere riscaricata per una rielaborazione.

## Dry-run e amministrazione

Dalla root, con Python e dipendenze backend:

```bash
PYTHONPATH=backend backend/.venv/bin/python scripts/satellite_cache_admin.py
PYTHONPATH=backend backend/.venv/bin/python scripts/satellite_cache_admin.py --apply
```

Il default è dry-run: candidati, ragioni, byte recuperabili, file protetti, uso stimato dopo la pulizia. `--apply` registra audit persistente con byte logici rimossi, byte allocati recuperati e variazione effettiva dello spazio libero. Se i file protetti impediscono l’obiettivo viene restituito un warning; non si elimina comunque un risultato.

`GET /api/v1/admin/satellite-cache` è disponibile soltanto con `Authorization: Bearer …` e `AFTERFIRE_ADMIN_TOKEN` configurato. Default disabilitato (403). La diagnostica nella pagina Datasets richiede quel token, conservato soltanto nella memoria del componente. Non esiste un endpoint pubblico di cancellazione. I percorsi assoluti non vengono restituiti.

Il database FIRMS è esterno alla directory satellitare: né il cleanup né il dry-run lo attraversano. I test distruttivi operano esclusivamente in directory temporanee.

## Limiti espliciti

Una singola analisi attiva protegge conservativamente tutta la cache scientifica. Se esaurisce la quota durante una scrittura, fallisce in modo controllato: non si forza l’evizione sotto un lettore. Il cleanup non garantisce spazio sufficiente se i file protetti occupano la quota. Ultimo accesso dipende anche dalla policy atime del filesystem; non è una frequenza di riuso statisticamente stimata. Non è previsto un servizio cron separato: il trigger è prima dell’acquisizione o dal comando amministrativo.

Per un host con venv non eseguibile o dipendenze HDF mancanti, usare l’immagine canonica: `docker compose run --rm --no-deps -e PYTHONPATH=/app -v "$PWD/scripts:/scripts:ro" backend python /scripts/satellite_cache_admin.py`. Il default resta dry-run.


## Phase 6 — Reburn & Recovery Gap

The existing implementation is extended by [Reburn Intelligence](REBURN_INTELLIGENCE.md), [observed episode methodology](REBURN_DETECTION_METHODOLOGY.md), [shared-area Recovery Gap](RECOVERY_GAP.md) and [cumulative vegetation](CUMULATIVE_VEGETATION.md). See [measured infrastructure changes](PERFORMANCE_OPTIMIZATION.md) and [verification and limitations](PHASE6_VERIFICATION.md). Previous-phase publications and reports are preserved.
