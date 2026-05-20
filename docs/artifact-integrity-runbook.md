# Artifact Integrity Runbook

## Digest Mismatch Alert

`artifact_digest_mismatch` is a critical integrity alert. It means a blob
downloaded through the artifact manifest reader did not match the SHA-256 digest
recorded in its manifest.

## Immediate Response

1. Treat the affected blob as corrupted or tampered with.
2. Keep the blob quarantined and do not reuse it from cache. If a quarantine
   marker directory is configured, leave the blocked marker in place until
   recovery is complete.
3. Compare the manifest digest against the upstream producer logs.
4. Rehydrate the artifact from a trusted source only after the producer digest
   and storage copy agree.
5. If multiple artifacts from the same storage prefix fail, disable reads from
   that prefix until storage health checks complete.

## Recovery

Replace the blob with a verified copy, regenerate the manifest if the producer
digest was wrong, and clear the quarantine entry or persistent marker only after
a successful read-through verification.
