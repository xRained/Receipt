# Tally: your Excel workflow on this computer

Double-click **start.bat**. It opens the app and reuses the existing server. Choose your working month (September 2026 initially).

## Use the modules you already know

All fourteen original worksheets have a corresponding module in the sidebar. Quarterly and monthly supplier/COA modules share one editable master, so you do not maintain two copies.

| Workbook module | What you can do |
|---|---|
| Material Expense | Add/edit payments, supplier/TIN/address, reference, receipt numbers, project, COA, principal and fees; link supporting receipts |
| Cost of Sales Expense | Record direct costs and their payment evidence; select the account and project |
| Operating Expense | Record operating costs using the same supplier and COA masters |
| COS_Allowance | Record advances, link settlement receipts, record unused amounts returned, see outstanding balances |
| GCashCheck | Add/edit cash and GCash daily controls and named cheque controls; compare with details at month-end |
| Expense Summary | Automatic daily payment totals by category and method, with personal amounts separate |
| SummaryMonth | Automatic monthly totals plus clearly labelled historical source snapshots |
| Suppliers List / Suppliers | Add/edit the shared supplier master; fill future entries from it |
| Copy of Accounts / COA | Add/edit the shared Chart of Accounts; fill future entries from it |
| Cash Voucher | Record receipt/voucher details, gross, input taxes, withholding and recorded net payable; retain all grouped S.I# values |
| Check Voucher | Record cheque references and grouped receipt evidence; preserve original line-level source evidence |
| Non Receipt | Record expenses without receipts separately from missing physical receipts |

## Upload instead of typing twice

From **Start here**, choose payment photos or receipt photos. You can select several. The browser reads each image and opens an editable draft. Check the date, amount and reference before Save; saving or closing proceeds to the next photo.

If an entry already exists, use **Attach photo to this entry**. Do not create another expense. Identical uploaded images are detected by their file hash. Supplier and account fields use the master and unambiguous history. Ambiguous fields stay for review.

Images are processed locally by browser OCR; initial engine/language download needs internet. PNG, JPG and WebP are supported. OCR quality must be checked against actual photos; text interpretation tests do not guarantee accurate image recognition.

## Reconcile

Exact unique supplier/amount matches can link automatically. Explicit receipt lists support one payment against several receipts; shared receipt numbers support several partial payments against one receipt. Fees stay outside the principal allocation.

**Reconciliation** groups likely exceptions and explains different names, conflicting TINs and amount differences. Confirm only after checking the supporting evidence. Remember a supplier relationship only if you verified it. Undo blocks automatic recreation of that link. Small differences are not silently written off.

Older payment dates can match September-collected receipts. The collection month and document date are separate. Do not treat July/August as missing September receipts by default.

## Finish the month

Use **Month-end & Excel** to check controls, open balances, personal/mixed groups and source tax arithmetic. Missing control totals are unknown, not zero.

**Download complete month-end package** produces:

- Quarterly expense workbook, all nine original sheet names.
- Monthly voucher workbook, all five original sheet names.
- Detailed reconciliation workbook.
- Export totals and unresolved-check manifests.

The original column positions, headers and source styles are used; detail areas and summaries are regenerated. Grouped S.I#s are displayed together. Original templates and line-level evidence remain in the local database. This is not a byte-for-byte copy of the original formulas: generated summaries use cached formula results; historical external-source figures remain labelled snapshots.

Payment records, receipt records and cash controls are different evidence for the same activity. Do not add all three as expenses. Summary totals represent recorded payment movement; advances remain advances until supported or returned. Recorded tax figures are preserved and editable; the app does not assume a universal tax rate.

## Keep a backup

Use **Back up records & photos** periodically. It contains a consistent SQLite snapshot, uploaded images and workbook templates. The app remains on localhost. The original Excel files are never overwritten.

## September-only reset

The active dataset was rebuilt from the original workbooks for September 2026. It includes September-dated quarterly payments and the complete September receipt/voucher collection, including older or blank receipt dates. July/August and undated quarterly payments are excluded from the active ledger. Reference suppliers and COA remain available. Historical monthly summaries and non-September controls are not included. The pre-reset backup and exclusion manifest are under data/. Prior manual edits, links and image associations remain in the backup rather than being carried into the rebuilt dataset.
