# Database migrations

Database changes are explicit deployment operations. The API and scheduler
worker perform a read-only schema check at startup and refuse to run when a
migration is pending or the database was migrated by a newer application build.
They never call `create_all` or issue `CREATE`, `ALTER`, or `DROP` schema DDL.

## Runner contract

From `apps/api`, using database credentials supplied through the environment or
an environment file (never command-line arguments):

```bash
python -m app.migrations status
python -m app.migrations upgrade
python -m app.migrations status
```

`Settings` resolves `MYSQL_APP_USER/MYSQL_APP_PASSWORD` for every runtime API
and Worker connection, while this CLI resolves
`MYSQL_MIGRATION_USER/MYSQL_MIGRATION_PASSWORD`. The legacy
`MYSQL_USER/MYSQL_PASSWORD` pair remains a development/backward-compatibility
fallback only. Do not populate only one field in a role pair, and never reuse a
runtime, migration, or root credential. SQLAlchemy URL rendering masks passwords;
operators must still avoid printing the resolved environment or Compose model.

`status` exits `0` only when the schema is current and exits `3` for a pending
or unknown version. `upgrade` discovers every `<number>_<description>.sql` file,
sorts by numeric version, acquires one MySQL `GET_LOCK`, and executes all files
through the same connection. A version is inserted into `schema_migration` only
after its complete script succeeds. The SHA-256 checksum of each applied file is
also pinned; an edited historical file makes `status`/startup fail closed instead
of being silently skipped. Already-recorded, matching versions are skipped.

An installation created before checksum tracking is adopted once under the same
MySQL lock: the runner adds the metadata column and records the current files as
the trusted baseline. That first adoption cannot prove which bytes were used by
an older manual deployment, so retain the reviewed release artifact and backup
as audit evidence. Every subsequent change is detected technically.

MySQL commits many DDL statements implicitly, so a failed file cannot be
transactionally undone. Every migration in this directory must therefore be
safe to rerun after any statement. Do not edit or renumber an applied file; add
the next numbered forward migration. Never add `DROP`, truncation, or destructive
data cleanup without a separately approved maintenance and recovery plan.

`001_init.sql` contains only session setup and `CREATE TABLE IF NOT EXISTS`, so
it is also a safe baseline for an existing database whose old migration history
is incomplete. SQL files must not write `schema_migration`; the runner owns that
record so a partial script can never claim success.

## Production maintenance sequence

