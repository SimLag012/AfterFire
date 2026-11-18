# Scientific methodology

AfterFire distinguishes three kinds of evidence: FIRMS thermal observations, algorithmic event candidates, and QA-screened satellite measurements of burned cells or vegetation. A candidate is not an official fire identity; a detection or mapped grid cell is not an official fire perimeter. All interpretation is retrospective.

## Products, provenance and geometry

| Product | Native evidence | Time support |
| --- | --- | --- |
| FIRMS MODIS / VIIRS | Thermal observations; nominal nadir footprints of 1 km / 375 m | Satellite overpass time, retained in UTC |
| MCD64A1.061 | BurnDate, uncertainty, QA and mapping coverage; nominal 500 m | Monthly product with estimated pixel burn dates |
| MOD13Q1.061 | NDVI/EVI, detailed QA and pixel reliability; nominal 250 m | 16-day composite periods |

Original sensor, satellite, processing/version, confidence, FRP and acquisition attributes remain traceable. Original records from different instruments are not interchangeable fire counts. Synthetic records are excluded from real-data Explorer results.

Candidate grouping uses operational spatial/temporal proximity, not verified administrative boundaries. Map marker clusters vary with zoom and are separate from persisted scientific candidate membership. Updated source membership can change a candidate's identity.

Event analysis distinguishes the linked hotspot footprint, a configurable provisional buffer and uniquely associated mapped burned cells. MCD64A1 cells are associated when their burn-date uncertainty interval overlaps the candidate interval plus configured tolerance, default three days. Cells compatible with competing candidates are marked ambiguous and excluded from unique association. Without associated mapped cells, vegetation may use an explicitly labelled provisional hotspot buffer; this is not evidence of mapped burned area.

The native MODIS sinusoidal grid uses sphere radius 6,371,007.181 m. A tile has 2,400 burned-area cells or 4,800 vegetation cells per axis, approximately 463.31 m or 231.66 m wide. Scientific areas use the actual native affine transform, not nominal 500 × 500 m areas. Cell-centre selection, grid identity and integral offsets determine correspondence. Display reprojection does not redefine scientific cells or QA.

## Quality and vegetation extraction

MCD64A1 requires valid land/mapping QA, positive valid burn day-of-year and uncertainty of 0–100 days for an observed burned cell. A shortened mapping period is rejected. Mapping coverage also excludes unsupported special conditions; unburned, unknown and missing observations remain distinct. Burn dates are decoded using the product year, not assumed from the file month. Repeated cell/date observations are deduplicated while retaining source provenance.

MOD13Q1 uses `index = raw × 0.0001`, with raw range −2,000…10,000. Out-of-range values remain missing. The strict mask requires pixel reliability 0; MODLAND bits 0–1 equal 0; usefulness bits 2–5 ≤2; aerosol bits 6–7 unequal to 3; adjacent/mixed cloud bits 8/10 clear; land/water bits 11–13 equal 1; snow/shadow bits 14/15 clear. Missing QA is rejected.

Area observations use the median of retained native pixels, with valid/expected counts, valid fraction and spatial dispersion. The default minimum valid fraction is 50%, counting missing intersecting tiles in expected coverage. Spatial dispersion is not a confidence interval. Valid masks can differ between dates even on the same analysis geometry.

Every expected composite has an explicit state. Missing, QA-rejected and incomplete periods keep null values; no interpolation or invented satellite frames are used. Composite dates describe periods, not every pixel's exact acquisition instant.

## Seasonal reference and recovery

Current event assessments compare each index against wholly pre-event observations from the same season. Legacy area reports use an older non-seasonal method and must not be interpreted as the event assessment.

For target date `t`, references must finish before the first FIRMS observation. Pre-event chart points additionally use only still-earlier references. Defaults require at least three valid composites from at least two years within ±24 seasonal days. Circular calendar distance uses the leap-stable reference year 2000:

