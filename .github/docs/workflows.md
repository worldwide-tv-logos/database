# Workflows

Same flow as [iptv-org/database](https://github.com/iptv-org/database): issue forms, automatic check, manual
approval, nightly update. Difference: each request is applied on its own, so one faulty request never blocks
the others.

## check

On every push and pull request: `ruff`, tests, `logos validate`. Blocks the merge on any error.

## validate_issue

When an issue with a `logos:*` or `aliases:*` label is opened or edited: `logos issue-validate` downloads and
checks the logo, then labels the issue `check:passed`, or comments the problems and labels it `check:failed`.

## update

Every night at 03:00 UTC (or by hand): `logos update` applies the open issues labelled `approved`, one by one
(a faulty one is commented, labelled `check:failed` and loses `approved`); then `logos validate`, `logos export`
(`missing/`), one commit closing the processed issues (`Closes #N`), and a comment on each with what changed.

## deploy

On every push to `main`: `logos export` publishes `logos.json` and `aliases.json` to the `gh-pages` branch.

## Labels to create in the repository

`logos:add`, `logos:edit`, `logos:remove`, `logos:request`, `aliases:add`, `aliases:remove`, `approved`,
`check:passed`, `check:failed`. A `logos:request` issue is only checked (the channel exists and has no logo yet):
it is closed by hand once a `logos:add` request brings the image.
