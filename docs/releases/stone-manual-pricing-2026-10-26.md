# Stone quote: owner-controlled job pricing and invoice documents

The stone editor now has five steps: Material, Layout, Design details, Pricing, Review. New material names start empty. Catalogue selection identifies the stone; arbitrary typed names work without a catalogue match. Imported catalogue/custom drafts keep their specified material identity but never supply the job selling price.

Pricing requires an explicitly entered job subtotal. Discount is a percentage (0–100), deducted before optional VAT. VAT starts switched off; when selected, its editable rate starts at 20%. Server-side Decimal arithmetic rounds money to pennies. No catalogue price, seeded material price, slab allocation, wastage or automatic installation surcharge is used on this manual path. Legacy calculator clients and existing stored quote values are unchanged.

One job amount covers the complete specification. The first stored item carries the subtotal and remaining specification items carry zero; customer documents and the quote detail screen suppress invented per-piece prices and present the overall job price. The persisted item snapshots identify this pricing mode and retain the discount percentage. PDF subtotal, discount, VAT and total reconcile with the saved values.

Invoice references are allocated on first successful PDF generation under a tenant row lock, then persisted and reused on every download. Each workspace starts at Invoice-000001. Company Settings exposes the invoice prefix and next sequence. Previously used references are skipped, a database uniqueness constraint prevents tenant-local duplicates, and existing assigned numbers are not changed by settings updates. A PDF generation failure does not commit a sequence change. Authenticated and customer-portal downloads share the same allocator. Download filenames use the assigned reference, including across the API/web origin boundary.

PDF descriptions use escaped, wrapping Paragraph cells with embedded Vera fonts, vertical top alignment, repeatable table headers, row splitting for long specifications and page/reference footers. Embedded fonts avoid printer-specific font substitution. Real PDF parsing replaces regex stream inspection in document tests.

## Validation at preparation

- 21 focused backend/manual-price/document checks passed (one database integration test excluded because no PostgreSQL service is available locally).
- 5 existing pure PDF/tenant identity checks passed.
- 400 web component checks passed, including manual pricing, empty materials and numeric invoice sequence settings.
- TypeScript passed. PDF one-page and multi-page previews rendered and visually inspected.
- SQLite tests prove persistence, per-tenant sequencing, repeated downloads and collision skipping. Actual PostgreSQL migration, concurrent invoice allocation and hosted browser checks remain CI release gates.

## Deployment order

1. Require green backend, web and browser CI and review this migration.
2. API first, applying Alembic 94e5f6a7b8c9 (additive tenant sequence fields and nullable quote invoice number).
3. Confirm API health, then deploy web from the same reviewed release SHA.
4. Authenticated smoke: blank material; arbitrary typed stone; manual price 3000, 10% discount, VAT 20% produces 3240; VAT off produces 2700; download Invoice-000001, re-download unchanged; inspect long descriptions; change prefix/sequence and confirm future invoices only.

No production deployment, migration, real customer modification, email or payment is performed by preparing this patch. The separate verification-email PR is not included.