```text
seasonal_distance = min(abs(day1 - day2), 366 - abs(day1 - day2))
B(t) = median(valid seasonal references)
MAD(t) = median(abs(reference - B(t)))
H(t) = max(0.05, 1.4826 * MAD(t))
A(t) = observed index(t) - B(t)
reference band = [B(t) - H(t), B(t) + H(t)]
```

The band is an operational descriptive range, not a confidence interval or universally validated ecological threshold. Post-fire values do not enter the pre-fire reference. Missing support yields null baseline/anomaly, not a fabricated reference or zero.

| Indicator | Default evidence rule |
| --- | --- |
| Initial change | First valid post-event observation and supported minimum/anomaly within the first 90 days are reported separately |
| Descriptive trend | Monthly anomaly medians; median pairwise slope using elapsed days and 365.2425 days/year; at least four months and 90 days |
| Persistent negative anomaly | At least three consecutive supported observations spanning ≥32 days, each below the band and with anomaly ≤−0.05 |
| Sustained return | Same observation count/duration, with supported values inside both band limits |
| Sequence break | Missing/insufficient observations or a gap >32 days interrupts persistence |
| Operational support | `insufficient` below three supported points; `limited` below 12 points or 70% completeness; otherwise `supported` |

The directional trend threshold is ±0.01 index units/year, not a significance test. Sequence durations use observed date differences; gaps are not filled. Historical return and negative periods remain separately visible if later observations change the current classification. Values above the band are not automatically labelled complete recovery. NDVI/EVI evidence and discordance remain separate.

### Native-cell maps and exports

Recovery Intelligence applies the seasonal method to each native vegetation cell. Per-cell support does not require an area-wide composite to pass the 50% threshold. Maps distinguish seasonal anomaly, period classification, descriptive trend and data reliability; nodata is distinct from zero. Persistent anomaly zones use four-neighbour native connectivity and at least three cells by default. Areas derive from actual cell counts and native areas, without causal attribution.

GeoTIFF exports preserve native grid, scaling, nodata and band descriptions. Unsupported all-nodata bands/exports are omitted; consumers must use band descriptions rather than assuming a fixed number of bands per date. Parameters, assessment/source fingerprints and scientific versions are part of publication identity.

## Repeated burning and Recovery Gap

Repeated burning requires distinct valid MCD64A1 observations on the **same native cells**. Global native row/column IDs establish identity; rounded longitude/latitude does not. A 500 m burned cell corresponds to four 250 m vegetation children. Shifted or incompatible grids are rejected.

Observed burn episodes are connected components on a cell and its four neighbours when uncertainty intervals fall within the configured separation, default 32 days. Disconnected patches can belong to one actual fire; a long connected chain can merge disturbances. Neither rule establishes official fire identity. Missing product coverage does not become a no-burn observation.

Recovery Gap uses the intersection of native cell IDs for an episode pair, removing cells with an intervening episode. Its interval uncertainty is `[B.lower - A.upper, B.upper - A.lower]`. No common ground or overlapping bounds means insufficient evidence. Vegetation is reconstructed from the actual native children of the shared cells; full-event statistics are not copied onto a smaller overlap.

The seasonal reference ends before the earliest episode's lower uncertainty bound. Eligible between-episode composites start after episode A's upper bound and finish strictly before episode B's lower bound. Default freshness is 48 days from the last eligible composite's end; fewer than three supported composites or stale support yields `insufficient_observations`.

The assessment retains supported return, persistent negative anomaly, no sustained return demonstrated, insufficient observations and conflicting NDVI/EVI evidence as distinct outcomes. Absence of demonstrated return does not establish non-recovery. Cumulative histories preserve the same fixed pre-disturbance reference and explicit gaps; they do not infer causation or predict future risk.

## Historical MODIS/VIIRS activity harmonization

