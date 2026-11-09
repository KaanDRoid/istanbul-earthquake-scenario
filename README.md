# Istanbul Earthquake Scenario Analysis

A Jupyter notebook that works with the earthquake scenario results published by the Istanbul Metropolitan Municipality (İBB). It cleans the neighbourhood-level data, aggregates it per district, plots casualties and building damage, draws a choropleth map of Istanbul's districts, and fits a simple linear regression between damaged buildings and casualties.

## Data

- `deprem-senaryosu-analiz-sonuclar.csv`: scenario results from the İBB Open Data portal (data.ibb.gov.tr), 959 neighbourhood rows in 39 districts. Semicolon separated, Latin-1 encoded. Columns include building damage counts by severity (`cok_agir_`, `agir_`, `orta_`, `hafif_hasarli_bina_sayisi`), casualties and injuries (`can_kaybi_sayisi`, `agir_yarali_sayisi`, `hafif_yarali_sayisi`, ...), pipeline damage and temporary shelter needs.
- `ilce_geojson.json`: district boundaries of Istanbul used for the map.

The notebook can also pull the same dataset from the İBB CKAN API (`datastore_search`). This part needs an internet connection; the rest only uses the local files.

## What the notebook does

1. Reads the CSV and fixes the Turkish characters that come out wrong with Latin-1 decoding (`Ý` to `İ`, `Þ` to `Ş`, ...).
2. Maps a few district names so they match the GeoJSON (for example `EYÜP` to `EYÜPSULTAN`).
3. Sums the data per district and adds two columns:
   - `total_casualties` = deaths + serious injuries + light injuries
   - `total_damaged_buildings` = sum of all four damage levels
4. Bar charts of both totals by district.
5. Folium choropleth of `total_damaged_buildings`.
6. Linear regression of `total_casualties` on `total_damaged_buildings` with an 80/20 train/test split.

## Results

From the saved notebook output, the regression on the 8 test districts gives:

| Metric | Value |
| --- | --- |
| MSE | 6,104,971.83 |
| R² | 0.37 |

With only 39 district-level samples this is a rough indication that building damage explains part of the casualty numbers, not a predictive model.

## Running

```bash
pip install -r requirements.txt
jupyter notebook earthq.ipynb
```

Keep the CSV and GeoJSON files in the same folder as the notebook.

## Files

```
earthq.ipynb                            analysis notebook
deprem-senaryosu-analiz-sonuclar.csv    İBB earthquake scenario results
ilce_geojson.json                       Istanbul district boundaries
requirements.txt
LICENSE
```

## License

MIT, see [LICENSE](LICENSE).
