# Step 8: lookup API

**Status: to do** (needs step 6)

## Goal

A read-only API that matches what users send (a guide channel ID, a free channel name, a whole XMLTV channel list)
to our channels and logos, so that nobody has to write their own matching. The repository stays the only source of
data; the site stays on GitHub Pages.

## How

- **Hosting**: Vercel (Python runtime, FastAPI as is). Stateless: no database, nothing written.
- **Data**: at start, the API loads `channels.json` and `guides.json` from GitHub Pages and keeps them in memory
  (a few MB); reloaded when a newer `version` is published.
- **Matching**: the same code as `guides.json` (`worldwide_tv_logos/guides.py`, no rules written twice), plus
  approximate matching of free names (`rapidfuzz`: typos, "HD"/"FHD", provider prefixes). Every answer carries a
  score; names shared by several countries need the country.
- **Endpoints**:
  - `GET /channels/{id}`: a channel by `ch_`, slug, iptv-org or Wikidata ID;
  - `GET /match?guide_id=…` or `?name=…&country=…`: likely channels, ranked, with their logos;
  - `POST /match/xmltv`: a whole XMLTV `<channel>` list (or the file), one answer per channel;
  - `GET /logo?guide_id=…` (or `name`, `country`): redirect to the logo image, usable directly in an IPTV app.
- **Safeguards**:
  - read-only: additions and corrections still go through issues (step 4);
  - if the API is down, the static files and the site keep working;
  - request size limited (XMLTV list), simple rate limit per address.

## Files to change

| File | Change |
|---|---|
| `api/main.py` (new) | FastAPI app, loading and reloading the published files, endpoints |
| `api/requirements.txt`, `vercel.json` (new) | Vercel deployment |
| `worldwide_tv_logos/guides.py` | matching usable without the repository's files (from the published JSON) |
| `pyproject.toml` | extra `api = ["fastapi", "rapidfuzz"]` |
| `.github/workflows/check.yml` | API tests on pull requests |
| `tests/test_api.py` (new) | each endpoint, XMLTV list, ambiguous names, reload |
| `README.md` | API usage and examples |
