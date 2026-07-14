# Production deployment and operations

This document covers the production deployment procedure, operational controls,
backup/recovery requirements, and incident rules for the open-source edition.

The normal production preflight validates technical configuration only:

```sh
python scripts/production_preflight.py --env-file .env
```

## Product-surface boundary

This open-source edition has one administrator identity and no end-user
registration or account recovery, VIP/membership, top-up, subscription,
standalone metering, or general-purpose payment surface. The only retained
commercial transaction is an advertising application followed by payment of
that application's advertising order. Its payment endpoints are confined to
the `/api/ads` namespace and are not a reusable checkout or billing API.

The historical registration handlers are not mounted. Known retired
registration/recovery route shapes return a structured HTTP 410 response so a
client sees an explicit unsupported state rather than a broken form or false
success. Historical specifications that said all payment was removed are
superseded only by this narrow advertising-order exception; they do not reopen
registration, subscription, membership, top-up, general billing, or payment for
any other feature.

## Non-negotiable release blockers

### 1. License and asset rights

- The repository has no `LICENSE` file. Calling the directory "opensource" does
  not grant recipients permission to use, modify, redistribute, or sell it. The
  rights holder must choose and approve the license; an agent must not choose one
  on the owner's behalf.
- There is no `THIRD_PARTY_NOTICES` file or complete dependency/license bill of
  materials. Legal counsel or the rights holder must review transitive software,
  fonts, icons, screenshots, copied designs, and data sources and publish the
  required notices and source offers.
- `apps/web/public` now contains **79 runtime-referenced image/vector/icon
  assets**. The 235 unreferenced design-source assets—including registration,
  recovery, generic-payment, membership, and obsolete banner material—were
  removed, and a source-tree contract prevents them from silently returning.
  Provenance and redistribution authorization for the remaining 79 assets are
  still undocumented. Obtain written rights for every remaining asset or
  replace/remove it before distribution. Trademark review is required
  separately from copyright review.
- Browser automation, account cookies, messaging, publishing, captcha/slider
  handling, and marketplace data access require a written review of platform
  terms, applicable law, and account authorization. Technical functionality is
  not legal permission to automate a third-party service.

### 2. Privacy, security, and compliance

- Document the data inventory and retention/deletion rules for account cookies,
  user identifiers, messages, orders, uploads, AI prompts, logs, and backups.
- Complete the applicable privacy and cross-border transfer assessment (for
  example PIPL/DSL/CSL, GDPR, or local equivalents), customer notices, processor
  agreements, breach process, and data-subject request workflow.
- Commission an independent penetration test and remediate all critical/high
  findings. Run secret scanning, SAST, DAST, container scanning, and an SBOM/
  license scan against the exact release candidate.
- Configure a monitored private vulnerability-reporting channel and incident
  response rota. `SECURITY.md` defines targets but no staffed contact currently
  exists.

### 3. Operational proof

- Run the Compose stack on the target Linux distribution and container runtime.
  This workspace has no Docker executable, so image builds, container health,
  non-root filesystem permissions, Playwright/Chromium behavior, and Nginx syntax
  have not been exercised locally. CI provides the first automated environment,
  not production proof.
- Complete realistic load/soak testing for login, SSE, uploads, message polling,
  crawler concurrency, MySQL connection pressure, Redis exhaustion, and upstream
  timeouts. Establish capacity and autoscaling limits from measurements.
- Prove encrypted backup and restore for MySQL, Redis (where persistence is
  required), uploads, application data, and secret-manager configuration. A
  backup without a timed restore rehearsal is not accepted.
- Define SLOs, alerts, on-call ownership, runbooks, maintenance windows, rollback
  criteria, and a tested disaster-recovery objective.

## Implemented baseline controls

The current production Compose baseline provides:

- only the Web port published, bound to `127.0.0.1` by default;
- internal service/data networking plus explicit API/crawler egress networks;
- non-root application containers, dropped Linux capabilities,
  `no-new-privileges`, read-only root filesystems, tmpfs scratch space, process/
  memory/CPU limits, health checks, restart policies, and bounded JSON logs;
