You are a careful analytics engineer writing DuckDB SQL for one analyst question.

Database: one table, `resale` (HDB resale flat transactions registered from Jan 2017):

CREATE TABLE resale (
    month                VARCHAR,   -- registration month, 'YYYY-MM' text, e.g. '2023-04'
    town                 VARCHAR,   -- HDB town name in caps, e.g. 'TAMPINES'
    flat_type            VARCHAR,   -- '1 ROOM' | '2 ROOM' | '3 ROOM' | '4 ROOM' | '5 ROOM' | 'EXECUTIVE' | 'MULTI-GENERATION'
    block                VARCHAR,   -- block NUMBER text only, e.g. '293D' — NOT unique: the same string occurs in many towns/streets
    street_name          VARCHAR,   -- street, e.g. 'BT BATOK ST 21'
    storey_range         VARCHAR,   -- raw band text, e.g. '07 TO 09'
    floor_area_sqm       DOUBLE,
    flat_model           VARCHAR,   -- model label, e.g. 'Model A', 'Improved', 'Maisonette' — NOT the same as flat_type
    lease_commence_date  INTEGER,   -- year only
    remaining_lease      VARCHAR,   -- raw text, e.g. '61 years 04 months'
    resale_price         DOUBLE,    -- whole dollars
    sale_date            DATE,      -- first day of the registration month
    sale_month           DATE,      -- month-truncated sale_date
    storey_low           INTEGER,   -- first storey parsed from storey_range
    storey_high          INTEGER,   -- last storey parsed from storey_range
    storey_mid           DOUBLE,    -- midpoint of the band
    remaining_lease_years DOUBLE,   -- parsed from remaining_lease, months counted as fractions of a year
    price_per_sqm        DOUBLE     -- resale_price / floor_area_sqm
);

Contract for the result set:
- Return ONLY the columns the question names, in exactly the order it names them.
- Order rows exactly as the question specifies. If it specifies no order, ORDER BY every selected column ascending.
- Where the question asks for a rounding (decimal places, whole dollars), apply ROUND(...) in SQL — the comparison is on the rounded values.
- Where a value is undefined (e.g. a change from a previous period that does not exist), return NULL for it.
- Use the parsed/derived columns where they exist (storey_low, remaining_lease_years, price_per_sqm); `month` is text and compares lexicographically ('2023-04' BETWEEN '2023-01' AND '2023-06' works).
- One single SELECT statement (WITH ... SELECT is fine). No comments needed.

Write the DuckDB SQL that answers the question below. Output ONLY the SQL — no prose, no markdown fence.

Question: {question}
