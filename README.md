# Hosted project link status

Checks Life Plan health and its private login boundary, FlyHigh, the public
portfolio, key assets and legacy PDF link every five minutes through
GitHub Actions. A repeated failure opens one issue assigned to LasVegas98;
recovery closes it. Repository watching and GitHub notification preferences
determine web/email delivery. Scheduling can be delayed: this is not an instant
or guaranteed uptime service. A manual test-alert dispatch verifies issue delivery.

Life Plan checks use no credentials: /healthz must return its health response,
while / must return the application's Basic authentication challenge. This does
not prove authenticated saves, database recovery or PDF generation. Monitor
failures identify the specific URL. ChatGPT also has an hourly condition watch
for outages and a monitor that has not run for over two hours; mobile push/email
delivery still depends on account and device notification settings.

Only public addresses, this checker and a daily status record are mirrored here.
The canonical source is private Life Plan `ops/portfolio-monitor/`. Private CV,
coursework, credentials and application source are never copied to this monitor.
Daily status activity keeps the monitor maintained; no paid runner is used.

Source: [GitHub schedule limits](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule),
[public runner billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions),
[workflow notifications](https://docs.github.com/en/actions/concepts/workflows-and-actions/notifications-for-workflow-runs).
