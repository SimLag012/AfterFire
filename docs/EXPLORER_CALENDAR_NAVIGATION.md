# Explorer selection memory and candidate calendars

Explorer automatically stores its current query in `afterfire-last-explorer` on this device. Returning through the analysis back link, global navigation, logo or a bare `/explorer` restores the last selected bounding box, label, circle, dates and camera. An explicit shared `territory` takes precedence; manual Save view remains independent.

Candidates have a dedicated panel with a permanent heading. Opening or closing Fire data does not hide the candidate list. Long lists scroll separately. The Hotspot calendar toolbar action brings the loaded-observation calendar into view without hiding candidates.

The Explorer calendar bins the same detection array supplied to the observation map into UTC days. It follows dates/instrument filters and the pinned bounding box. A circle narrows the group to its exact radius intersected with that bounding box, including when the circle crosses a selection edge. A wholly outside circle acquires no observations. Camera movement does not change acquisition bounds. Calendar month choices include empty months within the selected interval; counts describe loaded records, not fires or guaranteed absence of fire.

Candidate analysis includes its own original-observation calendar and an expandable historical Fire Activity Calendar. Existing historical acquisition, provenance, uncertainty and missing-data states remain available there. Reading cached studies does not replace the saved Explorer selection or rewrite the candidate URL. Historical acquisition still requires an explicit action. Truncated monthly records and the archive's 2,000-record display limit remain labelled as partial.

## Verification

- TypeScript/Vite production build and local Docker frontend build.
- `scripts/verify_explorer_calendar_navigation.cjs`: controlled hotspot fixtures at 1440×900 and 390×844; whole-area versus circle counts, mouse/touch circle drawing, persistent candidate heading, automatic return through logo/navigation, reload, explicit shared-view precedence, no outside-box acquisition, partial archive labels, and cached historical studies inside candidate analysis. Fixtures verify UI behavior, not NASA calibration or completeness.
- `scripts/verify_pinned_territory.cjs`: actual Spain search extents, full-country Return control, zero new hotspot HTTP requests during pan/zoom, strict small bounding boxes, saved view and Data & Sources return.
- `scripts/verify_unified_browser.cjs`: 15 checks against the actual local API and retained observations, including candidate/historical calendar counts, Recovery/Reburn, full Data & Sources with API configuration, return selection, and legacy saved comparison redirects. No historical or analysis acquisition is requested by these checks.

Recovery computation and the backend scientific pipeline are unchanged. The application is rebuilt locally; no remote publication is part of this change.
