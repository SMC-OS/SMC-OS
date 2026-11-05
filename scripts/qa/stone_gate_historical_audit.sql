-- STONE-GATE / DEF-003 historical audit. READ-ONLY: SELECT statements only,
-- run inside a READ ONLY transaction. It changes no data.
--
-- Before the fix, a requirement could be set to `received` when only one of
-- several linked PO lines was delivered, or when less than required_quantity
-- arrived. The fix is forward-only and does not rewrite history, so rows
-- found here need a human decision; they are never corrected automatically.
--
-- Usage (operator, against a replica or with explicit approval):
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f scripts/qa/stone_gate_historical_audit.sql
-- Output holds tenant/project ids only: keep it out of the public repository.

BEGIN TRANSACTION READ ONLY;

WITH line_totals AS (
    SELECT
        poi.material_requirement_id AS requirement_id,
        poi.id AS item_id,
        po.status AS po_status,
        poi.quantity AS ordered,
        poi.unit AS line_unit,
        COALESCE((SELECT SUM(pri.quantity_received)
                  FROM purchase_receipt_items pri
                  WHERE pri.purchase_order_item_id = poi.id), 0) AS received
    FROM purchase_order_items poi
    JOIN purchase_orders po ON po.id = poi.purchase_order_id
    WHERE poi.material_requirement_id IS NOT NULL
),
per_requirement AS (
    SELECT
        requirement_id,
        COUNT(*) AS linked_lines,
        SUM(received) AS total_received,
        BOOL_AND(received >= ordered - 1e-6) AS every_line_delivered,
        COUNT(*) FILTER (WHERE po_status IN ('draft', 'approved') AND received > 0) AS receipts_on_unordered_po
    FROM line_totals
    GROUP BY requirement_id
)
SELECT
    r.tenant_id,
    r.project_id,
    r.id AS requirement_id,
    r.status,
    r.required_quantity,
    r.unit,
    p.linked_lines,
    p.total_received,
    p.every_line_delivered,
    p.receipts_on_unordered_po,
    CASE
        WHEN p.receipts_on_unordered_po > 0 THEN 'receipt recorded on a draft/approved PO'
        WHEN r.required_quantity IS NOT NULL AND p.total_received < r.required_quantity - 1e-6
            THEN 'received total below required_quantity'
        WHEN NOT p.every_line_delivered THEN 'not every linked line delivered'
    END AS suspect_reason
FROM project_material_requirements r
JOIN per_requirement p ON p.requirement_id = r.id
WHERE r.status = 'received'
  AND (
        p.receipts_on_unordered_po > 0
     OR (r.required_quantity IS NOT NULL AND p.total_received < r.required_quantity - 1e-6)
     OR NOT p.every_line_delivered
  )
ORDER BY r.tenant_id, r.project_id;

-- Delivered PO lines that were never linked (the reported symptom): these
-- may be holding a project's gate shut. Linking is a manual, per-line
-- decision in the Materials tab; nothing is matched by name or quantity.
SELECT
    po.tenant_id,
    po.project_id,
    po.reference,
    poi.id AS item_id,
    poi.quantity,
    COALESCE(SUM(pri.quantity_received), 0) AS received
FROM purchase_order_items poi
JOIN purchase_orders po ON po.id = poi.purchase_order_id
LEFT JOIN purchase_receipt_items pri ON pri.purchase_order_item_id = poi.id
WHERE poi.material_requirement_id IS NULL
  AND po.project_id IS NOT NULL
  AND po.status <> 'cancelled'
GROUP BY po.tenant_id, po.project_id, po.reference, poi.id, poi.quantity
HAVING COALESCE(SUM(pri.quantity_received), 0) > 0
ORDER BY po.tenant_id, po.project_id;

ROLLBACK;
