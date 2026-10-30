# Recovery Assessment — metodologia Fase 5

Il motore `assessment-5.0.1` descrive **evidenze osservate degli indici vegetativi**. Non misura il recupero ecologico completo, non attribuisce automaticamente ogni cambiamento all’incendio e non prevede date future. [Architettura e API](RECOVERY_INTELLIGENCE.md), [analisi spaziale](SPATIAL_RECOVERY_ANALYSIS.md), [verifica riproducibile](PHASE5_VERIFICATION.md).

## Osservazioni e riferimento

Si riutilizzano le osservazioni pubblicate MOD13Q1.061, con calibrazione NDVI/EVI ×0,0001 e QA rigoroso della pipeline esistente. Il composito rappresenta un intervallo di 16 giorni; la data non è l’istante di acquisizione di ogni pixel. NASA documenta risoluzione nominale e compositing nella [scheda MOD13](https://modis.gsfc.nasa.gov/data/dataprod/mod13.php) e nella [scheda MOD13Q1 Collection 6.1](https://ladsweb.modaps.eosdis.nasa.gov/missions-and-measurements/products/MOD13Q1/).

Per ogni data t:

- si selezionano soltanto compositi che **terminano prima del primo rilevamento FIRMS**;
- la distanza stagionale è circolare, sui giorni di calendario dell’anno bisestile di riferimento 2000: `min(abs(d1-d2), 366-abs(d1-d2))`;
- finestra stagionale configurata dalla sorgente, predefinita ±24 giorni;
- almeno 3 compositi validi e almeno 2 anni distinti, configurabili; per un punto precedente all’evento sono ammesse soltanto osservazioni terminate prima di quel punto;
- `B(t) = mediana(riferimenti validi)`;
- `MAD(t) = mediana(abs(riferimenti − B(t)))`;
- `H(t) = max(0,05; 1,4826 × MAD(t))`;
- `A(t) = indice osservato(t) − B(t)`;
- fascia operativa di riferimento `[B(t)−H(t), B(t)+H(t)]`.

La fascia è una convenzione descrittiva ereditata dalla Fase 4, **non un intervallo di confidenza** e non una soglia ecologica universalmente validata. Nessuna normalizzazione per denominatori piccoli. Se il riferimento manca, baseline e anomalia sono null. Le lacune non diventano zero.

## Indicatori

**Cambiamento iniziale.** Si riportano separatamente prima osservazione post-evento valida, valore minimo supportato e anomalia minima supportata nei primi 90 giorni dall’ultima rilevazione FIRMS. La prima osservazione non viene identificata con il danno massimo. Una finestra selezionata che esclude questi giorni non produce un minimo iniziale artificiale.

**Trend descrittivo.** Mediane mensili delle anomalie, quindi mediana di tutte le pendenze fra coppie di mesi, con tempo effettivo in giorni e fattore 365,2425 per anno. Sono richiesti almeno 4 mesi e 90 giorni di estensione. È il principio [Theil–Sen](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.mstats.theilslopes.html), implementato con libreria standard. La soglia ±0,01/anno distingue direzioni operative; non è un test di significatività. L’aggregazione mensile attenua la dipendenza fra compositi vicini, senza pretendere di eliminare l’autocorrelazione. Nessun p-value, percentuale di probabilità o intervallo IID.

**Anomalia negativa persistente.** Almeno 3 osservazioni consecutive supportate, distanti complessivamente almeno 32 giorni, ciascuna sotto il limite inferiore della fascia e con anomalia ≤−0,05. Un composito mancante/QA insufficiente interrompe la sequenza; anche un salto fra date >32 giorni la interrompe. Durata = distanza fra inizi dei primi/ultimi compositi, non somma di giorni artificialmente riempiti. Le sequenze storiche sono conservate separatamente dalla classificazione corrente.

**Ritorno sostenuto.** Stessi requisiti di supporto e durata, con osservazioni dentro entrambi i limiti della fascia. La data riportata è la prima evidenza osservata di una sequenza sostenuta. Un successivo peggioramento non cancella il fatto storico. Valori superiori al limite superiore sono etichettati separatamente; non vengono automaticamente chiamati recupero completo.

**Qualità.** Numero di compositi attesi, validi e con baseline; completezza = supportati/attesi, massimo salto fra osservazioni supportate, copertura spaziale mediana, anni minimi di baseline, periodo realmente coperto. Le etichette operative sono `insufficient` con meno di 3 punti supportati, `limited` con meno di 12 punti o completezza <70%, altrimenti `supported`. Non sono probabilità né certificazioni scientifiche. NDVI ed EVI rimangono separati e la discordanza è visibile.

## Parametri e riproducibilità

`AssessmentParameters` valida finestra iniziale, numero minimo di riferimenti, durata, consecutività, lacuna massima, magnitudine negativa, supporto del trend, dimensione minima dei cluster e finestra post-evento opzionale. La finestra post-evento non cambia i riferimenti pre-evento. Tutti i parametri, versione e fingerprint SHA-256 del risultato sorgente entrano nell’identità persistente.

Non è stato addestrato ML: il piccolo insieme di eventi indipendenti verificati non giustifica un modello con separazione geografica/temporale e validazione esterna. Gli insight sono testi deterministici prodotti da risultati strutturati, senza LLM e senza alterare i valori.
