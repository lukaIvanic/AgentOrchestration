# Sidecar Runtime Hardening

Sidecar containers in `infra/docker-compose.yml` run with read-only root filesystems. Any path that must be writable is declared as a bounded tmpfs mount so runtime writes stay explicit and temporary.

| Service | Writable paths | Reason |
| --- | --- | --- |
| `metrics-sidecar` | `/tmp/ao-metrics`, `/run/ao` | Scratch metrics buffer and runtime pid/socket files |
| `log-forwarder-sidecar` | `/tmp/ao-logs`, `/run/ao` | Scratch log buffer and runtime pid/socket files |

Sidecar definitions are valid only when they set `read_only: true`, declare every writable path through `tmpfs`, drop all Linux capabilities, and enable `no-new-privileges:true`. Writable bind mounts are rejected for sidecars; use a named service-specific tmpfs entry instead.
