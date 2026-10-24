# Test Strategy

- Unit: schemas, services, tool registry, policy and model adapters.
- Integration: database transactions, migrations, outbox and workers.
- Security: auth, tenant isolation, prompt injection, secret redaction.
- Agent: allowed/denied tools, malformed arguments, bounded loop and provider timeouts.
- Voice: noise, silence, interruption, reconnect and provider failures.
- Reliability: duplicate requests, retries, worker restart and restore drills.
- Load: concurrent sessions, latency, quotas and provider limits.

Use synthetic data in CI, not customer recordings or personal data.
