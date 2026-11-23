"""Health check (workflow `health`, every day): what needs a maintainer, in one issue labelled `health`.

- the last run on main of a workflow failed (in the last eight days);
- a pull request labelled `needs:maintainer`, or opened by the bot more than seven days ago and still open;
- an issue labelled `needs:maintainer`.

Something found: the issue is opened, or updated. Nothing: it is closed. Uses the GitHub CLI (GH_TOKEN) only.
"""
from __future__ import annotations

import datetime
import json
import subprocess
import sys

TITLE = 'Health check: a maintainer is needed'
LABEL = 'health'
IGNORED = {'pages-build-deployment'}


def gh(*args: str) -> str:
    return subprocess.run(['gh', *args], capture_output=True, text=True, check=True).stdout


def ago(iso: str, now: datetime.datetime) -> float:
    return (now - datetime.datetime.fromisoformat(iso)).total_seconds() / 86400


def problems(now: datetime.datetime) -> list[str]:
    out = []
    runs = json.loads(gh('run', 'list', '--branch', 'main', '--limit', '300', '--json',
                         'workflowName,status,conclusion,url,createdAt,event'))
    latest: dict[str, dict] = {}
    for r in runs:                                   # newest first
        if r['status'] == 'completed' and r['workflowName'] not in latest and r['conclusion'] != 'skipped':
            latest[r['workflowName']] = r
    for name, r in sorted(latest.items()):
        if name not in IGNORED and r['conclusion'] in ('failure', 'startup_failure', 'timed_out') \
                and ago(r['createdAt'], now) <= 8:
            out.append(f'- workflow **{name}**: last run {r["conclusion"]} ({r["createdAt"][:10]}): {r["url"]}')
    for p in json.loads(gh('pr', 'list', '--state', 'open', '--limit', '100', '--json',
                           'number,title,labels,author,createdAt,url')):
        labels = {x['name'] for x in p['labels']}
        if 'needs:maintainer' in labels:
            out.append(f'- pull request #{p["number"]} waits for a maintainer: {p["title"]}')
        elif p['author'].get('login', '').startswith(('github-actions', 'app/github-actions')) \
                and ago(p['createdAt'], now) > 7:
            out.append(f'- pull request #{p["number"]} open for {ago(p["createdAt"], now):.0f} days: {p["title"]}')
    for i in json.loads(gh('issue', 'list', '--state', 'open', '--label', 'needs:maintainer', '--limit', '100',
                           '--json', 'number,title')):
        out.append(f'- issue #{i["number"]} waits for a maintainer: {i["title"]}')
    return out


def main() -> int:
    now = datetime.datetime.now(datetime.UTC)
    found = problems(now)
    issues = json.loads(gh('issue', 'list', '--state', 'open', '--label', LABEL, '--limit', '5', '--json', 'number'))
    number = issues[0]['number'] if issues else None
    if not found:
        if number:
            gh('issue', 'close', str(number), '--comment', f'All clear on {now:%Y-%m-%d}: closed.')
        print('all clear')
        return 0
    body = (f'Checked on {now:%Y-%m-%d %H:%M} UTC by the `health` workflow (updated every day, closed when all is '
            'clear).\n\n' + '\n'.join(found) + '\n')
    if number:
        gh('issue', 'edit', str(number), '--body', body)
    else:
        subprocess.run(['gh', 'label', 'create', LABEL, '--color', 'd93f0b', '--description',
                        'something needs a maintainer'], capture_output=True, check=False)
        gh('issue', 'create', '--title', TITLE, '--label', LABEL, '--body', body)
    print('\n'.join(found))
    return 0


if __name__ == '__main__':
    sys.exit(main())
