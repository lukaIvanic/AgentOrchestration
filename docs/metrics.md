# Metrics Label Cardinality Policy

Deployments must keep metrics labels bounded before rollout. Any new metric label must either use one of the allowed policy labels below, declare a finite `allowed_values` list with 20 values or fewer, or include an approved owner exception in the deployment manifest.

## Allowed Labels

| Label | Allowed values |
| --- | --- |
| `agent_type` | `worker`, `monitor`, `scheduler`, `gateway` |
| `environment` | `dev`, `staging`, `prod` |
| `event` | `enqueue`, `dequeue`, `complete`, `fail`, `retry` |
| `outcome` | `success`, `failure`, `timeout`, `skipped` |
| `priority` | `low`, `normal`, `high`, `critical` |
| `queue` | `default`, `priority`, `dead_letter` |
| `region` | `local`, `us-east`, `us-west`, `eu`, `apac` |
| `status` | `pending`, `running`, `completed`, `failed`, `paused`, `stopped` |
| `worker_type` | `processor`, `analyzer`, `watcher`, `executor` |

## Blocked Unless Approved

Labels such as `task_id`, `worker_id`, `agent_id`, `user_id`, `request_id`, `trace_id`, `session_id`, `run_id`, `timestamp`, `path`, `url`, `host`, `ip`, and `email` are treated as high-cardinality labels. They block deploy unless the manifest includes an approved exception with an owner and reason.

```yaml
metrics_cardinality_exceptions:
  - metric: task_debug_total
    label: task_id
    approved: true
    owner: observability
    reason: temporary debug-only rollout
```
