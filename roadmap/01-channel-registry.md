# Step 1: channel registry

**Status: to do**

## Goal

Every channel we follow has a `ch_` ID in `data/channels.csv`, with what anyone needs to match it on their side
(name, aliases, country, website). Its iptv-org and Wikidata IDs are in `data/external_ids.csv`. The registry starts
from iptv-org, so that nothing is lost when step 2 moves the logos.

## How

- **`data/channels.csv`**: `id, slug, name, country, status, parent, website, added, updated`.
  - `status`: `active` | `closed` | `merged` (with `parent` pointing to the channel it merged into).
  - `parent`: for an edition (regional, +1, HD of the same programmes), the main channel.
- **`data/external_ids.csv`**: `channel_id, source, external_id, method, added`.
  - `source`: `iptv-org`, `iptv-org-feed`, `wikidata` only. Guide IDs are **not stored**: they change on the guides'
    side; the matching with guides is rebuilt every night instead (step 6).
  - `method`: `import` (initial load), `match` (found automatically), `review` (confirmed by a person or Claude).
  - One `(source, external_id)` points to one channel only (checked by `validate`).
- **ID generator**: 10 random Crockford base32 characters (no I, L, O, U), redrawn on collision.
  Random rather than derived from the name: a rename never changes the ID.
- **Initial load** (`logos channels-init`): one `ch_` per iptv-org channel of the followed countries
  (`data/countries.csv`), plus its iptv-org ID and its Wikidata ID when iptv-org gives one; aliases from iptv-org's
  `alt_names` go to `data/aliases.csv`.
- **Merge-friendly**: both files go through `merge-data --files` like `logos.csv` (three-way row merge).

## Files to change

| File | Change |
|---|---|
| `worldwide_tv_logos/db.py` | `Channel` and `ExternalId` rows, load/save, `merge_rows` for both files |
| `worldwide_tv_logos/registry.py` (new) | ID generator, slug, lookup by any external ID |
| `worldwide_tv_logos/cli.py` | `channels-init`, `channel-add`, `channel-edit`, `channel-map`; `validate` checks both files |
| `.github/scripts/sync.sh`, `merge.sh` | include the two new files |
| `tests/test_logos.py` | ID format, uniqueness, one mapping per external ID, merge |
| `CLAUDE.md`, `MAINTAINING.md` | the registry and its commands |
