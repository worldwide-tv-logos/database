# Roadmap: our own channel registry

## Vision

worldwide-tv-logos manages its channels itself: a registry of channels with **our own IDs**, the logos attached to
those IDs, and an automatic watch of new, renamed and closed channels. We no longer wait for iptv-org to accept a
channel before giving it a logo.

## Decisions

| Subject | Decision |
|---|---|
| Channel ID | Opaque and stable: `ch_` + 10 Crockford base32 characters (e.g. `ch_7k3m9q2x4p`). Never changes, never reused. |
| Readable name | A `slug` (`tf1.fr`, `bfmtv-lyon.fr`), unique, may change on a rename; never used as a key. |
| Other IDs | Only two kept: iptv-org (needed by the watch) and Wikidata (stable). **No guide IDs stored**: they change on the guides' side and we would have to follow them. |
| Guide matching | A `guides.json` index rebuilt every night (guide channel ID → likely `ch_` and logos, with a score), plus matching by name and country on the site for unknown guides. Derived, never maintained by hand. |
| iptv-org | A **source** only: its channels, feeds and issues tell us about new, renamed and closed channels. |
| Provider | This repository **never** connects to an IPTV provider. Channels seen at a provider arrive as requests with public information only (name, country, website), sent by canonical-catalog. |
| Hosting | Data and site on GitHub (Pages). A read-only API (FastAPI on Vercel) loads the published files; it never writes, and the site works without it. |
| Edits | Data still changes only through `uv run logos` commands, never by hand. |

## Steps

| # | Step | Goal | Status |
|---|---|---|---|
| 1 | [Channel registry](01-channel-registry.md) | `data/channels.csv` and `data/external_ids.csv`, filled from iptv-org | Done |
| 2 | [Logos on our IDs](02-logos-on-our-ids.md) | Logos stored and published under `ch_` IDs (old paths dropped) | To do |
| 3 | [iptv-org watch](03-iptvorg-watch.md) | New, renamed and closed iptv-org channels applied to the registry every day | To do |
| 4 | [Requests on our registry](04-requests.md) | Anyone can add or edit a channel without iptv-org | To do |
| 5 | [Status watch](05-status-watch.md) | Closed channels confirmed from several signals | To do |
| 6 | [Publication](06-publication.md) | `channels.json`, `guides.json`, and logo lookup from a guide ID or a name | To do |
| 7 | [canonical-catalog integration](07-catalog-integration.md) | The catalogue sends its unknown channels and stores our IDs | To do |
| 8 | [Lookup API](08-api.md) | Read-only FastAPI on Vercel: guide ID, free name or whole XMLTV list → channels and logos | To do |

Steps 1 and 2 come first and in this order; 3 to 6 can then be done in any order; 7 needs 4 and 6; 8 needs 6.

Update the status here **and** in the step's file in the same pull request as the code.
