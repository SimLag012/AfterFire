# Static Vercel demo

The [public demo](https://afterfire-public-demo.vercel.app) serves the original AfterFire interface from `public-demo/`, using an explicitly exported snapshot of existing scientific publications. The local frontend and scientific backend remain independent. No backend, credentials or new acquisitions are required to visit the demo.

## Snapshot and limitations

The export allowlist is `scripts/vercel_demo_selection.json`; `public-demo/public/demo/manifest.json` records the exact available events, studies, publication identities, objects, omissions and coverage. Consult these files when updating the snapshot rather than treating a past export count as permanent.

The selected examples include Ródos, Morphett Vale, Paradise, Fouchana and Iglesias, plus three Fire Activity studies. The long Sardinia study is partial: requested dates do not establish continuous coverage. Unsupported observations and classifications remain null. Incompatible assessment fingerprints are excluded and recorded as omissions.

The original Explorer, **Analyze candidate**, calendars, NDVI/EVI timeline, Before/After, cell maps and published Reburn results read static responses. Filtering changes only the exported subset. New analyses, provider requests, imports, administration, dynamic reports and unexported downloads are unavailable. There is no fallback to FastAPI. Contextual map tiles/fonts remain external browser dependencies, with their original attribution.

`require_before_after` in the allowlist requires each selected event to have an exported authentic MODIS comparison or a genuine optical pair bracketing the event. It never manufactures missing frames or implies MODIS support where only optical evidence exists.

## Refresh and preview

Run from the repository root after verifying the original scientific publications:

```bash
python3 scripts/prepare_vercel_clone.py
python3 scripts/export_vercel_demo_docker.py
python3 scripts/check_vercel_clone.py
npm --prefix public-demo ci
npm --prefix public-demo run build
npm --prefix public-demo run preview
```

Open http://127.0.0.1:4173. The standard Vite preview replaces the removed custom preview server; deployment routing is configured separately in `public-demo/vercel.json`.

Preparation copies the current original frontend and applies explicit transport/availability adaptations. `clone-source.json` records source hashes and the adapted files. The integrity check verifies the snapshot and unchanged original App/map/chart/style files. If an original frontend change prevents a safe adaptation, preparation fails and requires reviewing that patch.

The Docker exporter uses the existing **local** container `afterfire-clean-backend-1`, its database and cache, without starting the HTTP server or worker. Override its name when needed:

```bash
python3 scripts/export_vercel_demo_docker.py --container YOUR_LOCAL_BACKEND
```

For direct export, use the backend Python environment and select the actual database/cache containing the allowlisted publications:

```bash
PYTHONPATH=backend backend/.venv/bin/python scripts/export_vercel_demo.py \
  --selection scripts/vercel_demo_selection.json \
  --database-url "sqlite+aiosqlite:///$PWD/backend/afterfire.db" \
  --cache-dir "$PWD/.local-runtime/analysis-cache" \
  --output public-demo/public/demo
```

The exporter reads PostgreSQL in a repeatable-read/read-only transaction or SQLite with `query_only`. It does not migrate schemas, compute new scientific publications or acquire provider data. Missing previews may be rendered from checksum-verified published native checkpoints with the original renderer. Optical previews must already exist locally.

Objects are deduplicated by SHA-256; large JSON/GeoJSON objects use lossless gzip and PNGs retain their scientific colour scales. The default export limit is 80 MiB. Staging is validated before atomically replacing an exporter-owned snapshot. Unknown private annotations abort the export. Database files, credentials, full caches, native GeoTIFFs and private operational metadata are excluded. Decompress `.json.gz`/`.geojson.gz` before using them in external tools.

## Hosting

| Setting | Source build |
| --- | --- |
| Root directory | `public-demo` within this repository |
| Framework | Vite |
| Node.js | 22.x |
| Install | `npm ci` |
| Build | `npm run build` |
| Output | `dist` |
| Environment variables / backend / database | None |

If importing the parent workspace, use `afterfire/public-demo` as the root. Do not include source files outside that root or copy local `.env` files. Export runs locally before deployment; Vercel receives the prepared static project. The existing public site has also been deployed from locally prebuilt output; that path uses no remote install/build command.

`public-demo/vercel.json` configures SPA navigation/refresh, immutable object caching and manifest revalidation. Missing `/api/`, `/demo/` and `/assets/` resources remain 404 rather than falling back to the application shell. Only the static project is published; local backend and cache configuration are not deployment inputs.

## Validate an update

```bash
python3 scripts/check_vercel_clone.py
backend/.venv/bin/python -m pytest backend/app/tests/test_vercel_export.py -q
npm --prefix public-demo run build
npm --prefix public-demo run preview
```

In the preview, open each exported candidate through **Analyze candidate**, check Before/After image loading, NDVI/EVI, available native cells, cached calendar studies, filters, navigation and refresh. Check desktop/mobile layouts and the browser network panel for failed static objects or unintended backend requests. The deployed site should also preserve deep-link refresh and return 404 for absent API routes.

Update only after checking the allowlist, manifest omissions, source parity, object integrity and available scientific evidence. Historical verification reports and one-off browser/source comparison scripts are not part of the maintained repository documentation.