- API readiness fails closed unless the database/schema, production Redis,
  message-automation outbox poller, and token refresher report healthy; liveness
  remains a separate process-only probe;
- password-protected Redis and separate MySQL root/application credentials;
- fail-closed production secrets for JWT, cookie encryption, internal API,
  database, Redis, and administrator authentication;
- a crawler internal-token boundary, constant-time comparison, rate and
  concurrency limits, body/cookie/URL limits, HTTPS domain allowlisting,
  cancellation, session TTL, precise session cleanup, graceful shutdown, and
  production error redaction;
- configurable chat/embedding providers restricted to bounded public HTTPS
  egress with one-time DNS validation and IP pinning, no redirects or proxy
  environment, and mandatory API-key re-entry when the configured host changes;
- Nginx request/connection limits, upload and timeout bounds, SSE handling,
  security headers, CSP, hidden version headers, and static cache policy;
- locked dependency installation, CI tests/builds, strict Python/npm audits,
  Compose validation, Nginx syntax validation, and Dependabot configuration;
- secret-safe, read-only root smoke scripts and a fail-closed production
  environment validator.

These are baseline controls, not a certification or warranty.

### Delivery-source pagination client contract

- The delivery-source goods response is now bounded. `configuredGoods` and
  `allGoods` remain as compatibility aliases, but each contains only the
  requested page. Clients must read `configuredGoodsPage` and `allGoodsPage`
  (`records`, `total`, `current`, and `size`) and must not treat either alias as
  the complete goods library. The UI sends independent `configuredCurrent` /
  `configuredSize` / `configuredKeyword` and `candidateCurrent` /
  `candidateSize` / `candidateKeyword` query fields.
- This is a breaking semantic contract for any external client that previously
  assumed the two arrays were exhaustive. A release owner must inventory and
  upgrade every supported client, version the public API if old clients remain,
  and retain compatibility-test evidence before promotion. Do not deploy the
  bounded server independently of its client update.
- AI recommendation analyzes at most 200 active goods, sends at most 60 bounded
  candidate excerpts to the configured model, and returns one stable snapshot
  of at most 30 recommendations. Paging that snapshot is client-local; page
  changes must not call the model again. A truncated candidate-pool notice is a
  truthful scope disclosure, not proof that older goods were evaluated.

## Secure deployment procedure

### Prerequisites

- Supported Linux host, Docker Engine, and Docker Compose v2 with the `--wait`
  option;
- an external TLS reverse proxy/load balancer, DNS, certificates, firewall, and
  restricted administrative access;
- a managed secret store, backup destination, centralized logging/metrics, and
  an on-call owner;
- all legal and privacy blockers closed in writing.

### Configure

1. Copy `.env.example` to `.env`; restrict it to the deployment administrator
   (`chmod 600 .env` on Linux).
2. Generate every required secret independently with a cryptographically secure
   generator. Use a bcrypt cost of at least 12 for `ADMIN_PASSWORD_HASH`. Never
   store the plaintext administrator password in `.env`.
3. Use separate non-root `MYSQL_APP_*` and `MYSQL_MIGRATION_*` identities with
   the documented grants. Do not reuse root, runtime, migration, Redis, JWT,
   cookie, internal API, provider, or bridge credentials.
4. Add the real hostname to `TRUSTED_HOSTS`. Keep `CORS_ALLOWED_ORIGINS` empty for
   same-origin traffic or provide only exact HTTPS origins.
5. Leave the commercial bridge and AI/provider settings blank unless their URLs,
   credentials, data processing, and failure modes have been reviewed.
6. Keep `WEB_BIND_ADDRESS=127.0.0.1` when a same-host TLS proxy fronts the stack.
   If binding publicly is unavoidable, `PUBLIC_BASE_URL` must be HTTPS and host
   firewall/TLS verification becomes a blocking step.

### Validate and start

On Linux/macOS:

```sh
sh ./start.sh
```

