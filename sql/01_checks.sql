-- 01_checks.sql — validation queries for the built `resale` table.
-- Each row: one check. src/build_db.py runs this and asserts all violations = 0
-- BEFORE the database file is promoted.

SELECT 'price > 0'              AS check_name, count(*) AS violations FROM resale WHERE resale_price <= 0
UNION ALL SELECT 'area > 0',               count(*) FROM resale WHERE floor_area_sqm <= 0
UNION ALL SELECT 'sale_month in range',    count(*) FROM resale WHERE sale_month < DATE '2017-01-01' OR sale_month > CURRENT_DATE
UNION ALL SELECT 'month text matches date',count(*) FROM resale WHERE month != strftime(sale_month, '%Y-%m')
UNION ALL SELECT 'town not null',          count(*) FROM resale WHERE town IS NULL OR town = ''
UNION ALL SELECT 'flat_type not null',     count(*) FROM resale WHERE flat_type IS NULL OR flat_type = ''
UNION ALL SELECT 'price/m2 sane',          count(*) FROM resale WHERE price_per_sqm IS NULL OR price_per_sqm <= 0
UNION ALL SELECT 'storey band sane',       count(*) FROM resale WHERE storey_low IS NULL OR storey_high IS NULL OR storey_low < 1 OR storey_high < storey_low
UNION ALL SELECT 'lease years sane',       count(*) FROM resale WHERE remaining_lease_years IS NULL OR remaining_lease_years < 0 OR remaining_lease_years > 99;
