# Redirect Ledger

[![CI](https://github.com/KanadeK/redirect-ledger/actions/workflows/ci.yml/badge.svg)](https://github.com/KanadeK/redirect-ledger/actions/workflows/ci.yml)

Audit an exact-path redirect CSV **before** migrating a website. Find loops, ambiguous sources, chains, and destinations absent from your new-site inventory. Generate a conservative replacement CSV and audit it again, entirely offline.

[中文说明](README.zh-CN.md) · Python 3.11+ · MIT · No runtime dependencies

For maintainers moving documentation, blog posts, or static pages who already have an old-path → new-path table. [Google's migration guide](https://developers.google.com/search/docs/crawling-indexing/site-move-with-url-changes) recommends preparing that mapping and avoiding redirect chains.

## Install and try

Clone this repository, then install from source in an isolated environment:

```sh
git clone https://github.com/KanadeK/redirect-ledger.git
cd redirect-ledger
python -m venv .venv
```

Activate it with `source .venv/bin/activate` on macOS/Linux or `.venv\Scripts\Activate.ps1` in Windows PowerShell. Then:

```sh
python -m pip install .
redirect-ledger examples/redirects.csv --inventory examples/live-paths.txt
redirect-ledger examples/redirects.csv --inventory examples/live-paths.txt --format json --plan flattened.csv
redirect-ledger flattened.csv --inventory examples/live-paths.txt --strict
```

The first command reports **4 rules, 0 errors, 1 warning**. The plan changes `/old-guide → /guide → /docs/guide` to `/old-guide → /docs/guide`. `/old-news` remains a 302. The final command exits 0 with no chain warnings. Delete `flattened.csv` after trying the example. `python -m redirect_ledger` is equivalent to the installed command. The release also includes an installable wheel; a package-index publication is not required.

## Input contract

UTF-8 CSV (optional BOM), with exactly this header and three fields per record:

```csv
source,target,status
/old-guide,/guide,301
/guide,/docs/guide,301
/offsite,https://example.org/archive,308
```

Sources are root-relative exact URL paths. Targets are root-relative paths or absolute HTTP(S) URLs. Supported statuses: 301, 302, 303, 307, 308. A repeated canonical source is a fatal input error, including identical duplicates. CSV quoting is supported. Surrounding whitespace is not trimmed.

Paths retain case and trailing slashes. Unreserved escapes are decoded (`/%7e` becomes `/~`); other escapes are uppercased. UTF-8 path characters must be percent-encoded. Repeated slashes, dot segments, encoded separators, encoded percent/control/whitespace, query strings, fragments, backslashes, wildcards, brackets, and unsupported URL characters are rejected. This deliberately small model prevents silently guessing your host's routing semantics.

The optional inventory is a UTF-8 text file, **one live root-relative path per line**, with empty lines allowed. It must contain at least one unique canonical path. Internal terminals must be present. A redirect source also listed as a live page is an `inventory_shadowed` error: decide explicitly whether it is a page or redirect. Without an inventory, internal terminal existence is marked `internal_unchecked`.

Absolute URL targets are always external terminals, even if they happen to use your own hostname. They are marked `external_unchecked` and never fetched. Convert same-site absolute URLs to root paths before auditing if you want graph and inventory checks to include them.

## Findings and plans

`--format json` emits schema version 1, a summary, cycles, findings, and one record per source. Records include original target/status/CSV ending line, terminal, hop count, cycle identity, inventory outcome, and proposed plan target. A tail feeding a loop is marked with that loop's identity; no false terminal is invented. Paths are included in reports, so review them before sharing.

`--plan new.csv` writes a **complete** replacement mapping to a new file. It refuses existing paths and all audits containing errors. It shortens a chain only if every hop has the **same** permanent status (all 301 or all 308). Temporary and mixed-status chains keep their original next hop. Review the file and validate it against the same inventory before translating it to your hosting platform's configuration. The tool never deploys rules or edits input files.

Exit statuses:

| Code | Meaning |
| --- | --- |
| 0 | No errors; warnings allowed unless `--strict` |
| 1 | Audit errors, or warnings with `--strict` |
| 2 | Invalid/unsupported input, file access, refused plan, or command usage |

Input/file errors use stderr (JSON when `--format json` is selected); successful audit reports use stdout. `--strict` can return 1 after successfully writing a plan containing chain corrections.

## Limits and alternatives

Version 0.1.0 supports one logical site's **exact paths without queries**. It does not simulate regex rules, first-match precedence, rewrites, query forwarding, host-specific normalization, authentication, or whether a live server actually serves a URL. An inventory is your asserted set of live paths, not proof of an HTTP 200 response. Do a deployed-site crawl after migration.

Each input is limited to 16 MiB, 100,000 rules or inventory paths, and 4,096 characters per path/target. Graph walks are iterative and avoid expanded quadratic traces; deterministic sorting adds O(n log n) time. Output size grows with rules and findings. Writes refuse existing destinations but are not crash-atomic.

[Repomatic](https://github.com/kdeldycke/repomatic) audits actual Cloudflare `_redirects` semantics. Crawlers such as Screaming Frog inspect deployed responses. Redirect Ledger addresses a narrower workflow: reviewing a vendor-neutral proposed CSV graph against a new-site path inventory, before a server exists. It contains no copied implementation from these projects.

## Development and removal

See [CONTRIBUTING.md](CONTRIBUTING.md). The suite includes real local HTTP redirects, 150 seeded random graphs checked against an independent naive walker, a 20,000-hop chain, malformed inputs, and plan re-auditing. CI tests Linux (3.11/3.14), Windows (3.13), and macOS (3.13), then installs the built wheel into a fresh environment and repeats the suite. See CI for actual run results.

To uninstall, run `python -m pip uninstall redirect-ledger`. Deactivate and remove the dedicated `.venv` directory if no longer needed. The runtime creates no database, cache, network service, or background process; only the optional plan file needs cleanup.

Security reports: [SECURITY.md](SECURITY.md). Runtime dependencies: none; development tools are pinned separately in `requirements-dev.txt`.
