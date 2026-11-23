# Step 6: publication

**Status: to do** (needs step 2)

## Goal

Users find a channel and its logo from what they already hold: our ID, an iptv-org or Wikidata ID, **the channel ID
of their programme guide**, or just the channel name and country. They no longer need their own matching system.

## How

- **`channels.json`**: every channel with its status, parent, website, aliases, logos, iptv-org and Wikidata IDs.
- **`guides.json`**, rebuilt every night (never edited by hand, never stored in `data/`):
  - for each known public guide (iptv-epg, epgshare01, xmltv-se…) and each of its channel IDs: the likely `ch_`
    IDs with their logo and a score;
  - matching by name, aliases, country, Wikidata ID, with the rules already used by the sources
    (`sources/names.py`, ambiguous names across countries left out);
  - a guide that renames its IDs is picked up the next night: nothing to follow.
- **Site search**: a guide channel ID, any of our IDs, or a name plus a country (for guides we do not know); results
  ranked by score, with the logo.
- **Stable format**: documented fields, one `version` field; new fields added, never renamed.

The site is static (GitHub Pages): lookups are files and a search in the page, no server.

## Files to change

| File | Change |
|---|---|
| `worldwide_tv_logos/guides.py` (new) | read the public guides' channel lists, match, score |
| `worldwide_tv_logos/sources/iptvepg.py`, `xmltvse.py` | channel lists reused by `guides.py` |
| `worldwide_tv_logos/site.py` | `channels.json`, `guides.json`, channel pages, search |
| `worldwide_tv_logos/cli.py` | `logos guides-index`, `logos lookup <guide ID or name> --country` |
| `.github/workflows/deploy.yml` | build both files every night |
| `README.md` | format, examples ("I have the guide ID `TF1.fr`, which logo?") |
| `tests/test_logos.py` | export shape, matching (same name in two countries, aliases, renamed guide ID) |
