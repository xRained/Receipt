# Material Expense: entry, image upload and monthly receipt matching

The workspace supports **Online Payment, Bank, GCash, Cheque and Cash**. All five modes use the same Material Expense columns. Matching is a receipt-presence check; it does not require aggregate payment and voucher totals to balance.

## Existing reference data

Supplier names, TINs and addresses are stored in SQLite from **Suppliers List / Suppliers**. Account codes and titles come from **Copy of Accounts / COA**. Use **Suppliers & COA** to search, add/update records or import a reference workbook. Master changes populate future drafts; they do not rewrite historical transactions.

The current local database contains 1,373 suppliers and 80 account codes. The September Material Expense ledger includes its original 51 Online Payment rows and two Cash-labelled rows. GCash, Bank and Cheque are available for new entries; no transactions are invented for modes absent from the source.

## Upload payment evidence

1. Choose a working month.
2. Select **Upload payment images**; several PNG/JPG/WebP images can be queued.
3. Browser OCR extracts text and fills an editable draft: date, payment mode, supplier/payee, reference or cheque number, S.I.# when available, amount and fee.
4. A recognised supplier fills TIN/address from the database. The Material Expense form defaults to `CS-0001 / Materials`; you can select another recorded account.
5. Review the image and fields, then save. The next queued image opens automatically. **Add payment** supports manual entry.

Missing or ambiguous fields stay for review. OCR requires an initial internet download of its engine and language data. The images are processed in the browser. Text-parser tests are not a measurement of OCR quality on your actual photographs.

If an image/reference belongs to an existing transaction, use **Attach image instead of creating a duplicate**. Editing an entry also provides links to attached source documents.

## Bring in the next Cash Voucher collection

Select the collection month, such as October 2026, then use **Import monthly Cash Voucher** to upload its XLSX workbook. The importer reads Cash Voucher sheets, including merged receipt groups, and retains all their document dates. July receipts collected in October remain in October's collection. September is retained separately.

You can also use **Upload voucher images** to create Cash Voucher drafts, with the current collection month and a separate receipt date/recorded amount paid.

After saving/importing:

- Existing S.I.# evidence is shown automatically.
- A missing S.I.# can be linked automatically only when supplier/TIN and amount identify one candidate in both directions, with no conflicting TIN or rejected pair. The linked receipt number appears in the ledger/export.
- Multiple candidates, supplier conflicts and unexplained differences remain for review.
- Partial payments can each point to the same known S.I.#; no artificial balancing allocation is needed for the presence check.

Use the payment-mode and account filters. By default, payments from all months are available, so an October collection can contain receipts for September payments. Turn off **Show payments from all months** to limit the ledger and matching source to the selected month.

Re-importing the same workbook skips existing source rows. Changed source rows are reported as conflicts and are not silently overwritten. Reference-only imports update the supplier/COA master. Original Excel files are never modified.

## Export

**Export Material Expense** creates the original fourteen columns, including principal, fees and payable amount. Confirmed/uniquely linked receipt numbers fill the exported receipt column when the payment had none. **Download checklist** exports the current receipt-presence results and selected voucher collection.

## Local versus Vercel

This workflow is writable on the local computer, with a pre-change backup under `data/before-material-entry-*.zip`. The GitHub repository excludes the database and documents. Vercel remains an empty, read-only preview until persistent storage and access control are configured.
