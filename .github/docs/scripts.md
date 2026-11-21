# Scripts

Python 3.12 and [uv](https://docs.astral.sh/uv/). `uv sync` once, then `uv run logos <command>`.

| Command | What it does |
|---|---|
| `logos validate [--offline]` | checks `data/`, every file in `logos/` and `sources/`, and (unless `--offline`) the IDs against iptv-org |
| `logos import <file.csv> [--pause 5]` | adds or replaces logos from a CSV `channel,feed,origin[,label]`; `origin` is an `https://` URL or a local file; remote downloads are spaced by `--pause` seconds |
| `logos issue-validate --number N --labels L` | checks one request (body in `RAW_BODY`); writes the problems to `temp/errors.md` |
| `logos update` | applies the approved issues (`GITHUB_REPOSITORY`, `GITHUB_TOKEN`); writes `temp/processed.txt` and `temp/changes.json` |
| `logos notify --commit SHA` | comments each processed issue with what changed |
| `logos export [--offline]` | writes `.api/logos.json`, `.api/aliases.json` and (unless `--offline`) the website (`.api/index.html`, `countries.json`, `countries/<cc>.json`, `search.json`) and `missing/<cc>.md` |
| `logos changes [--dry-run]` | opens, updates or closes the `iptv-org:changes` issue from the warnings of `validate` |

Tests: `uv run pytest`. Style: `uv run ruff check worldwide_tv_logos tests`.

Downloads identify themselves with the repository address and honour `Retry-After`; iptv-org data is cached one
day in `.cache/`.
