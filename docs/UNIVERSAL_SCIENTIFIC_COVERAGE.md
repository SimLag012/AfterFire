# AfterFire — copertura scientifica e analisi adattiva

Verifica del 11 novembre 2026. Base remota `d37e2b2`; preservato e committato separatamente il lavoro già in staging sul limite dei 30 giorni. Motore pubblicato: `modis-recovery-3.1.0`; metodo ottico: `optical-evidence-2`.

## Esito misurato

| Categoria scientifica | Prima | Dopo |
|---|---:|---:|
| Combustione mappata e vegetazione | 15 | 15 |
| Vegetazione candidata, combustione non confermata | 4 | 5 |
| Evidenze limitate | 0 | 0 |
| Osservazioni insufficienti | 1 | 0 |
| Errore tecnico | 0 | 0 |

Il campione principale contiene 20 candidati reali, scelti senza conoscere gli esiti: ordinamento SHA-256 con seme `afterfire-universal-2026-11-11`, primi quattro candidati per viewport non vuoto, in cinque regioni e tra 2019 e 2024. Il viewport iniziale nordamericano vuoto resta nel manifesto; è stata aggiunta una finestra canadese. Non sono stati scartati eventi dopo averne visto i risultati. Il manifesto iniziale da 16 casi documenta il tentativo incompleto, non un campione alternativo favorevole. I candidati vengono selezionati attraverso gli stessi endpoint usati da Explorer; la selezione da mappa è stata verificata anche nel browser.

I 19 risultati MODIS già pubblicati hanno identiche geometrie, celle bruciate, valori NDVI/EVI, pixel validi, baseline, anomalie e metriche prima/dopo. Il ventesimo non aveva una pubblicazione: ora dispone di evidenze HLS. Tutte le 29 pubblicazioni presenti prima dell’attivazione sono rimaste identiche, verificando SHA-256 dei payload. Quattro candidati del campione hanno coppie ottiche indipendenti supportate; non sono quattro nuove conferme di incendio. Tutte le nuove pubblicazioni rimangono `partial` quando esistono lacune QA o limiti scientifici.

## Cause verificate e modifiche

- Il preflight dello stato locale richiedeva anche MCD64A1 per autorizzare la vegetazione: ora le disponibilità sono indipendenti. Un candidato storico senza MODIS sufficiente passa alla verifica ottica, senza abbassare il QA.
- La pipeline interrompeva la pubblicazione quando non trovava celle bruciate né compositi MODIS accettati. Ora conserva geometria, dati disponibili, conteggi e ragioni, distinguendo cinque categorie scientifiche. Gli errori del provider restano limiti tecnici, non insufficienza scientifica.
- Caso canadese casuale `global-08360dbf12a89d9e290d4efbcf07adfa`: prima osservazioni insufficienti; dopo HLS S30 pre/post del 17 e 27 maggio 2023, copertura NBR circa 86% e 65%, nessuna combustione MCD64A1 confermata. dNBR descrittivo circa 0,213 sul supporto congiunto; nessuna classificazione di severità.
- Regressione aggiuntiva Sardegna `global-3667e91d235a57ea33ce2a9dea557a0a`: 78 granuli elaborati in precedenza senza errori; 95 centri MODIS nel territorio. Nei due subset grezzi ispezionati si osservano fill e numerosi pixel della classe costiera/land-water 2, esclusi dal QA validato. Affidabilità nominale buona da sola non basta. Con Sentinel-2 si recuperano cinque scene valide e una coppia pre/post con copertura NBR circa 61%/60%. Nessuna curva MODIS inventata e nessuna conferma della combustione.
- Durante l’integrazione si è verificato che `filterBounds` HLS da solo restituiva anche tessere lontane con impronte non delimitate. Il filtro MGRS riproducibile restringe la ricerca alle tessere locali, includendo il margine di sovrapposizione.
- La versione del motore invalidava checkpoint MODIS scientificamente identici. La versione dei checkpoint resta separata (`modis-recovery-3.0.0`) finché estrazione, maschera e QA MODIS non cambiano. Test esplicito di compatibilità.

La geometria candidata rimane l’inviluppo convesso degli hotspot con buffer metrico locale azimutale equidistante, definito prima di interrogare i dati. Non si espande per cercare celle bruciate. Le celle sono selezionate con la regola preesistente dei centri nativi, data, incertezza e QA; associazioni ambigue restano escluse dalla geometria del recupero. La mappa e il riepilogo distinguono territorio candidato e celle osservate. Nessun nuovo errore di proiezione MODIS è emerso nel campione.

## Metodo multisensore e limiti

