# Step 1: channel registry

**Status: done** (2026-11-23: 27,782 entries, 17,156 channels and 10,626 editions, 208 countries)

## Goal

Every channel we follow has a `ch_` ID in `data/channels.csv`, with what anyone needs to match it on their side
(name, aliases, country, website). Its iptv-org and Wikidata IDs are in `data/external_ids.csv`. The registry starts
from iptv-org, so that nothing is lost when step 2 moves the logos.

## How

- **`data/channels.csv`**: `id, slug, name, aliases, country, status, parent, website, added, updated`.
  - `aliases`: other names, separated by `;` (iptv-org's `alt_names` at first).
  - `status`: `active` | `closed` | `merged` (with `parent` pointing to the channel it became).
  - `parent`: for an edition (regional or market version: iptv-org feeds other than the main one, the quality and
    timeshift ones, HD, 4K, +1, excepted), its main channel. An edition takes the country it is broadcast in when
    iptv-org gives exactly one (`24kitchen-bulgary.bg`), else its channel's; it follows iptv-org until edited here.
- **`data/external_ids.csv`**: `channel_id, source, external_id, method, added`.
  - `source`: `iptv-org`, `iptv-org-feed`, `wikidata` only. Guide IDs are **not stored**: they change on the guides'
    side; the matching with guides is rebuilt every night instead (step 6).
  - `method`: `import` (initial load), `match` (found automatically), `review` (confirmed by a person or Claude).
  - One `(source, external_id)` points to one channel only.
- **ID**: `ch_` + 10 random Crockford base32 characters (no I, L, O, U), from `secrets`, redrawn on collision. Like a
  UUID v4, but short and readable; random rather than derived from the name, so a rename never changes it.
- **Slug**: from the name (`france-3-alsace.fr`, `canal-plus-sport.fr`), `-2` added for a homonym in the same
  country (3 cases at the first load).
- **Load** (`logos channels-init`): the channels and editions of the followed countries, every channel or edition
  that has a logo, and the channels the closed ones were replaced by (`merged`). It only adds what is missing: the
  nightly `update` runs it, so new iptv-org channels and new logos are registered the same night.
- **Wikidata IDs**: iptv-org gives none; they are added by `channel-map` (and later by the sources that find them).
- **Merge-friendly**: both files are merged row by row like `logos.csv` (`merge-data`).

## Files changed

| File | Change |
|---|---|
| `worldwide_tv_logos/db.py` | `Channel` and `ExternalId` rows, load/save, row-by-row merge |
| `worldwide_tv_logos/registry.py` (new) | ID, slug, resolution of any ID, `init`, checks |
| `worldwide_tv_logos/cli.py` | `channels-init`, `channel`, `channel-add`, `channel-edit`, `channel-map`; `validate` and `merge-data` cover both files |
| `.github/workflows/update.yml` | `channels-init` every night |
| `tests/test_logos.py` | IDs, slugs, load run twice, merged channels, checks, merge, commands |
| `CLAUDE.md`, `MAINTAINING.md`, `.github/docs/scripts.md` | the registry and its commands |
