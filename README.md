# istanbul-earthquake-scenario
Data-driven earthquake scenario analysis and casualty prediction for Istanbul districts using Machine Learning and geospatial mapping.

# Istanbul Earthquake Scenario Analysis with Machine Learning

## Overview

This project provides a comprehensive earthquake scenario analysis for Istanbul using data analytics, machine learning (ML), and geospatial visualization techniques. It aims to predict casualties and damage outcomes by district based on earthquake scenarios.

## Project Contents

- **Jupyter Notebook (`earthq.ipynb`)**: 
  - Data import and cleaning
  - Data alignment (handling Turkish character issues)
  - Data visualization (bar charts)
  - Interactive Folium choropleth map
  - Machine Learning model (Linear Regression) for predicting casualties

- **Data Files**:
  - `deprem-senaryosu-analiz-sonuclar.csv`: Raw scenario data.
  - `ilce_geojson.json`: GeoJSON boundaries for Istanbul districts.

## Installation & Requirements

Install required Python packages:

```bash
pip install pandas matplotlib folium requests scikit-learn
```

Ensure that the data files (`.csv` and `.json`) are in the same directory as the notebook.

## Usage

Open and run the notebook (`earthq.ipynb`) in Jupyter Notebook or JupyterLab to reproduce analysis steps, visualizations, and ML predictions.

## Results & Visualization

- Bar charts showing total casualties and damaged buildings by district.
- Interactive Folium choropleth map visualizing damage distribution across Istanbul.
- Linear Regression model for predicting casualties from damaged buildings, evaluated using Mean Squared Error and R².

## Potential Enhancements

- Incorporate additional features (e.g., building types, population density).
- Automate data pipeline for continuous updates.
- Develop dashboards with interactive tools (Plotly Dash, Streamlit).

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

Feel free to explore, use, or extend this project!
