# CHECK case deviations

18 of 21 CHECK cases agree with the workbook. Failing case ids: [6, 7, 10].

| Case | Reference | Lang | Change | Workbook expects | Computed | Deviation |
|---|---|---|---|---|---|---|
| 6 | Matthew 28:19 | en | Curly apostrophe and quotes | Partial. Curly apostrophe normalises to straight, but Father’s is still 1 word wrong at position 16. | partial — 23 of 24 words matched, wrong at [15] | wrong position: workbook 16, computed [15] |
| 7 | Matthew 28:19 | en | Empty string | Incorrect. 0 of 22 words matched. | incorrect — 0 of 24 words matched, 24 missing from 1 | total: workbook 22, computed 24 |
| 10 | John 3:16 | zh | Traditional characters instead of simplified | Incorrect. Script conversion is not performed. Every differing character counts. | partial — 23 of 30 chars matched, wrong at [2, 7, 10, 13, 14, 16, 25] | status: workbook says incorrect, computed partial |
