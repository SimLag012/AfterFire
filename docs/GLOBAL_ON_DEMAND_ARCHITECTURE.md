# Global on-demand architecture

The clean-install workflow starts in Explorer, centered on Italy. The browser requests only its actual debounced viewport, at most 30° per dimension and 1–7 UTC days. Dateline viewports split into two bounded requests. NASA availability determines MODIS/VIIRS SP/NRT source/date segments; missing satellite dates are explicitly reported in `coverage.complete` and `coverage.missing_coverage`. Provider failures and unsupported periods are never empty-fire responses.

```mermaid
flowchart LR
  Viewport --> Availability --> FIRMS[FIRMS bounded cached CSV]
  FIRMS --> Snapshot[Provisional cluster snapshot]
  Snapshot -->|Explicit selection| Candidate[Persisted candidate]
  Candidate -->|Analyze| Queue[Durable job and lease]
  Queue --> Worker --> EE[Earth Engine native subsets]
  EE --> QA[Strict QA and pre-event baseline]
  QA --> Publication[Atomic scientific publication]
  Publication --> Recovery[Story and Intelligence]
  Publication --> Lazy[Requested dated maps]
```

CSV caching is shared across processes; requests are serialized, capped and deduplicated. Snapshots are bounded/disposable, while selected candidate detections and scientific publications persist. Clusters are reproducible for their exact viewport, dates and observations; changing boundaries may change membership and candidate IDs. Thermal points, provisional geometry and observed burned cells have separate meanings. There is no worldwide archive import, silent HDF fallback or new AppEEARS task.

See [release verification](FINAL_RELEASE_VERIFICATION.md) for real multi-continent checks, performance, limits and reproduction commands; [scientific methodology](SCIENTIFIC_METHODOLOGY.md) for baseline/QA; [cache policy](CACHE_MANAGEMENT.md) for protected results and explicit cleanup.
