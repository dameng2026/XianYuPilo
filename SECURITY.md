# Security policy

## Supported versions

Only the current default branch is eligible for security fixes. Historical snapshots, forks, local modifications, and unmaintained deployments are unsupported.

## Reporting a vulnerability

Do not disclose suspected vulnerabilities in a public issue, discussion, chat, or pull request. Use the hosting provider's private vulnerability-reporting feature if the repository owner has enabled it. If that feature is unavailable, contact the repository owner through a previously verified private channel and request an encrypted reporting channel before sending exploit details, secrets, personal data, cookies, or access tokens.

The owner must configure and publish a monitored security contact before public release. This repository intentionally does not invent an email address or claim an incident-response channel that has not been staffed.

Include only what is necessary:

- affected version or commit and deployment topology;
- impact and prerequisites;
- minimal reproduction steps or proof of concept;
- whether credentials, cookies, personal data, or third-party systems are at risk;
- suggested remediation, if known;
- a safe way to contact the reporter.

Never include live credentials or real customer data. Use synthetic accounts and redacted evidence.

## Response targets

The project adopts these targets (they are objectives, not a guaranteed SLA):

| Stage | Target |
| --- | --- |
| Acknowledge a complete report | 2 business days |
| Initial severity assessment | 5 business days |
| Critical containment decision | 24 hours after confirmation |
| High-severity remediation plan | 7 calendar days |
| Coordinated disclosure | Agreed with the reporter after a fix is available |

Confirmed incidents must preserve evidence, rotate exposed secrets, invalidate sessions, assess data exposure, notify affected parties where legally required, and document corrective actions. Do not delete logs or rebuild compromised hosts before evidence preservation is complete.

## Security boundaries

- The public browser boundary is the Web/Nginx container. MySQL, Redis, API, and crawler ports are internal-only in the production Compose topology.
- API access uses short-lived bearer tokens. Internal API access uses a distinct `INTERNAL_API_TOKEN` and fails closed in production.
- Xianyu cookies, provider keys, bridge tokens, database credentials, and Redis credentials are secrets. They must stay server-side and must not appear in source, screenshots, test output, URLs, telemetry, or support tickets.
- The crawler can navigate only an explicit HTTPS hostname allowlist. Expanding that allowlist is a security review, not a routine configuration change.
- The commercial bridge is optional and disabled when its URL/token are blank.
- Production `.env` entries are secret-file paths, not secret values. The deployment verifier reads those files and supplies short-lived Compose secret sources; containers receive only service-scoped `/run/secrets/*` mounts. Back the files with an audited platform secret store and restrict access to Docker/host administration APIs. Rotating a file still requires a controlled service restart; database-account rotation is a separate explicit operation.

## Deployment requirements

Before any internet-facing deployment:

1. Generate unique random secret files and a bcrypt administrator password hash; run `scripts/production_preflight.py` without errors.
2. Terminate TLS at a maintained reverse proxy or load balancer. Keep the default loopback bind unless that proxy is on another host.
3. Restrict administrator access with network controls and MFA at the outer identity/proxy layer where possible.
4. Enable encrypted backups, restore testing, centralized append-only audit logs, metrics, alerts, vulnerability scanning, and an incident-response rota.
5. Run the complete CI suite, dependency audits, container scans, secret scans, load tests, and an independent penetration test against the release candidate.

## Dependency and supply-chain policy

- Python and npm dependencies must be locked. CI runs `pip-audit` and `npm audit` against the official npm registry; high/critical findings are release blockers.
- Container base images must be scanned and updated regularly. For a formal release, pin images by digest and retain an SBOM and provenance record.
- Do not bypass audit failures with broad ignores. Any temporary exception needs an exact service/advisory/package/installed-version binding, applicability analysis, compensating control, owner, independent approver, evidence, and an expiry no more than 31 days after approval. Critical or fixable findings cannot be excepted.
- Never run workflows from untrusted pull requests with repository secrets, and never use `pull_request_target` for build or test execution.

## Out of scope for testing without written authorization

Do not test production customer accounts, third-party infrastructure, Xianyu or Taobao systems, commercial bridge systems, denial-of-service scenarios, social engineering, or data exfiltration without explicit written authorization from every affected system owner. This project does not grant permission to bypass a platform's controls or terms.
