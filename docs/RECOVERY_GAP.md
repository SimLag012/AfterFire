# Recovery Gap

Recovery Gap describes observed vegetation evidence between separate burn episodes on the **same native burned-area cells**. It does not diagnose ecological damage, establish causation, or forecast fire risk.

For each pair, take the intersection of native cell IDs. A cell with an intervening episode is removed from that pair; three-burn histories therefore preserve consecutive intervals for each cell. Record common area, shared fractions of both episodes and the nominal interval in days, months (30.436875 days) and years (365.2425 days). The uncertainty range is `[B.lower−A.upper, B.upper−A.lower]`. Overlapping bounds or no shared cells produce insufficient evidence.

The series is reconstructed from published QA-masked native MOD13Q1 rasters. Only the four native VI children of the selected common cells contribute. The median is available only when valid children cover the configured fraction (default 50%). Full-event means are never assigned to the smaller shared area. Missing raster support remains missing, never filled from another territory.

The seasonal reference is fixed before the earliest observed episode's lower uncertainty bound. It reuses the Phase 5 circular seasonal window, median, MAD band and minimum two reference years/three composites. References must finish before the first episode; pre-reference points use only still-earlier composites. A disturbed interval never silently becomes a new reference. No usable baseline means insufficient evidence.

For the pre-reburn assessment, a composite must start after A's upper bound and **finish strictly before B's lower bound**. Thus a MOD13Q1 composite that includes any plausible B date is excluded even if its start date precedes B. Freshness is measured from the last eligible composite's end to B.lower; default 48 days, configurable 16–128. Fewer than three supported composites or a stale last observation produce `insufficient_observations`.

Inherited persistence uses at least three consecutive supported observations over 32 days, breaking at missing values or gaps over 32 days. A negative run requires anomaly ≤−0.05 and value below the seasonal band. Sustained return uses the same duration and count inside the reference band. Parameters are persisted, with no ecological interpretation of the numeric defaults.

Outputs keep both indices and their evidence separately:

- `supported_return_to_reference`;
- `persistent_negative_anomaly_observed`;
- `no_sustained_return_demonstrated`;
- `insufficient_observations`;
- `conflicting_ndvi_evi_evidence` when supported NDVI/EVI classifications differ.

Persistent negative evidence at the latest observation takes precedence in the summary, while an earlier supported return remains separately visible. Absence of demonstrated return does not demonstrate non-recovery. The history's partial coverage remains visible even when an individual pair has sufficient vegetation support.

Cell map assessments use actual native VI children; the territory pair assessment uses the entire common support. Episode-wide date bounds are conservative. Results carry source publication fingerprints, parameters and the scientific version. [Implementation and API](REBURN_INTELLIGENCE.md), [cumulative analysis](CUMULATIVE_VEGETATION.md), [verification](PHASE6_VERIFICATION.md).