MODIS resta la serie storica e la baseline stagionale validata. Quando mancano celle univoche o osservazioni valide pre/post, si interrogano in un solo batch i metadati delle collezioni eleggibili HLS L30/S30, Sentinel-2 SR e Landsat 5/7/8/9 Collection 2 Level 2. Si calcolano al massimo due sorgenti, sei scene per lato entro 90 giorni. Si privilegia Sentinel-2 se il territorio rientra nel budget nativo a 10 m, altrimenti HLS; si interrompe alla prima coppia adeguata. Il budget corrente esclude una sorgente oltre l’80% di 100.000 pixel stimati, senza aumentare la scala o usare `bestEffort`. Non si eseguono tutte le analisi per tutti i sensori.

QA ottico: HLS Fmask esclude nube, prossimità nube/ombra, ombra, neve, acqua e aerosol alto; Sentinel-2 accetta SCL vegetazione/suolo nudo; Landsat esclude fill, nubi, cirri, ombre, neve, acqua e saturazione, mantenendo il bit Clear. Le riflettanze HLS Earth Engine sono già scalate; Sentinel-2 usa 0,0001; Landsat usa 0,0000275 e offset −0,2. Controlli fisici e denominatori validi precedono gli indici. NDVI/EVI Sentinel-2 sono ridotti sulla griglia a 10 m; NBR usa B8A/B12 a 20 m. Ogni riduzione usa proiezione e scala native. dNBR viene calcolato solo tra griglie native identiche e pixel congiuntamente validi, non sottraendo mediane territoriali.

Gli indici ottici non sono inseriti nelle osservazioni o nelle baseline MODIS. Si tratta di osservazioni vegetative e spettrali del candidato, non di un prodotto ufficiale burned area. Non sono disponibili una validazione indipendente della combustione o soglie di severità validate: il risultato lo dichiara. Le scene possono differire per copertura, fenologia, raccolto e umidità. Il limite di due sorgenti/sei scene per lato può lasciare inesplorate osservazioni successive valide; non si sostiene copertura universale o recupero ecologico dimostrato. I limiti MODIS esistenti su AOI/granuli restano applicati e configurabili; le impostazioni sono accessibili anche senza una prima pubblicazione.

Le anteprime RGB sono richieste soltanto quando visualizzate, ritagliate al candidato e limitate a 512 pixel e 4 MiB; il ricampionamento serve alla visualizzazione. Nessuna scena completa, esportazione Earth Engine o nuovo task AppEEARS. Cache con chiavi geometriche, temporali, di QA/metodo, lock tra processi e pubblicazioni persistite; le risposte con errori ottici non vengono memorizzate come assenze valide.

## Prestazioni e traffico

Mediana richiesta→risultato: 38.859 s prima, 26.437 s dopo. Mediana pipeline dei risultati pubblicati: 35.6 s / 16.755 s. Ripetizione della richiesta: 0.019 s, stesso job in 20/20 casi.

MODIS: 49,832,152 byte di array decodificati acquisiti prima; 0 nuovi byte dopo, con riuso della cache. Risposte JSON ottiche nel campione: 70,792 byte. Il traffico HTTP effettivo, autenticazione/overhead SDK e traffico interno cloud non sono misurati; non si sommano questi conteggi come byte su filo.

I tempi non costituiscono un benchmark a cache equivalenti: la seconda fase riusa sorgenti della prima. Include anche un riavvio controllato del worker per attivare la compatibilità dei checkpoint; il tempo richiesta→risultato comprende attesa e recupero del lease. I dettagli per evento conservano questa latenza, senza eliminarla per migliorare la media. Nessuna riduzione degli errori tecnici può essere dedotta: erano zero anche prima.

## Verifiche di rilascio

- Backend finale: 207 test passati su SQLite temporaneo e 207 su PostgreSQL dedicato `afterfire_test_universal_20261111`; database operativo non usato dai test.
- Test scientifici inclusi: QA MODIS invariato, date/scale/proiezioni, separazione candidato/combustione, maschere per sensore, budget e compatibilità checkpoint.
- Build TypeScript/Vite e immagini Docker backend, worker, frontend riuscite.
- Browser reale tramite browser integrato: selezione da Explorer; Brasile, Australia e Canada del campione più regressione Sardegna, desktop 1440×1000 e mobile 390×844, senza overflow. Immagini datate reali caricate; Recovery Intelligence MODIS verificata; assenza del grafico di recupero quando MODIS è insufficiente. Il runner CLI Playwright è fornito ma non è stato usato come prova di riuscita: il Chromium previsto dagli script storici non esiste in questo runtime.
- Secret scanning dei blob Git e controllo whitespace completati; nessuna credenziale o scena completa inclusa nei commit. File locali estranei e artefatti preesistenti non sono stati aggiunti.

