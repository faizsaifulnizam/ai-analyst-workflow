-- 00_build_db.sql — raw CSV -> cleaned DuckDB table `resale`.
-- Reads:  data/raw/hdb-resale-prices-2017-onwards.csv (never modified)
-- Writes: table `resale` (src/build_db.py handles the file replacement).
--
-- Cleaning mirrors hdb-resale-mart's staging rules (spec 07 §3): bad/empty numeric
-- fields and unparseable months are EXCLUDED, never coerced to zero; every exclusion
-- rule below is mirrored in src/build_db.py and counted there (retained + excluded
-- must reconcile to the raw row count).
--
-- Schema policy: raw columns keep their source names (month text, storey_range text,
-- remaining_lease text) AND derived analyst columns are added (sale_month, storey_*,
-- remaining_lease_years, price_per_sqm). The near-miss pairs are deliberate — the
-- golden set tests whether a reader picks the right one.

CREATE OR REPLACE TABLE resale AS
SELECT
    month,                                                     -- raw 'YYYY-MM' text
    town,
    flat_type,
    block,
    street_name,
    storey_range,                                              -- raw text, e.g. '07 TO 09'
    floor_area_sqm,
    flat_model,
    lease_commence_date,
    remaining_lease,                                           -- raw text, e.g. '61 years 04 months'
    resale_price,
    CAST(TRY_STRPTIME(month, '%Y-%m') AS DATE)                  AS sale_date,
    date_trunc('month', CAST(TRY_STRPTIME(month, '%Y-%m') AS DATE)) AS sale_month,
    TRY_CAST(regexp_extract(storey_range, '^([0-9]+)', 1) AS INTEGER)    AS storey_low,
    TRY_CAST(regexp_extract(storey_range, 'TO ([0-9]+)$', 1) AS INTEGER) AS storey_high,
    (TRY_CAST(regexp_extract(storey_range, '^([0-9]+)', 1) AS INTEGER)
     + TRY_CAST(regexp_extract(storey_range, 'TO ([0-9]+)$', 1) AS INTEGER)) / 2.0 AS storey_mid,
    (TRY_CAST(regexp_extract(remaining_lease, '^([0-9]+) year', 1) AS INTEGER)
     + COALESCE(TRY_CAST(regexp_extract(remaining_lease, '([0-9]+) month', 1) AS INTEGER), 0) / 12.0) AS remaining_lease_years,
    resale_price / NULLIF(floor_area_sqm, 0)                   AS price_per_sqm
FROM read_csv_auto('data/raw/hdb-resale-prices-2017-onwards.csv')
WHERE resale_price IS NOT NULL
  AND resale_price > 0
  AND floor_area_sqm IS NOT NULL
  AND floor_area_sqm > 0
  AND TRY_STRPTIME(month, '%Y-%m') IS NOT NULL
  AND remaining_lease IS NOT NULL;