The activity calendar uses a separate metric: **daytime occupied 10 km equal-area cell-days**, on a fixed EPSG:6933 grid. A satellite/day/cell counts once when at least one daytime detection occurs. Original night observations remain available, but occupancy is not physical fire count, burned area or emitted energy.

The direct reference is Aqua daytime occupancy. Terra is not concatenated into Aqua, and additional VIIRS missions are not summed to inflate the reference. A complete archive query establishes acquired records, not cloud-free observational coverage or absence of burning. Months before the Aqua reference retain missing-reference states.

The released [calibration artifact](../backend/app/fire_activity/calibration.json) defines the supported pilot domain. For area `A`, S-NPP occupancy `V` and Aqua occupancy `M`, the translation uses nonnegative constrained least squares:

```text
x = log(1 + V * 10000 / A)
y = log(1 + M * 10000 / A)
y_hat = a + b*x, with a >= 0 and b >= 0
M_hat = max(0, exp(y_hat) - 1) * A / 10000
```

The pilot uses six regions and January/August observations in 2019–2024, with separated training, interval-calibration, temporal-test and geographic-test sets. Translation requires improvement against identity, absolute relative bias ≤35% and interval coverage ≥70% on both holdouts. The nominal 80% split-conformal interval is not instrument accuracy. Broader scale/season evaluations failed the unchanged gates: there is no universal all-season, arbitrary-shape or all-mission conversion. Unsupported estimates remain null; original observations and directly measured Aqua occupancy stay usable.

Anomalies require at least five other complete years of the same month and compatible method/calibration identity; relative departures require a positive baseline. Annual totals require all 12 months. Annual slopes require at least eight complete direct-reference years. Partial periods and gaps are not replaced with zero. This retrospective reference is independent of Recovery assessments and is not a prediction model.

## Visual comparisons, limitations and attribution

Before/After MODIS views compare the same index on one shared map, with dated composites, QA and coverage. The displayed difference of area medians is not a pixelwise change map. Optical comparisons require compatible native lattices and joint valid support; dNBR is descriptive spectral change, not automatically attributed burn severity.

NDVI/EVI describe greenness, not forest structure, biodiversity or complete ecosystem restoration. Climate, drought, phenology, land management, mixed pixels, product omissions and other disturbances can affect the observed series. Current basemap imagery has acquisition dates independent of the historical scientific layers. No automatic causal attribution or future recovery date is claimed.

The README screenshots were captured from the actual full application on 17 November 2026 at 1440 × 1000: Explorer archive observations for 8–17 July 2026, and the saved July 2023 Ródos event `global-d77c8ac8d89369a61e7125f78cfe2e76`. The Recovery publication spans 21 July 2021–22 July 2024. Map credits remain visible: Esri, Vantor, Earthstar Geographics, GIS User Community and, in Explorer, NASA GIBS. They are existing-publication examples, not data automatically seeded into a fresh installation.

The README walkthrough was recorded on 18 November 2026 from the local static public demo, using the exported Ródos publication. It shows actual Explorer navigation, the Before/After divider, the NDVI/EVI timeline and Recovery Intelligence. The GIF and MP4 contain the same recording; captions and a cursor identify the interactions without changing scientific values.

Country component bounds in `backend/data/country_bounds.json` derive from [Natural Earth 5.1.1 Admin 0 Countries](https://github.com/nvkelso/natural-earth-vector/blob/v5.1.1/geojson/ne_110m_admin_0_countries.geojson), public domain. Place references use [GeoNames](https://www.geonames.org/) under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Context imagery and scientific datasets retain their respective terms.

Primary product specifications: [MOD13 C6.1 user guide](https://lpdaac.usgs.gov/documents/621/MOD13_User_Guide_V61.pdf), [MCD64 C6.1 user guide](https://lpdaac.usgs.gov/documents/1006/MCD64_User_Guide_V61.pdf), [NASA FIRMS](https://firms.modaps.eosdis.nasa.gov/). Acquisition and provider setup are documented in [Operations](OPERATIONS.md).
