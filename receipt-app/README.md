# Jolyn TAE - Material Expense upload and receipt matching

Current workflow: [MATERIAL_EXPENSE_GUIDE.md](MATERIAL_EXPENSE_GUIDE.md). All payment modes, editable image drafts, supplier/COA lookup, and monthly Cash Voucher imports are enabled locally. Earlier Step 1 notes below describe the previous scope.

---

# Tally ? online Materials receipt checklist

## Current scope: Step 1

Online Material Expense payments versus September Cash Voucher receipt presence. Open [STEP1.md](STEP1.md). The active screen checks whether receipts are already listed; it does not reconcile totals. The earlier full-workbook interface below is historical and is not the current task.

---

# Tally ? complete local workbook workspace

Start with **[USER_GUIDE.md](USER_GUIDE.md)**. Double-click `start.bat` to start/reuse the local server and open http://127.0.0.1:5050.

Every worksheet in both original workbooks has a working sidebar module. Supplier and COA masters are shared, expense entries drive calculated summaries, allowances support receipt settlement and returned funds, and monthly voucher registers retain grouped receipt numbers. Batch photo intake supports editable OCR drafts, file-hash duplicate detection, reference/S.I# duplicate checks, and attachment to existing entries.

The complete month-end download contains both regenerated workbooks (nine and five tabs), detailed reconciliation, totals and unresolved checks. Original source files are never overwritten. See the user guide for report treatment of controls, personal/mixed groups, advances, tax figures and historical external snapshots.

## Setup

Dependencies: `python -m pip install -r requirements.txt`.

Run directly: `python app.py`. The launcher runs one server and opens the browser; the server binds only to 127.0.0.1. This is a trusted single-computer application, not a publicly hosted service.

## Data and backup

`data/receipts.sqlite3` holds records and source evidence; `data/uploads/` holds images and `data/templates/` retains source workbooks. Use the app backup download for a consistent snapshot including photos and templates. The app has no automatic cloud sync. Workbook snapshots and the full audit may contain financial and personal information.

OCR runs through Tesseract.js in the browser; initial engine and language downloads need internet. Fonts load from Google Fonts with a fallback. No real photograph has yet been supplied for measuring OCR accuracy. Missing or uncertain fields require review. Supported image types are PNG, JPG and WebP.

## Verification

Run `python -m unittest discover -s . -p "test_*.py"` from this directory. Tests use separate temporary databases. They cover fourteen modules, shared master edits, grouped/partial matches, tax amount preservation, duplicate photo intake, attachment, returns, undo/idempotency, and complete workbook tab generation with cached totals.

The source-cell and formula audit is `EXCEL_WORKFLOW_AUDIT.md`; it records findings from before the system changes and is historical. `USER_GUIDE.md` describes the current implementation. Raw all-sheet evidence remains in `data/workbook-audit.json`.
