# Contributing

## Add or replace a logo

1. Find the channel on the [website](https://worldwide-tv-logos.github.io/database/countries): its ID, e.g.
   `ch_dhk02zjhwa` for France 3 Alsace. The forms take this ID only; the buttons of the channel's page fill it in.
2. Open the [logo form](../../issues/new?template=01_logos_add.yml) with a direct `https://` link to the image.
3. A bot checks the request within a minute (`check:passed` or a comment explaining what to fix).
4. A maintainer approves it (`approved`); the next nightly run downloads the image, converts it, commits it and
   closes the issue with a summary.

A logo must be on a **transparent background** (a white background is removed automatically), at least **500 px** on its
longest side; **SVG is preferred**. Use the version currently on air.

## All the forms

| Form | Use it to | Applied by the bot |
|---|---|---|
| [logos/add](../../issues/new?template=01_logos_add.yml) | add the logo of a channel that has none here | yes |
| [logos/edit](../../issues/new?template=02_logos_edit.yml) | replace a logo (new branding, better quality, wrong logo) | yes |
| [logos/remove](../../issues/new?template=03_logos_remove.yml) | remove a wrong or outdated logo | yes |
| [logos/request](../../issues/new?template=04_logos_request.yml) | ask for a logo when you do not have the image | no: someone answers with logos/add |
| [aliases/add](../../issues/new?template=05_aliases_add.yml) | link the ID a TV guide uses to a channel | yes |
| [aliases/remove](../../issues/new?template=06_aliases_remove.yml) | remove a wrong alias | yes |
| [channels/add](../../issues/new?template=07_channels_add.yml) | add a channel that is not listed yet (in iptv-org or not) | yes |
| [channels/edit](../../issues/new?template=08_channels_edit.yml) | correct a channel: new name, website, closed, main channel, iptv-org or Wikidata ID | yes |

### A channel that is not on the website

Add it with the [channels/add](../../issues/new?template=07_channels_add.yml) form (name, country, website; for a
regional version, its main channel): it gets its own ID the night after approval, without waiting for iptv-org. Then
add its logo, or let the weekly search find it. A renamed channel is corrected with channels/edit, never added again:
it keeps its ID and its logo. You never choose a channel's ID: it is made here.

Channels added to iptv-org are also registered every night (followed countries).

### A channel without a TV guide ID

Nothing to do: a guide ID is optional. An alias only helps to find a logo from the ID a guide uses.

## Many logos at once (pull request)

```sh
uv sync
uv run logos import my-logos.csv     # CSV: channel,origin  (channel: our ID, slug or iptv-org ID; origin: https URL or file)
uv run logos validate
```

Commit `data/`, `logos/` and `sources/` together, with a commit message in English. Never rename or edit files by hand: they are derived from
`data/logos.csv` and the checks refuse anything else.

## Data scheme

### data/logos.csv

| Field | Description | Example |
|---|---|---|
| channel | our channel ID (data/channels.csv) | `ch_dhk02zjhwa` |
| variant | empty, or `white` (made automatically for mostly dark logos) | `white` |
| width, height | size of the PNG in pixels | `1200`, `412` |
| origin | where the original comes from: URL, or `issue #N` | `issue #12` |
| added, updated | dates (YYYY-MM-DD) | `2026-11-21` |

### data/aliases.csv

| Field | Description | Example |
|---|---|---|
| epg_id | ID of the channel in the guide | `France3-Alsace.fr` |
| source | short name of the guide | `iptv-epg-fr` |
| channel | our channel ID | `ch_dhk02zjhwa` |

More: [scripts](.github/docs/scripts.md), [workflows](.github/docs/workflows.md).
