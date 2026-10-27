# AfterFire — Scientific Methodology & Algorithms

## 1. Challenge Context: Harmonization of MODIS and VIIRS Hot Spots

### 1.1 Sensor Footprints & Radiant Disparity
- **MODIS** (onboard Terra and Aqua): 1 km nominal nadir resolution with pixel broadening toward swath edges. High radiometric saturation limit on Channel 21/22 (4 µm) with Channel 31 (11 µm) for false alarm rejection.
- **VIIRS** (onboard Suomi-NPP, NOAA-20, NOAA-21): 375 m nominal nadir resolution on I-band (I4 at 3.74 µm, I5 at 11.45 µm).
- **Core Dilemma**: Because of the ~3-fold spatial resolution advantage, VIIRS detects smaller, lower-intensity, and smoldering fires that do not trigger the MODIS sub-pixel threshold. Directly summing detection points from both sensors over a single fire will grossly overestimate physical fire occurrences.
- **AfterFire Harmonization Rule**:
  1. Each raw record preserves instrument identifier, satellite, original confidence code, brightness temperature, and Fire Radiative Power (MW).
  2. Detections are categorized into standardized confidence tiers:
     - Numeric $\ge 80\%$ or categorical `'high'` $\rightarrow$ `high`
     - Numeric $30\% - 79\%$ or categorical `'nominal'` $\rightarrow$ `nominal`
     - Numeric $< 30\%$ or categorical `'low'` $\rightarrow$ `low`
  3. Daily, weekly, and monthly calendars group detections with discrete sensor breakout counts (`modis_count`, `viirs_count`) rather than unified scalar addition.
  4. Spatiotemporal clustering (DBSCAN variant: 7 km spatial radius, 3-day max temporal gap) groups detections into candidate fire events without asserting official administrative perimeters.

---

## 2. Differentiating Active Hotspots from MCD64A1 Burned Area

- **Point Hotspots**: Indicate thermal radiation emitted at the exact instant of satellite overpass (~4 passes daily per sensor). A single fire flaming over 5 days may generate 50+ detection records across overlapping passes.
- **MCD64A1 Burned Area Product**: Global 500m monthly composite providing pixel-level classification of charred land surface. Each classified pixel carries an estimated burn date (DOY) and temporal uncertainty (typically $\pm 2$ days).
- **AfterFire Separation**: The platform renders MCD64A1 as spatial polygon patches and displays total mapped hectares independently from hotspot detection totals.

---

## 3. Post-Fire Canopy Recovery Trajectory Engine

### 3.1 Pre-Fire Multi-Year Baseline
To avoid seasonal bias (e.g., comparing Mediterranean wet spring greenness with summer drought dry-down), AfterFire:
1. Evaluates all valid MOD13Q1 250m 16-day composites prior to the fire disturbance date.
2. Computes the baseline mean $\mu_{\text{pre}}$ and standard deviation $\sigma_{\text{pre}}$:
   $$\mu_{\text{pre}} = \frac{1}{N} \sum_{i=1}^{N} \text{NDVI}_i, \quad \sigma_{\text{pre}} = \sqrt{\frac{1}{N} \sum_{i=1}^{N} (\text{NDVI}_i - \mu_{\text{pre}})^2}$$
3. Produces a $\pm 1\sigma$ confidence envelope representing natural seasonal phenological amplitude.

### 3.2 Disturbance Drop & Recovery Percentage
- **Fire Trough ($\text{NDVI}_{\text{trough}}$)**: Minimum valid composite value observed immediately post-disturbance.
- **Drop Magnitude**: $\Delta_{\text{drop}} = \mu_{\text{pre}} - \text{NDVI}_{\text{trough}}$
- **Drop Percentage**: $\%_{\text{drop}} = \left(\frac{\Delta_{\text{drop}}}{\mu_{\text{pre}}}\right) \times 100$
- **Recovery Quotient**:
  $$\text{Recovery \%} = \frac{\text{NDVI}_{\text{latest}} - \text{NDVI}_{\text{trough}}}{\mu_{\text{pre}} - \text{NDVI}_{\text{trough}}} \times 100$$

### 3.3 Status Classification
- **Substantially Recovered**: $\text{Recovery \%} \ge 90\%$
- **Partial Recovery**: $60\% \le \text{Recovery \%} < 90\%$
- **Stagnant / Slow Recovery**: $\text{Recovery \%} < 60\%$

---

## 4. Quality Assurance (QA) Bitmask Masking

MOD13Q1 provides a 16-bit QA word per composite. AfterFire inspects:
- **Bits 0–1 (MODLAND QA)**:
  - `00`: Ideal quality.
  - `01`: Acceptable quality.
  - `10` or `11`: Excluded due to cloud cover, aerosol, or unfilled values.
- **Bit 14**: Snow/Ice flag. Observations with this flag set are excluded from vegetative calculations.

---

## 5. Ecological Limitations

1. **NDVI Represents Greenness, Not Full Biodiversity**: Opportunistic pyrophytic weeds and early-successional shrubs produce high chlorophyll reflectance rapidly, masking lingering devastation in mature tree canopies and soil seed banks.
2. **Sub-Pixel Heterogeneity**: A 250m composite pixel averages 6.25 hectares; small unburned islands or severely scorched soil patches are integrated into a single spatial average.
3. **Compound Re-Burns**: Successive fires occurring before vegetation re-attains reproductive maturity can trigger irreversible ecological regime shifts from mature woodland to degraded pyrophytic scrub.

