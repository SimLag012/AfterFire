# NASA ORNL TESViS

Official endpoints: [documentation](https://modis.ornl.gov/data/modis_webservice.html), `https://modis.ornl.gov/rst/api/v1/`.

A live probe on 2026-10-30 retrieved MOD13Q1 and MCD64A1 band catalogs and one-cell, one-date subsets in Sicily. Evidence is saved in `ornl-capability-probe.json`. MOD13Q1 returned NDVI, EVI, VI Quality and pixel reliability; MCD64A1 returned Burn Date, Uncertainty, QA, First Day and Last Day. Raw numeric responses and byte counts are recorded without credentials.

Neither tested response explicitly identifies Collection 6.1. A product shortname, matching bands, HTTP 200 or plausible values does **not** prove collection equivalence. Consequently ORNL is not automatically selected for scientific publication. Existing Collection 061 results are never overwritten with these unverified data.

The protocol adapter batches at most ten available MODIS dates per `/subset` call, streams with a response-size budget and rejects unknown/006 collection identifiers. It does not invoke `/subsetOrder`, submit email addresses or create orders. At present routing requires Earth Engine for new compatible API acquisitions. Enabling ORNL alone does not remove the scientific compatibility block; a future adapter change needs actual collection evidence and native-grid equivalence tests, including the rounded coordinates exposed in ORNL metadata.
