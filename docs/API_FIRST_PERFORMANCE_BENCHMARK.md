# API-first follow-up measurements — 2026-10-30

The table below is the historical pre-registration checkpoint. Current real
Earth Engine probe, HDF equivalence and new-event measurements are recorded in
[live verification](EARTH_ENGINE_LIVE_VERIFICATION.md) and
`earth-engine-live-verification.json`; estimates below are not live traffic.

No live Earth Engine benchmark was possible: the owner must first register a
project. See `earth-engine-activation-verification.json` for both runtime probe
results, actual test totals and browser timings.

| Measurement | Observed result and scope |
| --- | --- |
| New Earth Engine satellite arrays | 0 bytes; initialization blocked by configuration |
| Explicit collection/projection/pixel calls | 0 in both deployed runtime probes |
| Exact HTTP/wire bytes | Not measured; no wire-byte estimate is substituted |
| New event acquisition / processing / total time | Not run; unavailable until project setup |
| New scientific observations / burned cells | 0 / 0 |
| Historical payload estimate | 1,796,288 bytes (about 1.71 MiB), **not an observed transfer** |
| Saved Analyze API response | 0.2191 s; 2,706 response-body bytes; same job and attempts |
| Scientific source cache inventory | 3,921,416,895 bytes at the inventory read; total cache size, not bytes received in this work |
| Archive observations before/after | 803,761 / 803,761 |
| Existing publication response | 651,070 bytes; byte-identical across recreation |
| New HDF downloads / AppEEARS submissions | 0 / 0 |

Browser click-to-response timings include application rendering and local
machine load; they are recorded separately from the direct cached API timing.
Probe peak RSS is the whole diagnostic process high-water mark, not memory for
a completed multiyear scientific job. Backend/worker memory snapshots are not
used as a substitute for a scientific-processing benchmark. No new-event cache
hit or new-event ETA is claimed.
