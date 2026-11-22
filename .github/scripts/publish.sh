#!/usr/bin/env bash
# Publish the data changes of a workflow as a pull request, and merge it when allowed.
#
#   publish.sh <branch> <title> <body file>
#
# Only data/, logos/, sources/ and missing/ are committed (never code, workflows or instructions). The pull request
# body is the body file followed by the reviewer's report (temp/verdict.json, written by `logos verdict`). The pull
# request is merged only when the reviewer said `ready` and `logos validate` passes, unless the repository variable
# AUTO_MERGE is `false`; otherwise it waits for a maintainer (label needs:maintainer when the reviewer said `hold`).
set -euo pipefail
branch=$1 title=$2 body=$3

git config user.name "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
if [ -n "${GITHUB_ACTIONS:-}" ]; then
  # the Claude action leaves git configured with its own token, revoked when it ends: push with the workflow token
  git config --local --unset-all http.https://github.com/.extraheader || true
  git remote set-url origin "https://x-access-token:${GH_TOKEN}@github.com/${GITHUB_REPOSITORY}.git"
fi
uv run logos validate
git add data logos sources missing
if git diff --cached --quiet; then echo "nothing to publish"; exit 0; fi

state=hold
if [ -s temp/verdict.json ]; then
  state=$(python3 -c 'import json; print(json.load(open("temp/verdict.json"))["state"])')
  { cat "$body"; echo; echo "---"; echo; python3 -c 'import json; print(json.load(open("temp/verdict.json"))["text"])'; } > temp/pr-body.md
else
  { cat "$body"; echo; echo "---"; echo; echo "No review recorded: a maintainer must review this pull request."; } > temp/pr-body.md
fi

# On top of the current main: a branch based on an older main would seem to revert the workflows changed since,
# and the pull requests of the other countries, merged meanwhile, touch the same data files. Those are merged line by
# line (.gitattributes: merge=union) for the rebase, then row by row (`logos merge-data`: a row this pull request did
# not change keeps main's version), rewritten (sorted, one row per logo or alias) and validated again.
sync() {
  git fetch -q origin main
  local base ours
  base=$(git merge-base HEAD origin/main); ours=$(git rev-parse HEAD)
  if ! git rebase -q origin/main; then git rebase --abort; echo "rebase on main failed"; return 1; fi
  uv run logos merge-data "$base" "$ours"
  if ! git diff --quiet -- data; then git add data && git commit -q --amend --no-edit; fi
  uv run logos validate > /dev/null || { echo "data no longer valid once on top of main"; return 1; }
}

git switch -q -C "$branch"
git commit -q -m "$title"
sync || state=hold
git push -q -f origin "$branch"
number=$(gh pr list --head "$branch" --state open --json number --jq '.[0].number')
if [ -z "$number" ]; then
  gh pr create --head "$branch" --base main --title "$title" --body-file temp/pr-body.md > /dev/null
  number=$(gh pr view "$branch" --json number --jq .number)
else
  gh pr edit "$number" --body-file temp/pr-body.md > /dev/null
fi
echo "pull request #$number, review: $state"
[ -n "${GITHUB_OUTPUT:-}" ] && echo "pr=$number" >> "$GITHUB_OUTPUT"

if [ "$state" = ready ] && [ "${AUTO_MERGE:-true}" != false ]; then
  gh pr edit "$number" --remove-label needs:maintainer > /dev/null 2>&1 || true
  for attempt in 1 2 3; do              # another country merged meanwhile: on top of main again, then retry
    if gh pr merge "$number" --squash --delete-branch; then echo "merged"; exit 0; fi
    sleep $((attempt * 15))
    sync && git push -q -f origin "$branch" || break
  done
  gh pr edit "$number" --add-label needs:maintainer > /dev/null
  echo "could not be merged: on hold, redone at the next run"
elif [ "$state" = hold ]; then
  gh pr edit "$number" --add-label needs:maintainer > /dev/null
fi