1. Stop API/worker automation and verify the approved maintenance window.
2. Create an encrypted, access-controlled backup and test that it is readable.
3. Rehearse the exact migration against a recent restored staging copy. Record
   row counts, free disk, execution/lock duration, and the largest table rewrite.
   Migration 005 includes multiple `ALTER TABLE` operations and full-table
   compatibility backfills; assume it can hold metadata/table locks until target
   data volume measurements prove otherwise. Migration 008 takes ownership of
   the business-setting and notification tables that older builds created lazily
   during API requests; apply it before running API/worker identities without DDL
   privileges. Migration 009 adds the real-time delivery attempt/lease state and
   attempt-scoped card claims. After applying it, verify that API/worker database
   identities cannot bypass the migration gate and that `unknown` attempts remain
   quarantined for manual marketplace reconciliation rather than automatic retry.
   Migration 010 adds the AI auto-reply attempt state machine. Verify that an
   expired `message_sending` lease becomes `unknown`, that a `message_sent`
   attempt may only finalize its local chat row, and that encrypted reply text is
   cleared after local confirmation. Never reset an `unknown` row to `pending`;
   reconcile the buyer conversation in the marketplace first. Migration 011
   adds the per-account, configured-timezone daily quota. Verify that competing
   events cannot exceed the limit, same-event replays reuse one reservation,
   explicit no-send failures release their reservation, and confirmed/unknown
   outcomes remain occupied. An expired generation lease is a definite no-send
   and startup recovery releases it; an expired send lease remains unknown and
   occupied. The policy uses a half-open work interval and supports
   cross-midnight windows; invalid policy configuration fails closed.
   Migration 012 adds the manual text/image message attempt state machine.
   Every `/websocket/sendMessage` and `/websocket/sendImageMessage` caller must
   provide a stable `idempotencyKey` for the logical UI message and reuse that
   key only when `retrySafe=true`. Verify that an expired `sending` lease,
   acknowledgement timeout, transport ambiguity, or platform ACK followed by a
   local persistence failure becomes `unknown` and is never reclaimed for a
   second platform send. The table stores only SHA-256 digests, not message
   bodies, image URLs, raw conversation IDs, or raw peer IDs.
   Migration 013 adds the goods off-shelf attempt/lease state machine. Verify
   that `remote_confirmed` retries only the local `xianyu_goods.status=0`
   finalization, while an expired `in_progress` lease becomes `unknown` and
   cannot call the platform again. Only an explicit non-execution result may
   set `retry_safe=1`.
   Migration 014 adds the target index used to serialize publish and other
   external-operation intents by operation type and local business target.
   Verify that a second browser idempotency key cannot bypass an active,
   confirmed, or ambiguous attempt for the same target, and preserve the
   runtime lock order (`xianyu_goods` before the latest attempt lookup).
   Enable `COMMERCIAL_BACKEND_MUTATION_IDEMPOTENCY_ENABLED` only after the
   commercial provider contract proves that ad-application creation, feedback
   creation, and feedback replies honor the same key in the `Idempotency-Key`
   header and matching JSON body field. Unknown outcomes may only be replayed
   with that original key; never create a replacement intent.
   Migration 015 adds the inbound-message automation transactional outbox.
   Verify that each newly inserted chat message and its independent `delivery`
   and `ai` branch rows commit atomically; the outbox must contain only the chat
   row reference and a source digest, never a second copy of buyer content.
   Exercise an API crash after commit and an expired `processing` lease: the
   continuous API poller must recover both branches through their downstream
   exactly-once attempt state machines. An `unknown` downstream send remains
   quarantined with `retry_safe=0`; never reset it for an automatic resend.
   Migration 016 adds a durable commercial ad-payment target mutex plus retained
   attempt generations for each application.
   Enable `COMMERCIAL_BACKEND_PAYMENT_IDEMPOTENCY_ENABLED` only after the
   commercial provider contract proves that both payment-order **creation and
   close** honor the same key in the `Idempotency-Key` header and matching JSON
   body field. Verify concurrent browser keys create one row and one remote
   order; repeated close calls for one order must reuse the stable derived key.
   A timeout, interrupted lease, or ambiguous
   database confirmation becomes `unknown` with `retry_safe=0`; recovery may
   call the provider only with the original key. Reconcile `remote_order_no`
   against the commercial service before manual intervention. Only an explicit
   bridge `closed`/`expired` result may release the target for a new generation;
   `confirmed` and `unknown` still block a different key. Neither table may
   contain contact fields, bridge response bodies, payment/QR URLs, or credentials.
   Migration 017 adds the database-enforced delivery-config-to-goods foreign
   key. It intentionally performs no orphan cleanup: a failure means the
   deployment must stop while operators reconcile the reported legacy rows
   from approved evidence. Migration 018 adds the `(created_time, id)` audit
   retention index and durable singleton schedule. Rehearse the index build on
   production-scale data, verify the worker deletes only bounded batches, and
   confirm the MySQL named lock is released on its owning connection before
   commit/rollback returns that connection to the pool. Every non-empty batch
   must atomically leave one metadata-only `AUDIT_RETENTION` record with the
   policy days and deleted count; empty runs must not create audit noise. HTTP
   2xx mutations are
   completed, 4xx mutations are rejected, and redirects/5xx outcomes remain
   unknown for reconciliation; never relabel a rejected request as a completed
   business action.
   Migration 019 adds the per-user/per-channel notification-test target mutex
   and retained attempt generations. Verify that the API commits `in_progress`
   before invoking a provider; a normal provider success or rejection becomes
   `confirmed`, while transport ambiguity and an expired `in_progress` lease
   become non-retryable `unknown`. An expired pre-send `pending` lease may be
   reclaimed only with its original idempotency key. Delivery-log persistence
   is a separate local transaction: `confirmed + log_persisted=0` must block a
   new key and the original key may repair only the log without another provider
   call. An operator may resolve `unknown` only after external reconciliation,
   using the authenticated user, latest attempt ID, channel key, and original
   key; that audited action sets `resolved/manual_reconciled` and never sends.
   Neither table may contain channel secrets, message text, rendered templates,
   or request/response bodies. The migration creates the retained attempt table
   first, then adds the target mutex with a nullable `latest_attempt_id` foreign
   key using `ON DELETE/UPDATE RESTRICT`; the coordinator also repairs/stops on a
   stale pointer under the target lock rather than creating a parallel send.
   Migration 020 replaces process-local Cookie/new-order suppression with a
   per-event/account/SHA-256 target mutex and retained delivery generations.
   The coordinator commits `pending` plus a lease and then commits
   `send_started` before invoking any channel. Confirm only an explicitly
   delivered result. A known rejection or known local non-call enters bounded
   backoff and may reuse the same generation. HTTP redirects/5xx, malformed 2xx,
   transport ambiguity, or an expired `send_started` lease become `unknown` and
   must never auto-replay. Cookie recovery is an explicit durable resolution,
   but must not revoke an active `pending`/`send_started` lease; an expired
   `send_started` attempt is first quarantined as `unknown` without opening a new
   generation. A confirmed new-order
   generation expires after 15 minutes, after which the mutex may advance to a
   new generation. Rehearse concurrent replicas, pending/send-started crash
   recovery and restart reuse. Both tables contain only event type, account ID,
   irreversible target digest, bounded state/result flags and timestamps; they
   must never contain marketplace identifiers, message text or channel secrets.
