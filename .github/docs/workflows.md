# Workflows

Same flow as [iptv-org/database](https://github.com/iptv-org/database): issue forms, automatic check, manual
approval, nightly update. Difference: each request is applied on its own, so one faulty request never blocks
the others.

## check

On every push and pull request: every workflow file parses as YAML (GitHub silently skips an invalid one), `ruff`, tests, `logos validate`, and on a pull request `logos regress-check` (no older version of a logo comes back). Blocks the merge on any error.

## validate_issue

When an issue with a `logos:*`, `aliases:*` or `channels:*` label is opened or edited (an edit withdraws `approved`: the new
content must be reviewed again): `logos issue-validate` downloads and
checks the logo, then labels the issue `check:passed`, or comments the problems and labels it `check:failed`. A
Wikipedia or Wikimedia Commons file page (`.../wiki/File:X.svg`, `...#/media/Fichier:X.png`) is read as the image
itself. When the image is refused (too small, a web page, unreadable), Claude looks for a better file of the same
logo (`logos find`) and comments its URL, so that the author only has to edit the issue.

## Changes on the iptv-org side

Every night, `update` runs `logos watch-iptvorg` before `logos channels-init`: a channel renamed at iptv-org keeps
our ID and its logo (the new iptv-org ID mapped to it, the old one kept as `iptv-org-former`), a closed one is marked
closed, names and websites follow unless the channel was edited here. A channel removed from iptv-org is a
**warning** of `logos validate`, never an error: it never blocks the nightly update.

## changes

Every Monday at 06:00 UTC (or by hand): `logos changes` opens, updates or closes the single issue labelled
`iptv-org:changes`: logos of channels renamed in the week, channels no longer in iptv-org, and (information only) the
requests open at iptv-org for the followed countries.

## New channels, right away

A `channels:add` or `channels:edit` request approved by the review starts `update` at once (`validate_issue`): the
channel is added within minutes, not at night. `update` then starts `harvest` in mode `new` for the countries that got
channels without a logo: `logos hunt --recent 2` looks for their logos in every source, website included, and the pull
request `new/<cc>` is reviewed and merged like a hunt. Mode `new` has its own queue: it never waits for the weekly runs.

## harvest

One pull request per country of `data/countries.csv` (skipped while the previous one of the same kind is open):

- **Sunday 04:00 UTC, harvest**: `logos harvest --country <cc> --updates`: missing logos and newer or better
  versions of current ones, for every channel and edition (a weekly slice of 700 for the largest countries), from
  every source of `worldwide_tv_logos/sources/` (branch `harvest/<cc>`; their answers are kept in the Actions cache). A new iptv-org channel of a followed country is therefore looked for the first Sunday after it
  appears;
- **Wednesday 04:00 UTC, hunt**: `logos hunt --country <cc>`: a different slice of 40 channels still without a logo
  and of 30 small logos (under 1000 px, raster original) every week, every source including the channel website:
  missing logos, and sharper versions of the small ones (SVG, or 1.5 times larger), each marked "same drawing" or
  "DIFFERENT drawing" (branch `hunt/<cc>`).

The logos found are imported, then Claude looks at every one of them on the contact sheets, rejects the wrong ones
(`logos reject`), looks for better ones (`logos find`, `logos set`) and records its decision (`logos verdict`).
`.github/scripts/publish.sh` commits the data only, puts it on top of the current main without a rebase
(`.github/scripts/sync.sh`: rows merged row by row, the change's logo files applied on top, validated, no older logo
back), opens the pull request with Claude's report, and when Claude said `ready` labels it `review:ready` and merges
it (`.github/scripts/merge.sh`, which then starts `deploy` so the website has the logos at once), unless the
repository variable `AUTO_MERGE` is `false`. Claude decides every logo
itself (a doubt is rejected, never published; one image found for several numbered channels of a family, such as
Sport 1 and Sport 2, is the brand logo without the number and is kept out of all of them). One brand shares its logo across countries
(HGTV.be and HGTVSouthAfrica.za: the name without a country or region at the end): that is never a doubt, and a logo
found that differs from the brand's logo published for other countries (often an older branding) is listed for the
review and says `hold` only when the change is broken: the pull request then
waits for a maintainer (`needs:maintainer`), and the next harvest of the country redoes it.

## retry

Every 3 hours: the open pull requests labelled `review:ready` that could not be merged when they were published
(main moved meanwhile) are put on top of main again and merged. One that is no longer valid once on top of main gets
`needs:maintainer`; one whose change main already holds is closed.

## Review by Claude (validate_issue)

When the secret `CLAUDE_CODE_OAUTH_TOKEN` is set, a request that passes the checks is reviewed by Claude following
CLAUDE.md: the preview of the logo (`temp/preview/sheet-01.png`, on dark and light tiles) is compared with the
channel; a logo gets `approved` (applied the next night) unless there is a concrete reason against it, then it is closed
with the reason (`needs:maintainer` only when something is broken).
Issue texts are treated as data: Claude can only read, comment and label. For a `logos:request`, Claude looks for the
logo itself (`logos find`, `logos set`) and opens a pull request `request/<n>` that closes the issue.

## changes (Claude)

After the Monday update of the `iptv-org:changes` issue, Claude checks the logo of each renamed channel (`logos find`,
the website; `logos set` for a new branding) and removes the logo of a channel gone for good (`logos remove`), in the
pull request `iptv-org-changes`.

## report

On the 1st of every month, Claude writes an activity report as an issue labelled `report`.

## claude

A maintainer (owner, member or collaborator) writes `@claude` in an issue or a pull request: Claude answers there,
and works on a branch with a pull request when asked to change something.

## harvest_reject

A comment `/reject <channel id> <reason>` from a maintainer on a harvest pull request: `logos reject` gives the channel
back its logo of `main` (or none) and adds the proposed URL to `data/rejected.csv`; the bot commits and answers.

## epg-check

Every Friday at 04:00 UTC (or by hand for given countries): `logos epg-check` for a weekly slice of 30 countries of
iptv-org (every country in about 8 weeks). Replacements proved by the channel website are automatic; Claude reviews
the other cases (`logos set` the guide's logo when it is the current one, `logos dismiss` it otherwise, with the page
that proved it). One pull request per country (branch `epg/<cc>`), merged when Claude says it is ready.

## site-check

Thursday 04:00 UTC: `logos site-check --country <cc>` for every followed country, a weekly slice of 150 current
logos. Each channel's website is found and confirmed (`sites.py`); when our logo is not on it (read plainly, then
rendered by a headless browser) and the website shows other logos, the case is listed (`summary.md`, `sites-NN.png`:
ours, then each website logo, next to the top of the website). Claude applies a newer logo (`logos set`) or
dismisses it (`logos dismiss`); one pull request per country (branch `site/<cc>`).

