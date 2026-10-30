# Global fire explorer

The existing `/explorer` route now uses a map-first layout inspired by the controls of NASA FIRMS, without reusing its branding or implementation. Italy and the Mediterranean remain the initial view; pan and zoom have no Italy boundary. A compressible filter panel, independent Layers panel and bottom timeline keep the map visible on desktop and small viewports.

Fire data can come from the imported archive or an explicitly selected recent online source. The archive initially covers Italy; out-of-coverage messages do not imply an absence of fires. Real database observations only are returned. Individual observations are bounded to 2,000 per viewport; lower zooms use SQL aggregates. A truncation notice requests a narrower area/period. Dates, instruments and Terra/Aqua/S-NPP/NOAA-20/NOAA-21 filter the server query.

Controls include UTC Today, a rolling 24-hour filter at FIRMS minute precision, 7/30 days, 12 months, custom dates and the historical archive. Online retrieval supports at most seven days within the last ten days, in a viewport no wider/taller than 30 degrees. Across-date-line online requests require selecting one side; archive queries support crossing. Source availability can vary by satellite and date.

A 300 ms viewport debounce and AbortSignal cancel stale browser requests. A bounded 128-entry, 15-second server cache accelerates repeated PostgreSQL cluster requests. The cache can briefly lag imports; SQLite/test databases bypass it. Large zoom/query combinations exceeding 8,192 grouped rows are rejected rather than sent unbounded to the browser.

The URL stores filters, view bounds and layer choices. Save/Restore stores the URL query on the current device; Share copies it. The map restores bounds including the date line. Coordinate search works locally. Named place search uses a backend Photon proxy, explicit submits, five-result limit, five-minute bounded cache and one-second global spacing per server process. Attribution: OpenStreetMap contributors / Photon, ODbL. Public Photon is a moderate-use demo without an availability guarantee; self-host or replace it before scaling ([provider policy](https://github.com/komoot/photon#demo-server)).

The default shared `SatelliteBasemap` remains Esri satellite imagery. Optional terrain, labels/borders and dated NASA GIBS imagery are separate contextual layers. Base imagery dates vary and never represent the selected historical fire date. Fire marker size is symbolic, not burned area.

Reference inspected: [NASA FIRMS map](https://firms.modaps.eosdis.nasa.gov/map/). See `MAP_LAYERS_AND_TIMELINE.md` and `API_FIRST_VERIFICATION.md` for semantics and evidence.
