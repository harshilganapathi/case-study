# Setup and replacement exports

Requires Python 3.11 or newer with `venv` and `pip`.

## macOS/Linux

From the project directory, run `./run.sh` and open http://localhost:8501. The launcher creates `.venv` and installs pinned requirements on first use. Initial installation needs access to PyPI; later launches reuse the environment. The launcher was checked on macOS.

## Windows

These PowerShell instructions are provided but have not been validated on Windows:

```powershell
py -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python -m streamlit run app.py
```

## Source selection

The supplied `Case_Study_Dataset.csv` loads automatically. Upload a replacement in the sidebar, or select a file at launch on macOS/Linux:

```sh
PARTS_DATA_PATH=/absolute/path/to/export.csv ./run.sh
```

Replacement files must use the exact 25-column header/order and unpadded Type labels (`Inventory`, `Invoiced`, `Scrapped`). Dates accept M/D/YYYY or YYYY-MM-DD. Unexpected structures are rejected or quarantined. The narrow split recovery rule handles the observed export pattern; it does not infer arbitrary schemas.

The raw source is never edited. Source bytes and pipeline code determine the cleaning cache key. First load validates/cleans the export; later views reuse it. **Reload source and clear cache** forces a refresh. Restart the server after changing Python modules or installed dependencies.

The app uses no external API, account, or AI service at runtime. Non-UI calculations use the standard library; SQLite aggregates quantities and Decimal handles financial calculations. See the [implementation guide](../IMPLEMENTATION_PLAN.md).
