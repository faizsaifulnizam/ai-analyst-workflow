# Frozen historical HDB source

`hdb-2026-10-04.csv.gz` preserves the exact 23,928,760-byte CSV used by the historical receipt: 241,920 rows, SHA-256 `9835dfe6cd92a46a1302fabf3a692bf893ee5b86ec95638d10dfce61dbfbdb9a`. Archive uses gzip mtime 0 for deterministic packaging; this is not an acquisition timestamp.

Source: Housing & Development Board, via [data.gov.sg](https://data.gov.sg/datasets/d_8b84c4ee58e3cfc0ece0d773c8ca6abc/view). Data licence: [Singapore Open Data Licence](https://data.gov.sg/open-data-licence). Independent, unofficial analysis; attribution retained. Original pull receipt remains `data/raw/pull_manifest.json`: 2026-10-04 16:28:47 +08:00. October is partial. No raw bytes or historical manifest were rewritten.

Run `python src/restore_snapshot.py` for offline historical replay. `src/download.py --force` remains a live refresh, not permission to adopt new evaluation data or update golden scores. Restoring the CSV does not overwrite a live pull manifest; retain the historical committed manifest when rendering the historical receipt.
