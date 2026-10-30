# Cumulative vegetation history

The cumulative trajectory joins observed burn episodes to NDVI/EVI observations, a fixed seasonal reference, anomalies and observation quality. It is a descriptive history, not a cumulative damage score or risk model.

The reference is calculated before the earliest observed episode, with the [Phase 5 seasonal methodology](RECOVERY_ASSESSMENT_METHODOLOGY.md). It is never reset using vegetation between later fires. If the source series begins after an earlier burn, reference support can be insufficient; no baseline is invented.

The territory series aggregates only native children of observed burned-area cells. A selected cell uses its own four children. Each point retains composite start/end, valid fraction, valid and expected pixels, reference observations/years, reference band and anomaly. Missing dates and values remain explicit, with no interpolation.

Segments cover the period before the first episode, between episodes and after the last episode. Temporally overlapping spatial components are grouped before defining these windows. Composites crossing uncertainty bounds are excluded. Each segment records supported/available observations, missing/rejected composites, median/minimum anomaly, trend, persistent negative periods and sustained return periods, separately for NDVI/EVI. The source composite schedule retains missing assets as explicit null observations. Missing cell support never falls back to a whole-territory series.

Timeline buttons, episode selectors and chart reference bands use the actual observed dates and their uncertainty. Map cells expose their own observed dates. Selecting a cell switches the chart's support; selecting an index/composite preserves the same published history. Maps contain small native cell features; no historical raster stack is loaded into the browser.

Vegetation indices can change because of weather, land management, phenology, mixed pixels and other disturbances. The result explicitly records `causal_attribution=false`. [Recovery Gap](RECOVERY_GAP.md), [UI/API](REBURN_INTELLIGENCE.md), [verification limits](PHASE6_VERIFICATION.md).
