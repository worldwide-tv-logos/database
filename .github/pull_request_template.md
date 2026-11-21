<!--
One or a few logos? Use the issue forms instead: https://github.com/worldwide-tv-logos/database/issues/new/choose
Pull requests are for bulk imports (`uv run logos import`) and code changes. Commit messages in English.
-->

## What

<!-- e.g. "Import 40 logos of Spanish channels from <source>" -->

## Checklist

- [ ] `uv run logos validate` reports 0 error(s)
- [ ] `uv run pytest -q` and `uv run ruff check .` pass (code changes)
- [ ] files under `data/`, `logos/` and `sources/` come from `logos import`, not edited by hand
- [ ] every logo is the one currently on air for its exact channel or edition
