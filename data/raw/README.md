# data/raw — provenance

Raw files land here and are never edited or committed (gitignored). This repo re-downloads its own copy:

- **Dataset:** HDB Resale Flat Prices (registration date, Jan-2017 onwards) — data.gov.sg `d_8b84c4ee58e3cfc0ece0d773c8ca6abc` — https://data.gov.sg/datasets/d_8b84c4ee58e3cfc0ece0d773c8ca6abc/view
- **Licence:** Singapore Open Data Licence (© Housing & Development Board)
- **Note:** same series as `hdb-resale-mart`; each repo keeps its own copy — no cross-repo file dependencies.
- **Fetch:** `src/download.py` at build (initiate → poll → signed-URL flow; see the project's `tools/fetch-datasets.py`).
