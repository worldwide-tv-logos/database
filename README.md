# worldwide-tv-logos

Clean TV channel logos, keyed by [iptv-org](https://github.com/iptv-org/database) channel ID.

- **Transparent background**, trimmed to the drawing, high resolution (SVG originals rendered at 1200 px).
- **One stable address per logo**, derived from the iptv-org ID: no guessing, no renaming.
- **A white variant** for logos that are mostly black or grey, so they stay readable on dark screens.
- **Aliases** for the IDs used by TV guides (EPG) that differ from iptv-org.

## Use

```
https://raw.githubusercontent.com/worldwide-tv-logos/database/main/logos/<cc>/<channel>[@<feed>][.white].png
```

| Logo | Address (after `…/main/`) |
|---|---|
| TF1 | `logos/fr/TF1.fr.png` |
| France 3 Alsace (feed `Alsace` of `France3.fr`) | `logos/fr/France3.fr@Alsace.png` |
| …its version for dark backgrounds | `logos/fr/France3.fr@Alsace.white.png` |

The whole index as JSON: `https://worldwide-tv-logos.github.io/database/logos.json`
(and `aliases.json` for guide IDs).

## Layout

```
data/logos.csv       the index: channel, feed, variant, width, height, origin, added, updated
data/aliases.csv     guide IDs -> iptv-org IDs: epg_id, source, channel, feed
data/countries.csv   countries followed in missing/
logos/<cc>/          the logos (PNG), named after their iptv-org ID
sources/<cc>/        the originals they were built from (same name, original extension)
missing/<cc>.md      iptv-org channels of the country that still have no logo here
worldwide_tv_logos/         the tools (`uv run logos --help`)
tests/               tests of the tools
```

File names and paths are **always derived** from `data/logos.csv`; a file that does not match is refused by the
checks.

## Contribute

Pick a channel in [missing/](missing/) and submit its logo with the
[form](../../issues/new?template=01_logos_add.yml): the request is checked automatically, and once approved the logo
is downloaded, converted and added the next night. Details in [CONTRIBUTING.md](CONTRIBUTING.md).
