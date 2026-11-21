# Contributing

## Add or replace a logo

1. Find the channel's iptv-org ID on [iptv-org.github.io](https://iptv-org.github.io/) (e.g. `France3.fr`, and
   the feed ID for a regional version, e.g. `Alsace`). A channel that is not in iptv-org must be added there first.
2. Open the [logo form](../../issues/new?template=01_logos_add.yml) with a direct `https://` link to the image.
3. A bot checks the request within a minute (`check:passed` or a comment explaining what to fix).
4. A maintainer approves it (`approved`); the next nightly run downloads the image, converts it, commits it and
   closes the issue with a summary.

A logo must be on a **transparent background** (a white frame is removed automatically), at least **500 px** on its
longest side; **SVG is preferred**. Use the version currently on air.

## Remove a logo / link a guide ID

- [Remove form](../../issues/new?template=02_logos_remove.yml): wrong or outdated logo.
- [Alias form](../../issues/new?template=03_aliases_add.yml): the ID a TV guide uses for the channel.

## Many logos at once (pull request)

```sh
uv sync
uv run logos import my-logos.csv     # CSV: channel,feed,origin  (origin: https URL or local file)
uv run logos validate
```

Commit `data/`, `logos/` and `sources/` together. Never rename or edit files by hand: they are derived from
`data/logos.csv` and the checks refuse anything else.

## Data scheme

### data/logos.csv

| Field | Description | Example |
|---|---|---|
| channel | iptv-org channel ID | `France3.fr` |
| feed | iptv-org feed ID, empty for the channel itself | `Alsace` |
| variant | empty, or `white` (made automatically for mostly dark logos) | `white` |
| width, height | size of the PNG in pixels | `1200`, `412` |
| origin | where the original comes from: URL, or `issue #N` | `issue #12` |
| added, updated | dates (YYYY-MM-DD) | `2026-11-21` |

### data/aliases.csv

| Field | Description | Example |
|---|---|---|
| epg_id | ID of the channel in the guide | `France3-Alsace.fr` |
| source | short name of the guide | `iptv-epg-fr` |
| channel, feed | iptv-org IDs | `France3.fr`, `Alsace` |

More: [scripts](.github/docs/scripts.md), [workflows](.github/docs/workflows.md).
