# Step 2: logos on our IDs

**Status: done** (2026-11-23: 15,184 logos, 11,344 originals, 204 guide aliases and 300 refused URLs moved)

## Goal

`data/logos.csv`, `data/aliases.csv`, `data/rejected.csv` and the files in `logos/` and `sources/` use `ch_` IDs.
Every command, workflow and issue form works with them. No compatibility with the old iptv-org paths: nobody
depends on them yet.

## How

- **Flat paths**: `logos/<ch_id>[.white].png`, `sources/<ch_id>.<ext>`. No country folder: a channel moved to
  another country keeps its path, which never changes.
- **One migration command** (`logos migrate-ids`, run once): rewrote the three CSV files and moved the files through
  the mapping of step 1. One refused URL was left out (`Nickelodeon.fr@Plus1`, a timeshift version not registered).
- **Commands take any ID**: `set`, `remove`, `reject`, `dismiss`, `find`, `seen-on`, `sheet`, `import` and the issue
  forms resolve our ID, a slug or an iptv-org ID (`France3.fr@Alsace`) to the `ch_` ID (`ops.channel_of`). An
  iptv-org ID not registered yet makes a request wait (`waiting:channel`); anything else is refused.
- **Harvest and checks** work on registry channels (`registry.units`): harvest, hunt, bulk, epg-check, site-check,
  guide aliases and `missing/`. A channel absent from iptv-org can now get a logo. The iptv-org ID of a unit is still
  used to read iptv-org's own logos and the guide's same-ID channel.
- **`move`** now moves the logos of a channel registered twice to the other one; a rename keeps its ID and needs
  nothing.
- **`channels-init`** only registers iptv-org channels of the followed countries: every logo now belongs to a
  registry channel (`validate` refuses one that does not).
- **Publication**: `logos.json` gives `channel` (our ID), `slug`, `iptv`, `country`, `parent`, `variant`, size, `url`,
  `updated` (no longer a copy of iptv-org's format); the website lists registry channels with their editions.

## Files changed

| File | Change |
|---|---|
| `worldwide_tv_logos/db.py` | logo key = (`ch_` ID, variant); flat paths; aliases on our IDs |
| `worldwide_tv_logos/migrate.py` (new, one-off) | the migration |
| `worldwide_tv_logos/registry.py` | `unit`, `units`, `iptv_id`, `family_name`, `iptv_units`; logos and aliases checked |
| `worldwide_tv_logos/ops.py`, `issues.py`, `cli.py` | every command and form on our IDs |
| `worldwide_tv_logos/harvest/*.py`, `sources/*.py` | units from the registry |
| `worldwide_tv_logos/site.py`, `site/app/**` | website data and pages from the registry |
| `.github/ISSUE_TEMPLATE/01-06`, `validate_issue.yml`, `changes.yml` | one channel ID field, `waiting:channel`, renames |
| `tests/test_logos.py` | a test registry; every test on our IDs |
| `README.md`, `CONTRIBUTING.md`, `CLAUDE.md`, `.github/docs/scripts.md`, `site/content/**` | IDs and paths |
