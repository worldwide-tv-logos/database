# Step 6: publication

**Status: done**

## Goal

Users find a channel and its logo from what they already hold: our ID, an iptv-org or Wikidata ID, **the channel ID
of their programme guide**, or just the channel name and country. They no longer need their own matching system.

## What was done

- **`channels.json`**: every channel with its status, parent, website, aliases, logos, iptv-org and Wikidata IDs.
  An edition without a logo of its own gets its main channel's logo, written out (`logo_from: <parent ch_>`).
- **`guides.json`**, rebuilt by every export (`guides.py`, never stored in `data/`): for each guide channel ID, the
  likely `ch_` IDs with a score:
  - `1.0` the aliases confirmed by review (`data/aliases.csv`, kept: they win over the automatic matching, and those
    of guides not read are published too);
  - `0.95` the same iptv-org ID (case aside);
  - `0.9` one channel of the country with this main name; quality and timeshift marks (`HD`, `+1`, a final `TV`) are
    dropped, so `TF1 + 1` gives TF1; a guide without names gives its ID's name (`France3.fr`);
  - `0.7` another name only (iptv-org's other names are loose: `Euronews` is an other name of Euronews Russian), or
    one channel of another country; `0.5` two or three candidates; a name of more than three channels is left out.
  Guides read: the iptv-epg guides of the followed countries and the xmltv.se IDs. First measure: 3,301 guide
  channels matched, 2,168 from 0.9 (iptv-epg-fr: 274 of 485, 214 from 0.9; the others are mostly channels not in
  the registry, such as event channels).
- **Site search**: also finds a channel by its iptv-org, Wikidata and guide IDs (from 0.9), an edition's under its
  channel (5th column of `search.json`).
- **`logos lookup <text> [--country]`**: the same lookup from the command line (`guides.lookup`, used by step 8).
- **Deploy**: `.cache` kept between runs (`actions/cache`), the guides being downloaded once a day.
- **Stable format**: documented fields, one `version` field; new fields added, never renamed.

Left for later: epgshare01 and other guides (a line in `export`), and a search by name plus country on the site for
guides we do not know (the API of step 8 does it).

## Files changed

| File | Change |
|---|---|
| `worldwide_tv_logos/guides.py` (new) | match guide channels, score, `build`, `lookup` |
| `worldwide_tv_logos/site.py` | `channels.json`, `guides.json`, other IDs in `search.json` |
| `worldwide_tv_logos/cli.py` | `export` builds the guides, `logos lookup` |
| `site/app/composables/useCatalog.ts`, `site/app/app.vue` | search on the other IDs; an ID found in the channels hides the docs results |
| `.github/workflows/deploy.yml` | `.cache` between runs |
| `README.md`, `site/content/docs/1.getting-started/3.api.md`, `.github/docs/scripts.md` | formats and examples |
| `tests/test_logos.py` | matching, lookup, `channels.json` |