On Windows:

```powershell
.\start.bat
```

The wrappers run the secret-safe preflight, `docker compose config --quiet`,
build/start with `--wait`, and the Web `/healthz` probe. They deliberately never
print resolved Compose configuration because it contains secrets. To validate an
already-built release, call the verification script with `--no-build` (shell) or
`-NoBuild` (PowerShell).

After startup, validate through the TLS endpoint—not just localhost—and confirm:

- unauthenticated protected API calls fail;
- login throttling and lockout work from distinct client IPs behind the trusted
  proxy chain;
- crawler calls without/with invalid internal tokens fail and target-host
  lookalikes are rejected;
- upload limits, SSE reconnect, upstream timeouts, graceful shutdown, and restart
  recovery match the runbook;
- browser responses include the intended CSP/security headers and no secrets;
- API failure injection yields matching non-2xx transport status and envelope
  code; gateways and clients must not count `code=4xx/5xx` responses as success;
- logs contain request IDs but no credentials, bearer tokens, cookies, QR image
  data, provider keys, or personal message content.

## Backup and recovery minimum

### Advertising truthfulness and local PII stores

- Advertising is fail-closed. Without a configured, reachable commercial bridge,
  text ads and plans return HTTP 503, application/payment writes are disabled,
  and the UI must not render placeholder inventory, prices, review status, or
  simulated payment actions. Historical local ad applications are read-only and
  are not evidence that a commercial review or placement exists.
- Keep `COMMERCIAL_BACKEND_MUTATION_IDEMPOTENCY_ENABLED=false` until the
  commercial provider has been contract-tested to honor the identical
  `Idempotency-Key` header and JSON field for ad-application creation, feedback
  creation, and feedback replies. Once enabled, an unknown outcome may only be
  retried with the browser-persisted original key and unchanged payload. Payment
  order idempotency remains a separate capability and must not share this flag.
- Keep `COMMERCIAL_BACKEND_PAID_AD_PLACEMENT_ENFORCED=false` until commercial
  integration tests prove that unpaid, closed, expired, refunded, or otherwise
  unconfirmed advertising orders cannot become active and cannot appear in
  carousel or text-ad serving responses. Advertising reads and all new paid-ad
  workflows fail closed while this independent attestation is false.
- Local feedback and historical ad-application JSON are stored as purpose-bound
  `secret:v1` ciphertext in `xianyu_sys_setting`. Legacy plaintext remains
  readable only for migration compatibility and is encrypted on the next
  protected write. Preserve `COOKIE_CRYPTO_SECRET` through backup/restore;
  losing or rotating it without a reviewed re-encryption procedure makes those
  records unreadable.

- Local feedback uses a MySQL connection-scoped named lock around the complete
  read-modify-write cycle. A busy lock returns a retryable conflict and the
  encrypted payload is capped at 40,000 UTF-8 plaintext bytes so the AES-GCM
  envelope stays inside the existing `TEXT` column. Capacity responses require
  operator archiving; do not silently discard, truncate, or overwrite records.
- These compatibility stores are not a substitute for an approved PII system of
  record. Before launch, define retention, deletion/export handling, access
  logging, key rotation, backup recovery, and the owner of local-record archival.

### QR session topology

- The public marketplace QR flow intentionally owns an upstream HTTP session
  in API-process memory. The shipped API image therefore runs one Uvicorn
  worker and the reference Compose deployment declares one API replica. Do not
  add `--workers`, horizontally scale the API service, or route the create,
  status, credential-persistence, and cleanup steps to different replicas
  unless the ingress has a tested sticky-session rule for the complete QR
  flow. A shared session coordinator is required before non-sticky scaling.

### Schema migration gate

- Treat `python -m app.migrations upgrade` as a separately reviewed deployment
  step. The Compose `migrate` job is the only service authorized to issue schema
  DDL; API and Worker startup only check for pending/unknown versions and fail
  closed.
