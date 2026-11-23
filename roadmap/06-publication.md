# Step 6: publication

**Status: to do** (needs step 2)

## Goal

Users find a channel and its logo from any ID they hold (ours, iptv-org, a guide's, Wikidata), as a file and on the
site.

## How

- **`channels.json`** published with the site: every channel with its status, parent, website, logos and every
  mapped ID. A small `ids.json` index maps each external ID to its `ch_` ID.
- **Site**: channel page by `ch_` ID; search box accepting any ID; closed channels shown as such.
- **Stable format**: documented fields, one `version` field; new fields added, never renamed.

## Files to change

| File | Change |
|---|---|
| `worldwide_tv_logos/site.py` | `channels.json`, `ids.json`, channel pages, search |
| `.github/workflows/deploy.yml` | publish both files |
| `README.md` | format and examples |
| `tests/test_logos.py` | export shape, every ID resolves |
