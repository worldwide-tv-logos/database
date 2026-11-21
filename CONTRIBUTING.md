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

## All the forms

| Form | Use it to | Applied by the bot |
|---|---|---|
| [logos/add](../../issues/new?template=01_logos_add.yml) | add the logo of a channel that has none here | yes |
| [logos/edit](../../issues/new?template=02_logos_edit.yml) | replace a logo (new branding, better quality, wrong logo) | yes |
| [logos/remove](../../issues/new?template=03_logos_remove.yml) | remove a wrong or outdated logo | yes |
| [logos/request](../../issues/new?template=04_logos_request.yml) | ask for a logo when you do not have the image | no: someone answers with logos/add |
| [aliases/add](../../issues/new?template=05_aliases_add.yml) | link the ID a TV guide uses to the iptv-org ID | yes |
| [aliases/remove](../../issues/new?template=06_aliases_remove.yml) | remove a wrong alias | yes |

### A channel that is not in iptv-org

Every logo is attached to an iptv-org channel, so that its name is stable and shared with guides and playlists.
[Add the channel to iptv-org](https://github.com/iptv-org/database/issues/new?template=01_channels_add.yml) first;
once it is there (usually the next day), submit its logo here.

### A channel without a TV guide ID

Nothing to do: a guide ID is optional. Logos are found by iptv-org ID; an alias is only useful when a guide uses a
different ID for the channel.

## Many logos at once (pull request)

```sh
uv sync
uv run logos import my-logos.csv     # CSV: channel,feed,origin  (origin: https URL or local file)
uv run logos validate
```

Commit `data/`, `logos/` and `sources/` together, with a commit message in English. Never rename or edit files by hand: they are derived from
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