## Casi del campione

| Candidato | Regione | Prima | Dopo | Ottico | MODIS validi (indici) | s dopo |
|---|---|---|---|---|---:|
| `global-66cbb1d3ab8865c663719a9cf3287fd6` | brazil | Burn + VI | Burn + VI | — | 64 | 46.931 |
| `global-75e84782b376558619c389da8e6fc716` | brazil | Burn + VI | Burn + VI | — | 80 | 37.613 |
| `global-1da33a9eb741c54ede92a99dd7bcec3b` | brazil | Burn + VI | Burn + VI | — | 48 | 85.822 |
| `global-f626c357cf56a84c532365e622c257da` | brazil | Burn + VI | Burn + VI | — | 84 | 48.945 |
| `global-9c2c24dd1272c940d44751b47b44c544` | southern_africa | Burn + VI | Burn + VI | — | 104 | 41.142 |
| `global-67e2b874c620b0d65a0bf0ae24986af0` | southern_africa | Burn + VI | Burn + VI | — | 106 | 214.928 |
| `global-94f806faad3e2ad6938b8a14941a0330` | southern_africa | Burn + VI | Burn + VI | — | 104 | 11.358 |
| `global-8fde71bb30d403cd50fa5e063b82192f` | southern_africa | Burn + VI | Burn + VI | — | 98 | 14.304 |
| `global-f7cb018c137015e862c46477265634b4` | australia | VI candidata | VI candidata | Sentinel_2 | 116 | 29.579 |
| `global-3cc35cec1062a8ee07ec3f58a59daaa8` | australia | Burn + VI | Burn + VI | — | 114 | 17.626 |
| `global-dcf6c3104d4ccaae41e607b9001416f5` | australia | Burn + VI | Burn + VI | — | 118 | 23.009 |
| `global-0dd9b9d40589368dd479050d3d712f4b` | australia | Burn + VI | Burn + VI | — | 114 | 17.02 |
| `global-7979a92ec3524e523ee8bb35539ef03e` | siberia | Burn + VI | Burn + VI | — | 30 | 20.253 |
| `global-f4cb534f05897923399b28794eaf82df` | siberia | Burn + VI | Burn + VI | — | 36 | 14.582 |
| `global-7157fc3286de2eb0e9b8582af9bd42dd` | siberia | VI candidata | VI candidata | HLS_L30 | 34 | 26.957 |
| `global-9709bff093c7ccab50d2ecdc3c235e6e` | siberia | VI candidata | VI candidata | HLS_S30 | 46 | 25.916 |
| `global-0ccb066bbdad86b5aedb8df0a81a3784` | canada_west | Burn + VI | Burn + VI | — | 64 | 14.843 |
| `global-613540c6540b89ce0820213935d42ee3` | canada_west | VI candidata | VI candidata | — | 58 | 50.647 |
| `global-08360dbf12a89d9e290d4efbcf07adfa` | canada_west | Insufficiente | VI candidata | HLS_S30 | 0 | 39.029 |
| `global-ead9f0016a759f1209758405f7b207cf` | canada_west | Burn + VI | Burn + VI | — | 54 | 23.082 |

Artefatti: [manifesto](universal-coverage/manifest.json), [confronto numerico](universal-coverage/comparison.json), [prima](universal-coverage/before-enriched.json), [dopo](universal-coverage/after-enriched.json), [immutabilità pubblicazioni](universal-coverage/publication-check.json), [browser](universal-coverage/browser.json), [SQLite](universal-coverage/sqlite-tests.txt), [PostgreSQL](universal-coverage/postgres-tests.txt).

## Fonti metodologiche

- [HLS S30, bande e Fmask](https://developers.google.com/earth-engine/datasets/catalog/NASA_HLS_HLSS30_v002)
- [HLS L30, bande e Fmask](https://developers.google.com/earth-engine/datasets/catalog/NASA_HLS_HLSL30_v002)
- [Sentinel-2 SR Harmonized, scale e SCL](https://developers.google.com/earth-engine/datasets/catalog/COPERNICUS_S2_SR_HARMONIZED)
- [Landsat 8 Collection 2 L2, scale e QA](https://developers.google.com/earth-engine/datasets/catalog/LANDSAT_LC08_C02_T1_L2)
- [Landsat 7 Collection 2 L2](https://developers.google.com/earth-engine/datasets/catalog/LANDSAT_LE07_C02_T1_L2)

Il probe Landsat storico del 2008 verifica l’adattatore su un controllo geografico e resta separato dal campione di incendi. Ha restituito vegetazione valida Landsat 7; dNBR è stato correttamente lasciato indisponibile quando le griglie pre/post differivano.