4. Run the migration job, then the read-only status command. Do not terminate an
   apparently idle DDL operation without checking MySQL process/lock state.
5. Start the application build only after status reports `current`.

The Compose stack has a one-shot `migrate` service. `api` and `worker` depend on
its successful completion. To run a planned upgrade explicitly:

```bash
docker compose stop api worker
docker compose run --rm migrate
docker compose run --rm migrate python -m app.migrations status
docker compose up -d api worker
```

On a brand-new MySQL data volume, the mounted
`deploy/mysql/init/010-least-privilege-users.sh` provisions two accounts without
placing passwords in process arguments: the runtime account receives only
`SELECT`, `INSERT`, `UPDATE`, and `DELETE` on `MYSQL_DATABASE`; the migration
account receives database-scoped privileges needed by the numbered migrations,
without `GRANT OPTION`. The script revokes pre-existing grants before applying
that allowlist and rejects shared/reserved identities and reused credentials.

MySQL entrypoint initialization does not rerun on an existing data volume. Before
upgrading an older installation, a database administrator must execute the same
reviewed revoke/grant policy over a local socket, verify it with `SHOW GRANTS`,
then rotate the managed secrets and run preflight. Recreating only the container
does not provision or rotate accounts. Never delete a production volume merely
to trigger initialization.

Example logical backup without putting a password in the host process arguments:

```bash
umask 077
docker compose exec -T mysql sh -ec '
  export MYSQL_PWD="$MYSQL_ROOT_PASSWORD"
  exec mysqldump --protocol=socket -uroot --single-transaction \
    --routines --events --triggers "$MYSQL_DATABASE"
' > "backup-$(date +%Y%m%d-%H%M%S).sql"
```

The dump contains production data and must be encrypted/moved to the approved
backup store immediately. Do not use a plaintext dump as a long-lived backup.

## Rollback compatibility

There is deliberately no automatic `downgrade` command. Before an application
rollback, confirm the older build is forward-compatible with every applied
schema version. Prefer a reviewed forward-fix. If schema/data recovery is
unavoidable, stop all writers and restore the verified pre-upgrade backup into
an isolated database first; validate it before switching production. Never
delete rows from `schema_migration` to imitate a rollback.
