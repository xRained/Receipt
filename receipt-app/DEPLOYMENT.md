# Jolyn TAE — Tangaw, Atiris, Esmiringhoy

## GitHub contents

The repository contains application source, tests and setup documentation. Databases, receipt images, uploaded workbooks, generated spreadsheets, backups, logs, financial audit reports and credentials are excluded.

The local September dataset is not included. A fresh checkout starts empty. It does not read the original Excel files automatically.

## Local use

1. Open a terminal in `receipt-app`.
2. Install dependencies with `python -m pip install -r requirements.txt`.
3. Run `python app.py` and open http://127.0.0.1:5050. On Windows, `start.bat` also opens the browser.

The existing computer keeps using its original `receipt-app/data/` directory. `RECEIPT_DATA_DIR` can specify a different writable local directory. Do not put that directory under version control.

## Vercel preview

Import the GitHub repository into Vercel and set **Root Directory** to `receipt-app`. Use Flask detection with `app.py` as the entrypoint and `requirements.txt` for dependencies. No custom build command is required. Assets are included under `public/assets/` for the Vercel CDN, while the local Flask server serves the same paths.

The Vercel environment starts with an empty temporary database under `/tmp/jolyn-tae`. It displays a preview notice and rejects write requests. Temporary files are not a durable financial database; a local path environment variable does not make them persistent across function instances or redeploys.

Before using real financial records online, add a persistent database, durable private file storage and authentication/access control. This change prepares a source-only preview, not a production financial deployment. Do not commit the SQLite database or Excel files as a workaround.

Official setup reference: [Flask on Vercel](https://vercel.com/docs/frameworks/backend/flask).
