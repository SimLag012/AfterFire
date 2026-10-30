# Analisi spaziale del recupero

La Recovery Anomaly Map usa i GeoTIFF scientifici pubblicati dalla pipeline NASA esistente. Non usa il valore medio dell’evento come baseline di ogni pixel. [Metodologia](RECOVERY_ASSESSMENT_METHODOLOGY.md), [API](RECOVERY_INTELLIGENCE.md), [evidenze](PHASE5_VERIFICATION.md).

## Griglia e QA

Le sorgenti sono i raster NDVI/EVI già calibrati e mascherati con QA. Vengono controllati CRS sinusoidale MODIS, assenza di rotazione, dimensione del pixel e offset intero sulla tile. Una griglia spostata o riproiettata viene rifiutata, non ricampionata. Le coordinate globali `(tile_v×4800+riga, tile_h×4800+colonna)` uniscono finestre HDF/AppEEARS con inviluppi diversi e supportano adiacenze fra tile.

Ogni cella è selezionata dal centro dentro la geometria scientifica dell’analisi. La dimensione reale è circa **231,656 m** (prodotto nominale 250 m); area nativa circa 0,053665 km². Il poligono visualizzato è l’impronta della cella, non un confine a scala catastale. I pixel misti e il compositing restano limiti fondamentali. Le celle MCD64A1 hanno invece risoluzione nominale 500 m.

## Baseline per pixel

Le matrici data×cella vengono allineate senza interpolazione. Le date stagionali e gli indici dei riferimenti sono preparati una sola volta; mediane, MAD, numero di riferimenti e anni validi sono calcolati vettorialmente, con esclusione dei nodata separata per pixel. Il test di equivalenza verifica gli stessi risultati della funzione scalare. Ogni cella applica poi gli indicatori temporali della [metodologia](RECOVERY_ASSESSMENT_METHODOLOGY.md).

Una cella senza riferimenti sufficienti è `insufficient_data`; non riceve valori dai vicini. I risultati contengono la serie osservata e il supporto per ogni cella; l’API pubblica della mappa restituisce soltanto il composito selezionato e i riepiloghi. La serie completa di una singola cella è consultabile tramite l’endpoint dedicato.

## Layer

- **Seasonal anomaly:** osservato − baseline per pixel alla data condivisa con Recovery Story; scala fissa −0,05/+0,05 per distinguere caldo/neutro/freddo, senza attribuire significatività statistica al colore.
- **Persistent anomaly:** classificazione sul periodo di assessment esplicitamente indicato, distinta dalla data del composito selezionato.
- **Recovery trend:** pendenza descrittiva annua; scala cromatica fissa ±0,05 unità/anno, distinta dalla soglia direzionale ±0,01.
- **Data reliability:** frazione di compositi con baseline e osservazione sufficienti; la soglia operativa del 70% è dichiarata.

Il nodata è grigio, distinto da zero, da una bassa vegetazione e da un’anomalia negativa. La basemap resta Esri World Imagery con data variabile, senza presentarla come fotografia del giorno storico.

## Zone e aree

Connected components con **quattro vicini** sulle coordinate native globali. Sono aggregate solo celle attualmente classificate con anomalia negativa persistente. Minimo predefinito 3 celle; componenti più piccole non vengono presentate come zone. Area = numero di celle × area nativa. Ogni zona riporta celle, area osservata, anomalia mediana, durata minima e completezza mediana. I cluster storici di periodi diversi non sono fusi.

Le etichette sono “Persistent vegetation anomaly zones”. Siccità, clima, uso del suolo e altri eventi possono contribuire. Nessuna attribuzione causale automatica.

## Esportazioni e limiti di risorse

GeoTIFF multibanda per indice/tile, CRS e risoluzione nativi: tre bande per data (valore, baseline, anomalia) e quattro bande statiche (trend annuo, completezza, durata persistente, classe). Le descrizioni delle bande includono data e grandezza; i nodata restano NaN. Classi: 0 insufficiente, 1 persistente negativa, 2 nella fascia, 3 sotto, 4 sopra. Le esportazioni sono sotto la quota risultati esistente e sono protette dalla pulizia.

La mappa interattiva rappresenta impronte vettoriali delle celle dei raster reali, limitate alla piccola AOI: non trasmette matrici raster enormi come JSON. Massimo 50.000 celle e `AFTERFIRE_RECOVERY_MAX_CELL_OBSERVATIONS=2000000` coppie cella/data per indice; oltre il limite si richiede esplicitamente un’area/intervallo minore, senza ridurre automaticamente la risoluzione. Per un impiego su aree molto maggiori occorrerà un servizio tile e un formato colonnare per le serie per pixel.


## Phase 6 — Reburn & Recovery Gap

The existing implementation is extended by [Reburn Intelligence](REBURN_INTELLIGENCE.md), [observed episode methodology](REBURN_DETECTION_METHODOLOGY.md), [shared-area Recovery Gap](RECOVERY_GAP.md) and [cumulative vegetation](CUMULATIVE_VEGETATION.md). See [measured infrastructure changes](PERFORMANCE_OPTIMIZATION.md) and [verification and limitations](PHASE6_VERIFICATION.md). Previous-phase publications and reports are preserved.
