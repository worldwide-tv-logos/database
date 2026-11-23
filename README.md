<p align="center"><img src="site/public/logo-mark.svg" width="96" alt="Worldwide TV Logos"></p>

<h1 align="center">Worldwide TV Logos</h1>

Clean TV channel logos from all over the world, under a channel ID of our own that never changes, with each
channel's [iptv-org](https://github.com/iptv-org/database) ID when it has one.

**Browse them by country, channel and edition: https://worldwide-tv-logos.github.io/database/** (every page has
buttons to add, replace or request a logo).

- **Transparent background**, trimmed to the drawing, high resolution (SVG originals rendered at 1200 px, longest
  side 500 to 2000 px, never upscaled).
- **Readable everywhere**: a white variant for logos that are black, grey or very dark (navy letters), so they stay
  readable on dark screens; a logo made for dark screens (white letters) gets a dark version for light ones.
- **One stable address per logo**, derived from our channel ID: a channel renamed or moved keeps it.
- **Current logos only**: old brandings are refused (dated by Wikidata or by the file name), and every logo is
  checked by eye on contact sheets before it is published.
- **Aliases** for the IDs used by TV guides (EPG).

## Use

```
https://worldwide-tv-logos.github.io/database/logos/<id>[.white].png
```

`<id>` is our channel ID (`ch_` and 10 characters, shown on each channel page; `data/channels.csv`): it never
changes and is never reused.

| Logo | Address (after `https://worldwide-tv-logos.github.io/database/`) |
|---|---|
| TF1 (`ch_rxxkmndvjh`, iptv-org `TF1.fr`) | `logos/ch_rxxkmndvjh.png` |
| France 3 Alsace (`ch_dhk02zjhwa`, iptv-org `France3.fr@Alsace`) | `logos/ch_dhk02zjhwa.png` |
| its version for dark backgrounds | `logos/ch_dhk02zjhwa.white.png` |

An edition without its own logo uses the logo of its channel (`parent` in `logos.json`). Images are served by GitHub Pages (a CDN); the same
paths also work under `https://raw.githubusercontent.com/worldwide-tv-logos/database/main/`, which is not meant for
heavy use.

### API

| File | Content |
|---|---|
| [`logos.json`](https://worldwide-tv-logos.github.io/database/logos.json) | every logo: `channel` (our ID), `slug`, `iptv` (its iptv-org ID), `country`, `parent` (an edition's channel), `variant`, `width`, `height`, `format`, `url`, `updated` |
| [`aliases.json`](https://worldwide-tv-logos.github.io/database/aliases.json) | TV guide IDs of channels: `epg_id`, `source`, `channel` |

Static files, no key, updated every night. Details and examples: [API page](https://worldwide-tv-logos.github.io/database/docs/getting-started/api).

## Where the logos come from

| Source | Used for |
|---|---|
| Contributors | logo requests through the [issue forms](../../issues/new/choose) |
| [iptv-org](https://github.com/iptv-org/database) | the logos listed with each channel |
| [iptv-epg](https://iptv-epg.org) | the logos of its TV guides, by country (with their permission) |
| [Wikidata](https://www.wikidata.org) / Wikimedia Commons | official logos with their dates (old ones are refused), and Commons files named after the channel |
| Wikipedia | the logo of the channel's article, in the country's languages then English (many are hosted by one Wikipedia only) |
| [picons](https://github.com/picons/picons), [xmltv.se](https://gitlab.com/xmltv-se/open-source/channel-logos) | collections of channel logos, matched by name |
| The channel's own website | its current logo |

Every candidate goes through the same preparation and checks; the best one is kept (SVG first, then the largest),
then reviewed on contact sheets (each logo on a dark and a light background). The iptv-org logos of every country
that pass these checks (SVG or at least 500 px) were added in bulk without a review of their own, iptv-org reviewing
them already; a wrong or outdated one is fixed through the issue forms or by the weekly harvest.

## How it is maintained

The repository runs by itself with [GitHub Actions](.github/docs/workflows.md); Claude (Anthropic's AI) reviews and
prepares the changes following [CLAUDE.md](CLAUDE.md), and maintainers keep the last word.

| When | What |
|---|---|
| Every request | automatic checks (IDs, image), then Claude's review: clear cases are approved, doubts go to a maintainer; a wanted logo is looked for by Claude |
| Every night | approved requests applied, data validated, website and API published |
| Sunday | harvest: new and better logos for every followed country, one pull request per country |
| Wednesday | hunt: a weekly slice of the channels still without a logo, and of the small logos for a sharper version, every source including their website |
| Thursday | website check: a weekly slice of current logos looked for on their channel's website; a newer logo there is reviewed and applied |
| Friday | iptv-epg check: logos whose TV guide shows a newer drawing, for a slice of 30 countries |
| Monday | changes on the iptv-org side (channel renamed, replaced or removed) applied |
| 1st of the month | activity report as an issue |
| Every day | health check: a failed workflow, or a pull request or issue waiting for a maintainer, opens (or updates) one issue labelled `health`, closed when all is clear |

Pull requests prepared by Claude contain data only (never code or workflows). Claude decides every logo itself:
it keeps the right ones, replaces or rejects the others (a doubt is rejected, never published: the channel is
simply looked for again the next week), and the pull request is merged automatically once the data validates. A
maintainer is needed only when something is broken (label `needs:maintainer`). A logo
refused in review is recorded in `data/rejected.csv` and never proposed again.

## Contribute

Pick a channel in [missing/](missing/) or on the website, and submit its logo with the
[form](../../issues/new?template=01_logos_add.yml): the request is checked within a minute, reviewed, and the logo
is added the next night. You can also just [ask for a logo](../../issues/new?template=04_logos_request.yml).
Details in [CONTRIBUTING.md](CONTRIBUTING.md).

Maintainers: [MAINTAINING.md](MAINTAINING.md). Everyone: [code of conduct](CODE_OF_CONDUCT.md).

## Layout

```
data/channels.csv    our channels: id, slug, name, aliases, country, status, parent, website, added, updated
data/external_ids.csv their iptv-org and Wikidata IDs: channel_id, source, external_id, method, added
data/logos.csv       the index: channel, variant, width, height, origin, added, updated
data/aliases.csv     guide IDs -> our channel IDs: epg_id, source, channel
data/countries.csv   countries followed (missing/ lists, weekly harvest and hunt)
data/rejected.csv    logos refused in review, never proposed again
logos/               the logos (PNG), named after our channel ID
sources/             the originals they were built from (same name, original extension)
missing/<cc>.md      channels of the country that still have no logo here
roadmap/             the plan: our own channel registry
site/                the website (Nuxt, from the Nuxt UI docs template; its data is built by `logos export`)
worldwide_tv_logos/  the tools (`uv run logos --help`, see .github/docs/scripts.md)
tests/               tests of the tools
```

File names and paths are **always derived** from `data/logos.csv`; a file that does not match is refused by the
checks.
