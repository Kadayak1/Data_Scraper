# Property Data Scraper

This project scrapes property data from boligsiden.dk, focusing on auction properties in the Copenhagen area. It extracts detailed information including prices, property characteristics, and additional BBR details.

## Requirements

- Python 3.8+
- Git

## Installation

1. Clone the repository:
```bash
git clone <your-repository-url>
cd <repository-name>
```

2. Create and activate a virtual environment:
```bash
python -m venv .venv
.venv\Scripts\activate  # On Windows
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Install Playwright browsers:
```bash
playwright install
```

## Usage

1. First, run the initial data scraper to collect property listings:
```bash
python data_scrape.py
```
This will create a `scraped_properties.csv` file with basic property information.

2. Then, run the detailed property scraper:
```bash
python site_processer.py
```
This will create a `property_details.csv` file with detailed information about each property.

## Output

The scraper generates two main CSV files:
- `scraped_properties.csv`: Contains basic property information from the listing pages
- `property_details.csv`: Contains detailed property information including BBR data

Additionally, for debugging purposes, the scraper saves:
- Screenshots in the `debug_screenshots` directory
- HTML content in the `debug_html` directory

## Notes

- The scraper includes random delays between requests to avoid overwhelming the server
- All scraped data is saved with unique IDs for tracking
- The script handles dynamic content by waiting for JavaScript execution