## health

Every day 08:30 UTC, without Claude: a workflow whose last run on main failed, a pull request labelled
`needs:maintainer` or opened by the bot more than seven days ago, an issue labelled `needs:maintainer`: listed in
one issue labelled `health` (opened, or updated), closed when all is clear (`.github/scripts/health.py`).

## bulk

By hand only: `logos bulk` for every country of iptv-org (or the countries given), four at a time, one commit per
country pushed to main. The iptv-org logos are added without review (maintainer's decision of 2026-11-22).

## update

Every night at 03:00 UTC (or by hand): `logos update` applies the open issues labelled `approved`, one by one
(a faulty one is commented, labelled `check:failed` and loses `approved`); then `logos validate`, `logos export`
(`missing/`), one commit closing the processed issues (`Closes #N`), and a comment on each with what changed.
If the repository had no commit for 45 days, it makes an empty commit: GitHub disables scheduled workflows after 60
days without activity.

## deploy

On every push to `main` and after every nightly `update` (a push made by a workflow starts no other workflow):
`logos export` builds the data of the website (every iptv-org country and channel), `logos.json` and
`aliases.json` in `.api/`; `npx nuxt generate` builds the website (`site/`, Nuxt) and the data is copied next to its
pages, then everything is published to the `gh-pages` branch: https://worldwide-tv-logos.github.io/database/

To work on the website: `uv run logos export`, then in `site/`: `npm install` and `npm run dev` (the data of `.api/` is
served by the development server).

## Labels to create in the repository

`logos:add`, `logos:edit`, `logos:remove`, `logos:request`, `aliases:add`, `aliases:remove`, `approved`,
`check:passed`, `check:failed`, `needs:maintainer`, `review:ready` (created by `publish.sh`), `report`, `iptv-org:changes`, `waiting:iptv-org` (a logo for a channel or feed not in iptv-org yet: kept
`approved`, tried again every night, applied as soon as iptv-org has it). A `logos:request` issue is only checked (the channel exists and has no logo yet):
it is closed by hand once a `logos:add` request brings the image.
