"""Check hosted project entry points; notify the owner on outage/recovery.

The published monitor mirror contains this script, public URLs and status only.
GitHub supplies its short-lived token. No app/database/provider secrets needed.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
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
TITLE = 'Live project link needs attention'
LEGACY_TITLE = 'Portfolio link needs attention'


def run_checks(checks):
    """Bound slow-network retries while retaining configuration order."""
    def check_one(check):
        for attempt in range(3):
            try:
                probe(check)
                return None
            except (HTTPError, URLError, OSError, ValueError) as error:
                if attempt < 2:
                    time.sleep(3)
                else:
                    return {'url': check['url'], 'error': str(error)[:200]}
    # Eight fully timing-out checks finish in two batches (about 192 seconds),
    # leaving time for incident handling inside the five-minute workflow.
    with ThreadPoolExecutor(max_workers=4) as executor:
        return [failure for failure in executor.map(check_one, checks) if failure]


def probe(check):
    url = check['url']
    parsed = urlsplit(url)
    if parsed.scheme != 'https' or parsed.username or parsed.password:
        raise ValueError('Monitor targets must be public HTTPS addresses.')
    request = Request(url, method=check.get('method', 'GET'),
                      headers={'User-Agent': 'LifePlan-Portfolio-Link-Check/1.0'})
    expected_status = check.get('expected_status', 200)
    try:
        response = urlopen(request, timeout=30)
    except HTTPError as error:
        if error.code != expected_status:
            error.close()
            raise
        response = error
    with response:
        if response.status != expected_status:
            raise ValueError('HTTP ' + str(response.status))
        for name, expected in check.get('headers_contain', {}).items():
            if expected not in response.headers.get(name, ''):
                raise ValueError('Expected access-control header missing: ' + name)
        if check.get('contains'):
            content = response.read(2_000_001)
            if len(content) > 2_000_000 or check['contains'] not in content.decode('utf-8', errors='replace'):
                raise ValueError('Expected project content missing.')


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
    if repository != 'LasVegas98/portfolio-status' or config.get('owner') != 'LasVegas98':
        raise ValueError('Unexpected alert repository.')
    route = '/repos/' + repository
    if test:
        issue = api('POST', route + '/issues', token, {
            'title': 'Live project monitor test - no outage',
            'body': MARKER + '\nA one-off owner-requested test. The configured checks are healthy. Monitoring can create an assigned alert.',
            'assignees': [config['owner']],
        })
        api('PATCH', route + '/issues/' + str(issue['number']), token, {'state': 'closed'})
        print('Owner alert test created and closed: ' + issue['html_url'])
        return
    issues = api('GET', route + '/issues?state=open&per_page=100', token)
    existing = next((item for item in issues if item.get('title') in (TITLE, LEGACY_TITLE)
                     and MARKER in (item.get('body') or '')), None)
    if failures:
        details = '\n'.join('- ' + item['url'] + ': ' + item['error'] for item in failures)
        body = MARKER + '\nA hosted project check failed repeated checks:\n\n' + details
        if not existing:
            issue = api('POST', route + '/issues', token, {
                'title': TITLE, 'body': body, 'assignees': [config['owner']],
            })
            print('Owner outage alert: ' + issue['html_url'])
        elif existing.get('body') != body:
            number = str(existing['number'])
            api('PATCH', route + '/issues/' + number, token, {'title': TITLE, 'body': body})
            api('POST', route + '/issues/' + number + '/comments', token,
                {'body': 'The failing project checks have changed:\n\n' + details})
            print('Updated owner incident ' + number)
    elif not failures and existing:
        number = str(existing['number'])
        api('POST', route + '/issues/' + number + '/comments', token,
            {'body': 'Recovered: every configured hosted project check now passes.'})
        api('PATCH', route + '/issues/' + number, token, {'state': 'closed'})
        print('Recovery recorded for issue ' + number)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--notify', action='store_true')
    parser.add_argument('--test-alert', action='store_true')
    args = parser.parse_args()
    config = json.loads((ROOT / 'config.json').read_text(encoding='utf-8'))
    failures = run_checks(config['checks'])
    # Daily status also keeps the public mirror active without a commit for
    # every probe. Exact completion timestamps are recorded in workflow logs.
    # Save probe truth before alert delivery, so a provider failure cannot hide
    # the actual site result or leave a stale healthy status behind.
    status = {'checkedDate': datetime.now(timezone.utc).date().isoformat(),
              'status': 'down' if failures else 'up', 'failures': failures}
    (ROOT / 'status.json').write_text(json.dumps(status, indent=2) + '\n', encoding='utf-8')
    if args.test_alert and failures:
        raise SystemExit('Test alert requires healthy targets; actual checks failed.')
    alert_error = False
    if args.notify or args.test_alert:
        token = os.environ.get('GITHUB_TOKEN')
        if not token:
            raise SystemExit('GitHub alert token is unavailable.')
        try:
            notify(config, failures, token, test=args.test_alert)
        except (HTTPError, URLError, OSError, ValueError):
            # Do not include provider responses or credentials in public output.
            alert_error = True
    print(json.dumps({'checkedAt': datetime.now(timezone.utc).isoformat(),
                      'status': status['status'], 'checks': len(config['checks']),
                      'failures': failures, 'alertError': alert_error}))
    return 1 if failures or alert_error else 0


if __name__ == '__main__':
    raise SystemExit(main())
