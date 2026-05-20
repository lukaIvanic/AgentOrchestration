# Metrics Label Cardinality Policy

Deployment validates metric labels before rollout when either:

- the manifest embeds a `metrics` schema,
- the manifest points to a schema with `metrics_schema` / `metricsSchema`, or
- the CLI is run with `ao deploy --metrics-schema`.

## Allowed Labels

Metric labels need an owner and documented bounded values. Good labels describe
small controlled sets such as:

- `event_type`: `queued`, `started`, `completed`, `failed`
- `worker_pool`: `default`, `gpu`, `batch`
- `status`: `success`, `error`, `timeout`

## Blocked Labels

Labels that can grow with users, requests, paths, tokens, sessions, timestamps,
or worker IDs are treated as unbounded unless they have an approved exception.
Unbounded labels block rollout because they can increase observability cost and
degrade query performance.

## Exceptions

An exception must name the metric, label, owner, approver, and reason. Exceptions
should be temporary and reviewed by the observability owner before production
rollout.

```json
{
  "metrics": [
    {
      "name": "task_events_total",
      "labels": [
        {
          "name": "event_type",
          "owner": "observability",
          "values": ["queued", "started", "completed", "failed"]
        }
      ]
    }
  ],
  "exceptions": [
    {
      "metric": "worker_events_total",
      "label": "worker_id",
      "owner": "observability",
      "approved_by": "sre-lead",
      "reason": "Temporary one-release debugging window."
    }
  ]
}
```
