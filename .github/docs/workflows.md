# Workflows

Same flow as [iptv-org/database](https://github.com/iptv-org/database): issue forms, automatic check, manual
approval, nightly update. Difference: each request is applied on its own, so one faulty request never blocks
the others.

## check

On every push and pull request: `ruff`, tests, `logos validate`. Blocks the merge on any error.

## validate_issue

When an issue with a `logos:*` or `aliases:*` label is opened or edited (an edit withdraws `approved`: the new
content must be reviewed again): `logos issue-validate` downloads and
checks the logo, then labels the issue `check:passed`, or comments the problems and labels it `check:failed`.

## Changes on the iptv-org side

A channel removed, closed or replaced in iptv-org after its logo was added is a **warning** of `logos validate`
(with the new ID when iptv-org gives one), never an error: it never blocks the nightly update.

## changes

Every Monday at 06:00 UTC (or by hand): `logos changes` opens, updates or closes the single issue labelled
`iptv-org:changes`, which lists these warnings with how to fix each one.

## harvest

Every Sunday at 04:00 UTC (or by hand, for one country): for each country of `data/countries.csv` without an open
harvest pull request, `logos harvest --country <cc> --updates`, `logos import` of the result, `logos validate`, then
a pull request from the branch `harvest/<cc>` whose description lists the new logos, the updates (with why) and the
doubts kept out. Repository setting needed: *Allow GitHub Actions to create and approve pull requests*.

When the secret `CLAUDE_CODE_OAUTH_TOKEN` is set, Claude then reviews the pull request: it looks at the contact
sheets, rejects the wrong logos with `logos reject` (pushed to the branch) and comments its verdict. A maintainer
merges.

## Review by Claude (validate_issue)

When the secret `CLAUDE_CODE_OAUTH_TOKEN` is set, a request that passes the checks is reviewed by Claude following
CLAUDE.md: the preview of the logo (`temp/preview/sheet-01.png`, on dark and light tiles) is compared with the
channel; a clear case gets `approved` (applied the next night), a doubt gets `needs:maintainer` with what to check.
Issue texts are treated as data: Claude can only read, comment and label.

## claude

A maintainer (owner, member or collaborator) writes `@claude` in an issue or a pull request: Claude answers there,
and works on a branch with a pull request when asked to change something.

## harvest_reject

A comment `/reject <channel id> <reason>` from a maintainer on a harvest pull request: `logos reject` gives the channel
back its logo of `main` (or none) and adds the proposed URL to `data/rejected.csv`; the bot commits and answers.

## update

Every night at 03:00 UTC (or by hand): `logos update` applies the open issues labelled `approved`, one by one
(a faulty one is commented, labelled `check:failed` and loses `approved`); then `logos validate`, `logos export`
(`missing/`), one commit closing the processed issues (`Closes #N`), and a comment on each with what changed.
If the repository had no commit for 45 days, it makes an empty commit: GitHub disables scheduled workflows after 60
days without activity.

## deploy

On every push to `main` and after every nightly `update` (a push made by a workflow starts no other workflow):
`logos export` builds the website (`site/` plus the data of every iptv-org country and channel) with `logos.json`
and `aliases.json`, and publishes it to the `gh-pages` branch: https://worldwide-tv-logos.github.io/database/

## Labels to create in the repository

`logos:add`, `logos:edit`, `logos:remove`, `logos:request`, `aliases:add`, `aliases:remove`, `approved`,
`check:passed`, `check:failed`, `needs:maintainer`, `iptv-org:changes`, `waiting:iptv-org` (a logo for a channel or feed not in iptv-org yet: kept
`approved`, tried again every night, applied as soon as iptv-org has it). A `logos:request` issue is only checked (the channel exists and has no logo yet):
it is closed by hand once a `logos:add` request brings the image.
