# Step 1: online Materials receipt checklist

The active task is deliberately limited to two source sheets:

- September online-payment rows in **2026 EXPENSES 3rd Quarter.xlsx → Material Expense**.
- **9 SEPTEMBER 2026.xlsx → September Cash Voucher**, default account **Materials**, with other accounts available in the filter.

The entire September Cash Voucher register is retained regardless of receipt date. Older dates and blank receipt dates do not remove an entry from the search. Cash, GCash and cheque payments are outside the online-payment source. Two September Material Expense rows labelled Cash were excluded rather than relabelled.

## Read the result

- **S.I.# already listed:** the S.I.# number is already listed, or you manually confirmed the receipt. If supplier/TIN differs, verify identity. This is not an allocation or proof that the payment amount settled that invoice.
- **Possible match — review:** supplier or amount evidence suggests an existing receipt, but no exact confirmed S.I.# link exists.
- **No candidate found:** no candidate was found in the selected account. Verify supplier and S.I.# before concluding that the receipt is missing.
- **In another account:** the S.I.# is already in Cash Voucher under another account. Do not enter it again just because it is not categorised as Materials.

Use the account, status and search filters. Expand Cash Voucher evidence to see its source row, supplier, date, S.I.# and recorded amount paid. Confirm same receipt or reject a candidate. Neither action changes money or performs total reconciliation.

Download the checklist to get separate lists for each result and the selected Cash Voucher rows. Original Excel files remain unchanged.

## Dataset reset

The previous complete dataset and document links are archived in `data/before-materials-step1-*.zip`. Active data was rebuilt from the original sources. Allocations and prior matches were cleared. Current counts and exclusions are in `data/materials-step1-manifest.json`. Supplier and COA reference data remain available internally, but the earlier full-workbook interface is outside the active step.

Run `start.bat` to open the local checklist. No photo uploads, total balancing, GCashCheck, cheque-voucher or non-receipt workflow is required for this step.
