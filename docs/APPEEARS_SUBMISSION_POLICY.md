# AppEEARS submission policy

`AFTERFIRE_APPEEARS_SUBMISSION_ENABLED=false` is the backend and Compose default. The separate `AFTERFIRE_APPEEARS_ENABLED` setting permits reading existing subsets; it does not enable new submissions.

`AppEEARS.prepare()` rejects a missing manifest before product discovery, authentication or submission. `AppEEARS.request()` independently rejects POST `/task` before authentication or HTTP transport. This covers analysis, retry, worker recovery, history acquisition and maintenance scripts. Opt-in adapter tests explicitly enable the flag with a mocked transport. Production UI offers automatic verified-cache/direct-HDF access and explicit HDF selection.

Automatic acquisition uses existing HDFs, verified native subsets, previously submitted tasks and bounded direct NASA HTTPS HDFs. A saved incomplete manifest may resume its existing task/download without creating a replacement task. New missing sources never silently fall back to task submission. Missing sources beyond configured budgets produce a controlled explanation. Historical Reburn acquisition uses bounded direct HDF access when submission is disabled.

Existing remote tasks are neither cancelled nor deleted. NASA account settings are unchanged. The [official AppEEARS API documentation](https://appeears.earthdatacloud.nasa.gov/api/) was checked: no email-notification parameter or account email toggle was found there. No undocumented mute endpoint is used. Notifications from earlier requests or other account activity can still arrive.

The read-only audit found 27 AfterFire remote tasks and 25 locally recorded manifests. Full task parameters include AOIs: zero exact duplicate requests were found. Dates/layers alone produce apparent duplicates and must not be used to classify task duplication. See `appeears-task-audit-full.json`.

Zero new submissions is enforced and tested at the backend transport boundary. It is not a promise that previously submitted NASA tasks will stop sending mail.