- Keep three unique MySQL credentials: root for initialization/recovery,
  `MYSQL_MIGRATION_*` for the one-shot schema runner, and `MYSQL_APP_*` for
  API/Worker DML. Capture `SHOW GRANTS` evidence proving the runtime identity has
  only `SELECT/INSERT/UPDATE/DELETE` and no schema/global/grant-option privilege.
  The entrypoint provisioning script runs only for a new data volume; existing
  installations require an explicit reviewed grant migration and secret rotation.
- Before every upgrade, stop external automation/writers, take a verified
  encrypted backup, review each newly numbered SQL file, and record the before/
  after output of `python -m app.migrations status`. Credentials must come from
  the managed environment or secret mount, never `-pPASSWORD` or a resolved
  Compose configuration printed to logs.
- MySQL DDL may commit implicitly. Migration files must be interruption-safe and
  rerunnable, and the runner records a version only after the whole file
  succeeds. Applied file checksums are pinned and drift fails closed; the first
  adoption of legacy, checksum-free history is a trust-on-first-use baseline.
  Never alter migration history to conceal a partial operation.
- Migration 005 performs compatibility `ALTER TABLE` operations and deterministic
  full-table backfills over delivery/card/model/RAG data. Measure lock duration,
  rewrite/disk requirements, replication lag, and maintenance-window headroom on
  a recent restored staging copy. Do not infer production duration from an empty
  CI database.
- Automatic schema downgrade is intentionally unsupported. Application rollback
  is allowed only after proving the older build accepts all applied versions.
  Otherwise use a reviewed forward-fix or restore the pre-upgrade backup in an
  isolated environment before any production switch.
- The exact operator commands and password-safe dump example are maintained in
  `apps/api/migrations/README.md`; rehearse that runbook against staging and a
  restored backup before approving the release.

### Retired marketplace features and legacy credential cleanup

Product polishing, automatic rating, account strategy storage, username/password
login configuration, and face-verification records are intentionally unavailable.
Their compatibility endpoints return HTTP 410 with a remediation message and do
not read or write account data. The account UI exposes only the real batch login
check and the supported QR-code/Cookie authorization flow. Do not represent any
of the retired features as marketplace operations until an approved executor,
persistent job model, and externally verified result are implemented.

The historical `login_username`, `encrypted_login_password`, and `show_browser`
columns remain in the schema to avoid a destructive automatic migration. The API
and browser must not echo these values or even password-presence state. A database
operator must remove legacy values manually, after a verified encrypted backup
and during an approved maintenance window. First record counts without selecting
credential values:

```sql
SELECT COUNT(*) AS rows_with_legacy_login_data
FROM xianyu_account_auth
WHERE login_username IS NOT NULL
   OR encrypted_login_password IS NOT NULL
   OR COALESCE(show_browser, 0) <> 0;
```

Then review and execute the cleanup as a separately approved change:

```sql
START TRANSACTION;

UPDATE xianyu_account_auth
SET login_username = NULL,
    encrypted_login_password = NULL,
    show_browser = 0
WHERE login_username IS NOT NULL
   OR encrypted_login_password IS NOT NULL
   OR COALESCE(show_browser, 0) <> 0;

DELETE FROM xianyu_sys_setting
WHERE setting_key LIKE 'frontend.account.auto_rate.%'
   OR setting_key LIKE 'frontend.account.strategy.%';

COMMIT;
```

Repeat the count query and application-level read-only checks after cleanup. If
the affected-row count differs from the reviewed estimate, roll back before the
commit and investigate; never print the legacy values into tickets or logs.

### Real-time delivery reconciliation

Migration 009 makes each payment event a persistent single-flight attempt. Treat
`unknown` as an operator-owned quarantine, not a retryable error: first inspect
the buyer conversation and marketplace order in the official client, then record
the reconciliation outcome through an approved operational procedure. Never reset
or reissue card items linked to an `unknown` attempt until the operator has proved
that the buyer did not receive them. Delivery records intentionally omit message
text and card secrets; use the local attempt ID and error code for incident
correlation instead of copying order, buyer, or content data into logs.

