# Backup and restore safety contract

This document describes the repository's fail-closed backup evidence and
restore-planning contract. It is not evidence that a production backup or a
restore drill has completed.

## Current scope

[`scripts/backup_restore.py`](../scripts/backup_restore.py) is deliberately
read-only. It can:

- validate a completed backup bundle without extracting it;
- validate an isolated restore project name;
- compute a retention plan without deleting anything.

It cannot create, encrypt, upload, extract, restore, start, stop, or delete
data. There is no apply, execute, or delete command.

The required backup components are:

- `mysql_data`: primary relational data;
- `redis_data`: security and runtime state whose restoration can revive old
  sessions or replay-protection records;
- `api_uploads`: user-uploaded content;
- `api_data`: API-owned durable files.

All four components are required. A partial bundle is invalid.

## Bundle contract

A bundle has this layout:

```text
<bundle>/
  manifest.json
  COMPLETE
  components/
    api_data.tar
    api_uploads.tar
    mysql_data.tar
    redis_data.tar
```

`manifest.json` uses strict schema version 1. Unknown or duplicate JSON keys
are rejected. Timestamps must be canonical RFC 3339 UTC values ending in `Z`.
An unverified bundle records `verifiedAt` as JSON `null`; it must not omit the
field or use a placeholder string.

`verifiedAt` is an operator attestation, not something this validator can
invent or independently prove. It may be populated only after the project's
approved verification procedure has produced accountable evidence. Until a
real isolated restore procedure exists, production records must keep it null.

```json
{
  "schemaVersion": 1,
  "backupId": "706c535e-fcc9-4a74-9056-77a680125b73",
  "createdAt": "2026-07-11T04:00:00Z",
  "productionProject": "xianyu-production",
  "verifiedAt": null,
  "components": [
    {
      "name": "api_data",
      "archive": "components/api_data.tar",
      "bytes": 10240,
      "sha256": "<64 lowercase hexadecimal characters>"
    }
  ]
}
```

The example abbreviates the component array for readability. A real manifest
must contain each required component exactly once, and `bytes` and `sha256`
must match the archive on disk.

`COMPLETE` is created only after all component archives and `manifest.json`
have been durably written by a future backup operator. It is strict JSON:

```json
{
  "schemaVersion": 1,
  "backupId": "706c535e-fcc9-4a74-9056-77a680125b73",
  "completedAt": "2026-07-11T04:06:00Z",
  "manifestSha256": "<SHA-256 of the exact manifest.json bytes>"
}
```

Validation rejects a missing or malformed marker, a mismatched backup ID, a
non-UTC timestamp, or a digest that does not bind the exact manifest bytes.
SHA-256 detects a mismatch against the recorded bytes; it does not authenticate
an untrusted writer. Signing and immutable storage remain separate production
requirements.

Run the read-only validator with:

```text
python scripts/backup_restore.py validate-bundle --bundle <bundle-directory>
```

The validator never extracts the archives. Tar metadata is rejected when it
contains an absolute or Windows-ambiguous path, `..` traversal, duplicate
member path, device/FIFO or unsupported member type, or a symbolic/hard link
whose target escapes the archive root.

## Isolated restore naming

Every future restore drill must use a separate Compose project. The accepted
name is exactly `restore-<canonical-lowercase-UUID>` and must not equal the
production project name, including a case-insensitive comparison.

```text
python scripts/backup_restore.py validate-restore-project \
  --project restore-706c535e-fcc9-4a74-9056-77a680125b73 \
  --production-project xianyu-production
```

Name validation is only a guardrail. It does not start a restore environment
and does not prove network, volume, port, or credential isolation.

## Retention planning

Retention input is a strict, non-secret catalog:

```json
{
  "schemaVersion": 1,
  "records": [
    {
      "backupId": "706c535e-fcc9-4a74-9056-77a680125b73",
      "createdAt": "2026-07-11T04:00:00Z",
      "verifiedAt": "2026-07-11T04:05:00Z",
      "legalHold": false
    }
  ]
}
```

The planner protects every legal-hold record, the latest verified backup, the
latest backup overall, the configured number of recent verified backups, and
records inside the age window. Other records are only labeled
`delete_candidate`; the script has no deletion path.

```text
python scripts/backup_restore.py plan-retention \
  --catalog <retention-catalog.json> \
  --as-of 2026-07-11T00:00:00Z \
  --max-age-days 30 \
  --keep-verified 7
```

Output always contains `"mode":"plan"` and `"destructive":false`.

## Secret handling

None of these commands accepts passwords, tokens, encryption keys, or other
secret values. Unknown arguments are not echoed, and strict input errors never
print unknown field values. A future backup operator must obtain secrets from
a dedicated runtime secret provider and keep them out of process arguments,
manifests, catalogs, logs, and shell history.

## Evidence still required before production use

The following work has **not** been completed by this contract implementation:

- no Docker command or production service operation has been run;
- no crash-consistent MySQL/Redis snapshot procedure has been implemented;
- no encryption, key rotation, off-site replication, or immutable storage has
  been implemented;
- no isolated restore has been executed against real backup bytes;
- no application-level integrity, session-revocation, migration, or rollback
  acceptance has been performed after a restore;
- no measured RPO/RTO, restore duration, load test, or operator sign-off exists.

Production readiness requires a real, isolated, documented restore exercise
with representative encrypted data and accountable human approval. Until that
evidence exists, this repository provides safety primitives only—not a proven
backup and disaster-recovery system.
