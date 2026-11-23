# Step 7: canonical-catalog integration

**Status: to do** (needs steps 4 and 6)

## Goal

canonical-catalog uses our IDs for its channels and sends the ones we do not know, so that every channel it serves
gets a logo, without this repository ever seeing the provider.

## How

- **In canonical-catalog**, not here:
  - reads `channels.json` / `guides.json` and stores our ID in `channel_external_ids` (`source = wtl`), matched
    through the iptv-org IDs and guide IDs it already holds;
  - for a served channel with no match, opens a `channels: add` request with **public information only** (name,
    country, website, guide ID): no stream, line or provider name;
  - reads the logo from our published paths.
- **Here**: the request is checked and applied like any other (step 4). No catalogue ID is stored here: the
  catalogue keeps the link on its side.

## Files to change

| Project | File | Change |
|---|---|---|
| canonical-catalog | `live/logos/` | read `channels.json` / `guides.json`, store `wtl` IDs, take the logo |
| canonical-catalog | new command | open the requests (public information only), daily in the worker |
| canonical-catalog | `docs/roadmap/` | its own step |
