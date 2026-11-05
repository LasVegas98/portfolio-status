"""Check public CV destinations; notify the owner only on an outage/recovery.

The published monitor mirror contains this script, public URLs and status only.
GitHub supplies its short-lived token. No app/database/provider secrets needed.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
MARKER = '<!-- life-plan-portfolio-monitor -->'
TITLE = 'Portfolio link needs attention'


def probe(check):
    url = check['url']
    parsed = urlsplit(url)
    if parsed.scheme != 'https' or parsed.username or parsed.password:
        raise ValueError('Monitor targets must be public HTTPS addresses.')
    request = Request(url, method=check.get('method', 'GET'),
                      headers={'User-Agent': 'LifePlan-Portfolio-Link-Check/1.0'})
    with urlopen(request, timeout=15) as response:
        if response.status != 200:
            raise ValueError('HTTP ' + str(response.status))
        if check.get('contains'):
            content = response.read(2_000_001)
            if len(content) > 2_000_000 or check['contains'] not in content.decode('utf-8', errors='replace'):
                raise ValueError('Expected portfolio content missing.')


def api(method, route, token, payload=None):
    request = Request('https://api.github.com' + route, method=method,
                      headers={'Authorization': 'Bearer ' + token,
                               'Accept': 'application/vnd.github+json',
                               'X-GitHub-Api-Version': '2022-11-28',
                               'Content-Type': 'application/json',
                               'User-Agent': 'LifePlan-Portfolio-Link-Check'},
                      data=json.dumps(payload).encode() if payload is not None else None)
    with urlopen(request, timeout=20) as response:
        content = response.read()
        return json.loads(content) if content else None


def notify(config, failures, token, *, test=False):
    repository = config['repository']
    if repository != 'LasVegas98/portfolio-status':
        raise ValueError('Unexpected alert repository.')
    route = '/repos/' + repository
    if test:
        issue = api('POST', route + '/issues', token, {
            'title': 'Portfolio monitor test — no outage',
            'body': MARKER + '\nA one-off owner-requested test. The public portfolio is healthy. Monitoring can create an assigned alert.',
            'assignees': [config['owner']],
        })
        api('PATCH', route + '/issues/' + str(issue['number']), token, {'state': 'closed'})
        print('Owner alert test created and closed: ' + issue['html_url'])
        return
    issues = api('GET', route + '/issues?state=open&per_page=100', token)
    existing = next((item for item in issues if item.get('title') == TITLE
                     and MARKER in (item.get('body') or '')), None)
    if failures and not existing:
        details = '\n'.join('- ' + item['url'] + ': ' + item['error'] for item in failures)
        issue = api('POST', route + '/issues', token, {
            'title': TITLE, 'body': MARKER + '\nA public CV link failed repeated checks:\n\n' + details,
            'assignees': [config['owner']],
        })
        print('Owner outage alert: ' + issue['html_url'])
    elif not failures and existing:
        number = str(existing['number'])
        api('POST', route + '/issues/' + number + '/comments', token,
            {'body': 'Recovered: every configured public portfolio check now passes.'})
        api('PATCH', route + '/issues/' + number, token, {'state': 'closed'})
        print('Recovery recorded for issue ' + number)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--notify', action='store_true')
    parser.add_argument('--test-alert', action='store_true')
    args = parser.parse_args()
    config = json.loads((ROOT / 'config.json').read_text(encoding='utf-8'))
    failures = []
    for check in config['checks']:
        for attempt in range(3):
            try:
                probe(check)
                break
            except (HTTPError, URLError, OSError, ValueError) as error:
                if attempt < 2:
                    time.sleep(3)
                else:
                    failures.append({'url': check['url'], 'error': str(error)[:200]})
    if args.test_alert and failures:
        raise SystemExit('Test alert requires healthy targets; actual checks failed.')
    if args.notify or args.test_alert:
        token = os.environ.get('GITHUB_TOKEN')
        if not token:
            raise SystemExit('GitHub alert token is unavailable.')
        notify(config, failures, token, test=args.test_alert)
    # Daily status is useful history and regular repository activity; avoids
    # GitHub's automatic schedule disable after 60 days without activity.
    status = {'checkedDate': datetime.now(timezone.utc).date().isoformat(),
              'status': 'down' if failures else 'up', 'failures': failures}
    (ROOT / 'status.json').write_text(json.dumps(status, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'status': status['status'], 'checks': len(config['checks']), 'failures': failures}))
    return 1 if failures else 0


if __name__ == '__main__':
    raise SystemExit(main())
