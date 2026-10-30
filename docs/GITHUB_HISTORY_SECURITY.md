# Git history security — 2026-10-30

Verified remote: `https://github.com/SimLag012/AfterFire`, branch `main`.
The repository had two published commits, no tags, pull requests, forks,
branch protections or rulesets. The owner confirmed a coordinated update
window with the other writer (`aresthebellator`).

Before: `dff43cf22fd6dccae71002679dde275ad6796ef8`.
Clean checkpoint: `9f34464355348ee692cffe803eb3c1593ed56663`.
First changed commit: `9797a98ff2525fa4a730e2410037c78ee8d82483`.

A private local backup contains the full working copy, scientific data and a
verified `git bundle --all`. It contains contaminated history: never publish it.
Its location and machine-readable audit are held outside the repository under
`~/.local/state/afterfire-security/`. The parent directory has mode 0700.

`git-filter-repo` 2.47.0 ran in a separate fresh mirror with
`--sensitive-data-removal --replace-text` and `--replace-message`.
The temporary replacement file was private and outside Git. A scan of all 543
reachable objects found zero exact matches; all 163 historical application file
versions were compared with the originals, allowing only the secret replacement.
Local snapshot tree refs were preserved and scanned too.

Only `refs/heads/main` was pushed, using an explicit old-SHA force-with-lease.
The resulting remote SHA was verified. All 289 local modified/untracked entries
were preserved. The old value was also cleared from the private backend `.env`.
Credential revocation has **not** been independently verified: revoke/rotate the
exposed credential through NASA FIRMS before using a replacement.

## Other clones and GitHub caches

Collaborators should reclone the clean repository and reapply unpublished work
as patches. Do not merge old history or push old tags/branches. The verified
backup is for private recovery only.

Rewriting branches does not prove physical deletion from GitHub caches or other
clones. If cached views remain and removal is eligible, supply GitHub Support
with the repository, the first changed commit above and affected PR count (zero
at audit time). No Support request has been submitted by this agent.

Procedure: [GitHub sensitive-data removal](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository).

## Prevention

Keep credentials in ignored `.env` files or a secret manager. Templates must use
empty values or obvious placeholders. Never put secrets in screenshots, URLs or
logs. Enable GitHub secret scanning/push protection where available (not enabled
automatically here). Each clone should run:

```sh
git config core.hooksPath .githooks
python3 scripts/check_secrets.py --all
```

The hook scans staged blobs; CI scans all tracked blobs. These conservative
checks catch environment files, FIRMS literals, GitHub tokens and private keys;
they do not claim to detect every possible credential format.
