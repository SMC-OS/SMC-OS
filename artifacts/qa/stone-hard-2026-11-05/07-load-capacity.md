# 07 — Load and capacity

**Status: BLOCKED. No load test was run, and no capacity figure is claimed.**

| Requirement | State | Reason |
|---|---|---|
| Staged load at 1, 5, 10, 25, 50 and 100 concurrent users, with isolated A/B tenants, quote saves, PDFs and uploads | Not run | The target is staging running the release SHA. Staging does not run it (00/06). Load against the current staging build would measure different code |
| p50/p95/p99, throughput, DB pool waits, CPU and memory | Not measured | Same |
| 30-minute soak and 1,000+ mixed journeys | Not run | Same; also needs owner agreement on the staging cost and noise window |
| "Supports N businesses" | No claim | Businesses are not concurrent users; nothing has been measured |

## What is known (not capacity evidence)

- Each API service runs a single replica (`numReplicas: 1`) with a local upload volume, so uploads are not shared and cannot scale horizontally without a storage change (ADR-032).
- The new receipt row lock serialises deliveries per PO, not globally. Contention only occurs on the same PO.

## Next safe action

After the staging deploy is approved (06): run a bounded k6 or Locust profile from the operator machine against staging, using synthetic tenants only. Stop on any 5xx spike, cross-tenant read, data mismatch or pool exhaustion. Record the deployment ID and SHA with the results.