An explicit platform-confirmation failure after `message_sent` may retry only the
confirmation step. A `message_sending` or `platform_confirming` lease abandoned by
a crash becomes `unknown` after expiry and must not be automatically replayed.
Legacy `api` and `custom` modes are failed closed and visible as failed delivery
records; they do not call configured URLs or claim success.

### Notification test reconciliation

Migration 019 makes `POST /api/notifications/test` a durable, single-channel,
at-most-once operation. The browser must retain one idempotency key per selected
channel and reuse it after a timeout or reload. The API commits the sending state
before calling the provider; it never treats a transport exception, timeout, or
expired sending lease as a safe retry. Provider success and explicit rejection
are both terminal results. Delivery-log failure is reported separately as
`logPersisted=false`: retrying the original key may repair only that local log
and must never invoke the provider again.

An `unknown` test remains quarantined until an operator checks the provider and
uses the explicit high-risk resolution action with the latest attempt ID,
channel key, and original idempotency key. Resolution is mutation-audited, stores
only `resolved_at` plus `manual_reconciled`, sends no notification, and does not
automatically start a replacement test. A different browser key cannot resolve
or bypass an active, unknown, or audit-pending generation. Attempt tables and
delivery logs must not contain credentials, request/response bodies, notification
text, or rendered templates; incident records should use only attempt IDs and
bounded state/error codes.

### Notification event delivery

Migration 020 makes automatic Cookie-expiry and new-order notifications durable
across processes and restarts. The target lock is the tuple of internal event
type, account ID and an irreversible SHA-256 digest; raw marketplace identifiers,
message text, rendered payloads and channel credentials are prohibited from both
state tables. The API must commit `pending`/lease and then `send_started` before
the first provider call. Only an explicit delivered result becomes `confirmed`.

An explicit HTTP 4xx/provider business rejection, disabled/missing configuration
or an empty target set is a known outcome and may retry the same generation after
bounded backoff. Redirects, HTTP 5xx, timeout, transport exception, malformed 2xx
provider result, expired `send_started` lease or uncertain terminal-state commit
are `unknown`; they are never automatically resent. Verified Cookie recovery may
resolve the current generation, but cannot revoke an active `pending` or
`send_started` lease. An expired `send_started` attempt must first be persisted as
`unknown` without opening a replacement generation; only an expired `pending`
attempt that never crossed the provider boundary is safe to resolve directly.
A confirmed new-order generation remains occupied for 15 minutes
before a later event may create the next generation. Staging evidence must cover
two concurrent API replicas, both crash boundaries, restart reuse, zero-config
recovery and inspection proving that no message, order identity or secret was
persisted.

- MySQL: encrypted logical plus volume/snapshot backups, consistency checks,
  retention tiers, off-host copies, and point-in-time recovery if required.
- Redis: decide explicitly which data is authoritative. If AOF data is required,
  back it up consistently; never treat ephemeral rate-limit state as the only
  source of truth.
- Uploads/application data: preserve ownership, integrity metadata, and malware/
  content review status. Test missing-object and partial-restore behavior.
- Secrets: back up secret-manager metadata and recovery procedures, not plaintext
  `.env` files in general-purpose storage.
- Quarterly at minimum, restore to an isolated environment, run integrity and
  read-only feature checks, record duration, and destroy recovered secrets/data
  securely after the exercise.

## Rollback and incident rules

1. Preserve logs/evidence and identify the affected release and data window.
2. Stop unsafe automation or external ingress without deleting persistent data.
3. Roll back to a signed, previously validated image set; do not rebuild mutable
   tags during an incident.
4. Rotate affected credentials, revoke JWT/sessions and bridge/provider tokens,
   and verify crawler/browser processes have terminated.
5. Validate schema compatibility before application rollback. Database recovery
   requires an approved, tested procedure—not an ad hoc destructive command.
6. Run health and read-only smoke checks, monitor error/queue/backlog recovery,
   and obtain incident-owner approval before restoring automation.
