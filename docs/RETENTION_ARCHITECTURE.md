# Retention Architecture

GeoCore separates data for lifecycle decisions without asserting legal periods.

| Category | Examples | Purge treatment |
| --- | --- | --- |
| Workspace data | customers, projects, quotes, documents | eligible for deletion/anonymisation after the recovery window |
| Billing/accounting | subscription and invoice metadata | retained pending Phase 3 legal determination |
| Security/audit | authentication, deletion and purge evidence | retained pending Phase 3 legal determination |
| Suppression | bounce/complaint/unsubscribe records | retained to honour suppression pending legal determination |
| Backup | provider/volume copies | governed by the platform backup lifecycle; no duration asserted here |

The internal purge operation must not delete the latter categories merely
because a workspace deletion is eligible. Exact retention periods and any
legal holds are Phase 3 legal-review inputs.
