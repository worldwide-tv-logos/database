# Scripts

Python 3.12 and [uv](https://docs.astral.sh/uv/). `uv sync` once, then `uv run logos <command>`.

| Command | What it does |
|---|---|
| `logos validate [--offline]` | checks `data/`, every file in `logos/` and `sources/`, and (unless `--offline`) the IDs against iptv-org |
| `logos import <file.csv> [--pause 5]` | adds or replaces logos from a CSV `channel,origin[,label]` (channel: our ID, slug or iptv-org ID); `origin` is an `https://` URL or a local file; remote downloads are spaced by `--pause` seconds |
| `logos issue-validate --number N --labels L` | checks one request (body in `RAW_BODY`); writes the problems to `temp/errors.md` |
| `logos update` | applies the approved issues (`GITHUB_REPOSITORY`, `GITHUB_TOKEN`); writes `temp/processed.txt` and `temp/changes.json` |
| `logos notify --commit SHA` | comments each processed issue with what changed |
| `logos export [--offline]` | writes `.api/logos.json`, `.api/aliases.json` and (unless `--offline`) the data of the website (`countries.json`, `countries/<cc>.json`, `search.json`) and `missing/<cc>.md` |
| `logos harvest --country <cc> [--updates] [--max n] [--offset n] [--pause s] [--limit n]` | best logo of each channel of a country from every source (`worldwide_tv_logos/sources/`: Wikidata, Wikipedia and Commons for channels without a logo, iptv-org, iptv-epg, picons, xmltv-se; answers cached in `.cache/`), a weekly slice of `--max` (700) channels when the country has more, same checks as requests, into `temp/harvest/<cc>/` (manifest.csv for `logos import`, report.csv, doubts.csv, summary.md, contact sheets); `--updates` also proposes newer or better versions of current logos |
| `logos reject <channel> --base <main checkout> [--reason r] [--unconfirmed]` | refuse a logo of a harvest pull request: back to the logo of main, URL added to `data/rejected.csv`; `--unconfirmed` (no proof found, not wrong): only removed from the pull request, proposed again next time |
| `logos unreject [--channel id] [--date d] [--reason-contains text]` | remove rows of `data/rejected.csv`: those logos are proposed again |
| `logos sheet --changed [--base ref] \| --channels A,B \| --country cc` | contact sheets of logos of the repository (temp/sheets/) |
| `logos country-add <cc>...` | follow countries (`data/countries.csv`, iptv-org codes: `uk` for the United Kingdom): harvested and hunted every week |
| `logos site-check --country <cc>... [--size 150] [--review 20] [--offset n]` | current logos looked for on their channel's website (a weekly slice); those absent from it while the website shows another logo are listed for review in `temp/site-check/<cc>/` (summary.md, sites-NN.png) |
| `logos find <id>` | every candidate for a channel or feed from every source (`worldwide_tv_logos/sources/`, the channel website included), checked, ranked, on a contact sheet (temp/find/<id>/) |
| `logos set <id> <url or file>` | add or replace a logo (same preparation and checks as a request) |
| `logos move <id> <other id>` | move the logos, originals and aliases of a channel to another channel of the registry (a channel registered twice; a rename keeps its ID) |
| `logos remove <id>` | remove a logo with its variant, original and aliases |
| (harvest and hunt) | work on channels **and editions** (feeds other than the main one, named after their channel: "France 3 Alsace"); quality versions (HD, 4K...) are skipped, an edition whose logo is the drawing of its channel is skipped, and the same drawing found for several channels or editions, or already used anywhere in the repository by a
channel of another family, is a doubt (perceptual fingerprint; a family is one brand across countries or numbered
sister channels: `Eurosport6.fr`, `Eurosport8.fr`). Current logos of the country with the drawing of a channel of
another family are listed in the summary ("Current logos to check") for the review |
| `logos guide-aliases --country <cc>` | aliases from the iptv-epg guide of the country: a guide channel found by name for exactly one channel or edition gets the alias `iptv-epg-<cc>:<guide id>` (run by the harvest and listed in its summary) |
| `logos alias-remove <source> <guide id>` | remove a guide alias |
| `logos bulk --country <cc> [<cc>...]` | adds directly, without review, the iptv-org logos of whole countries that pass the rules (SVG or at least 500 px once prepared): every channel and edition without a logo here; skips editions with their channel's drawing, rejected URLs and drawings of a channel of another family; details in `temp/bulk/<cc>.csv` (workflow `bulk`) |
| `logos epg-check --country <cc> [--review 15]` | current logos whose iptv-epg guide channel (found without doubt: guide alias, same ID or a single channel of that name) shows another drawing: replaced when the channel website shows the guide's drawing and not ours (`seen-on`), else listed for review in `temp/epg-check/<cc>/summary.md` with a sheet (ours, then the guide's) |
| `logos dismiss <id> <url> [--reason]` | never propose this logo URL again for this channel (`data/rejected.csv`) |
| `logos seen-on <page> <logo>` | is the logo (URL, `data:image/...`, file or logo ID) shown on the page? Reads it like a browser; FOUND (the SVG written in the page, or one of its images with the same drawing, by perceptual fingerprint) or NOT FOUND: the proof a reviewer gives that a logo is current Read plainly, then rendered by a headless browser (`web.py`, Playwright) when the site refuses it or the logo is not found; drawings compared by fingerprint and by silhouette |
| harvest proofs | every logo kept that does not come from Wikidata or Wikipedia is looked for on its channel's website (`sites.py` finds it: iptv-org's address, Wikidata's, the home page, or one made from the name, confirmed by its title or domain); Website column of the summary, and `sites-NN.png`: each logo next to the top of the website |
| `logos hunt --country <cc> [--limit 40] [--sharpen 30]` | like harvest, for a weekly slice of the channels without a logo and of the small logos (under 1000 px, raster original: a sharper version is proposed, marked same or different drawing), every source including the website |
| `logos verdict ready\|hold "<report>"` | a reviewer's decision for the workflows (temp/verdict.json) |
| `logos merge-data <base> <ours> [<upstream>] [--files]` | puts a change on top of main (workflows, `.github/scripts/sync.sh`): `data/logos.csv`, `data/aliases.csv`, `data/channels.csv` and `data/external_ids.csv` rebuilt from `upstream` (default `origin/main`) and the change (`ours`), merged row by row against their common ancestor (`base`): a row the change did not touch keeps main's version. With `--files` the working tree holds main (`git reset --hard origin/main`) and the change's logo files are applied on top (one source per logo, `data/rejected.csv` rows added): no rebase, so two versions of an image never conflict |
| `logos channels-init` | our channel registry (`data/channels.csv`, `data/external_ids.csv`, see `roadmap/01-channel-registry.md`): every iptv-org channel and edition of the followed countries gets a `ch_` ID and its iptv-org ID; adds only, run every night by `update` |
| `logos migrate-ids` | one-off, done on 2026-11-23 (roadmap step 2): logos, originals, aliases and refused URLs moved from iptv-org IDs to our IDs |
| `logos channel <ref>` | show a registry channel from our ID, its slug, or its iptv-org or Wikidata ID |
| `logos channel-add <name> --country <cc> [--alias a] [--website u] [--parent ref]` | a new channel (new `ch_` ID); refused when a channel of the country has the same name (`--force`) or the country is not followed (`--any-country`) |
| `logos channel-edit <ref> [--name] [--slug] [--alias] [--website] [--status active\|closed\|merged] [--parent]` | change a channel; its ID never changes, its slug follows the name |
| `logos channel-map <ref> iptv-org\|iptv-org-feed\|wikidata <id> [--remove]` | map another project's ID to a channel; guide IDs are never stored |
| `logos regress-check <ref>` | fails when a logo is older (its `updated`, else `added`, date) than in `ref`: an older version would come back. Run by `check` on pull requests and by `sync.sh` |
| `logos reprocess` | rebuild every logo from its original after a change of the image rules |
| `logos changes [--dry-run]` | opens, updates or closes the `iptv-org:changes` issue from the warnings of `validate` |

Tests: `uv run pytest`. Style: `uv run ruff check worldwide_tv_logos tests`.

Downloads identify themselves with the repository address and honour `Retry-After`; iptv-org data is cached one
day in `.cache/`.
