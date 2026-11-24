#!/usr/bin/env bash
# Merge a pull request of the bot that its review said ready (label review:ready).
#
#   merge.sh <number> <branch>      (run with the branch checked out)
#
# Waits until GitHub knows whether it can be merged, merges it, and when main moved meanwhile puts it on top of main
# again (sync.sh) and retries. Still not merged: the label review:ready stays and the retry workflow tries again a few
# hours later. Invalid once on top of main: label needs:maintainer. Nothing left (main already holds it): closed.
set -uo pipefail
number=$1 branch=$2
source "$(dirname "$0")/sync.sh"

for attempt in 1 2 3 4 5; do
  state=UNKNOWN
  for _ in $(seq 24); do                 # GitHub computes whether it can be merged a few seconds after a push
    state=$(gh pr view "$number" --json mergeable --jq .mergeable)
    [ "$state" != UNKNOWN ] && break
    sleep 5
  done
  if [ "$state" = MERGEABLE ] && gh pr merge "$number" --squash --delete-branch; then
    echo "merged"
    # a merge by the workflow token starts no workflow: the website is published now, not at the end of the run
    gh workflow run deploy.yml > /dev/null 2>&1 || echo "deploy not started (permission actions: write missing)"
    exit 0
  fi
  echo "attempt $attempt: not merged ($state), on top of main again"
  sleep $((attempt * 10))
  sync; rc=$?
  if [ $rc = 2 ]; then
    gh pr close "$number" --delete-branch --comment "Nothing left to merge: main already holds this change."
    exit 0
  fi
  if [ $rc != 0 ]; then
    gh pr edit "$number" --remove-label review:ready --add-label needs:maintainer > /dev/null
    gh pr comment "$number" --body "Could not be put on top of main: a maintainer is needed (see the workflow log)."
    exit 1
  fi
  git push -q -f origin "HEAD:$branch"
done
echo "could not be merged yet: the retry workflow tries again"
exit 1
