# Step 2: logos on our IDs

**Status: to do** (needs step 1)

## Goal

`data/logos.csv`, `data/aliases.csv`, `data/rejected.csv` and the files in `logos/` use `ch_` IDs. Every command,
workflow and issue form works with them. No compatibility with the old iptv-org paths: nobody depends on them yet.

## How

- **One migration command** (`logos migrate-ids`, run once in a pull request): rewrites the three CSV files and
  moves `logos/<cc>/<iptv-id>…` to `logos/<cc>/<ch-id>…`, through the mapping of step 1.
- **Commands take a `ch_` ID or a slug**: `set`, `remove`, `reject`, `dismiss`, `find`, `seen-on`… resolve the slug
  to the `ch_` ID (`registry.resolve`).
- **Harvest and checks** work on registry channels instead of iptv-org units (`harvest/candidates.units`), so a
  channel absent from iptv-org can get a logo.

## Files to change

| File | Change |
|---|---|
| `worldwide_tv_logos/db.py` | logo key = `ch_` ID; paths |
| `worldwide_tv_logos/cli.py`, `ops.py` | `migrate-ids`; every command resolves IDs through the registry |
| `worldwide_tv_logos/harvest/candidates.py`, `sitecheck.py`, `run.py` | units from the registry |
| `worldwide_tv_logos/sources/*.py` | look up names, website and Wikidata ID from the registry |
| `worldwide_tv_logos/issues.py` | forms take any ID |
| `worldwide_tv_logos/site.py`, `.github/workflows/deploy.yml` | new paths |
| `.github/ISSUE_TEMPLATE/01-06` | "channel ID (`ch_` or slug)" |
| `tests/test_logos.py` | migration on a small sample, resolution of a slug |
| `README.md`, `CLAUDE.md`, `.github/docs/*.md` | IDs and paths |
