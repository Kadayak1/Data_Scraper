import requests
from bs4 import BeautifulSoup
import pandas as pd
from multiprocessing import Pool, cpu_count
import time
import logging
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import re

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Set the headers with the User-Agent
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/85.0.4183.121 Safari/537.36'
}

# Load the list of property links from the CSV file
df = pd.read_csv('scraped_properties.csv')
links = df['Link'].unique()
unique_ids = df.set_index('Link')['ID'].to_dict()  # Keep track of unique IDs
property_types = df.set_index('Link')['Property Type'].to_dict()  # Map links to property types

root_url = 'https://www.boligsiden.dk'

# Define session with retry strategy
session = requests.Session()
retry_strategy = Retry(
    total=3,
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=["HEAD", "GET", "OPTIONS"],
    backoff_factor=1
)
adapter = HTTPAdapter(max_retries=retry_strategy)
session.mount("https://", adapter)
session.mount("http://", adapter)

def extract_building_year(soup):
    """Extract the building year from a BeautifulSoup object."""
    
    # Enhance pattern to capture building year from sentences with surrounding context
    year_patterns = [
        r'byggeår(?:et)?[^0-9]*(\d{4})',  # Matches phrases with "byggeår" followed closely by a four-digit year
        r'opført[^0-9]*(\d{4})',          # Matches phrases like "opført i" with nearby digits
    ]

    # Search within the entire text content
    all_texts = soup.find_all(text=True)
    for text in all_texts:
        text = text.strip()
        for pattern in year_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1)  # Return the first matched year

    return "N/A"

def fetch_property_data(relative_link):
    full_url = root_url + relative_link
    unique_id = unique_ids.get(relative_link, "Unknown ID")
    property_type = property_types.get(relative_link, "N/A")
    logging.info(f"Processing {unique_id}: {full_url}")

    try:
        response = session.get(full_url, headers=headers, timeout=10)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html.parser')

        # Address extraction
        address_el = soup.find('h1')
        address = address_el.get_text(strip=True).replace('\n', ', ') if address_el else "N/A"

        # Living area extraction
        living_area_el = soup.find(lambda tag: tag.name == "span" and "m²" in tag.text)
        living_area = living_area_el.get_text(strip=True) if living_area_el else "N/A"

        # Rooms extraction
        rooms_el = soup.find(lambda tag: tag.name == "span" and "værelser" in tag.text)
        rooms = rooms_el.get_text(strip=True) if rooms_el else "N/A"

        # Restrooms extraction
        restrooms_el = soup.find(lambda tag: tag.name == "span" and "toilet" in tag.text)
        restrooms = restrooms_el.get_text(strip=True) if restrooms_el else "N/A"

        # Sale price extraction
        sale_price = "N/A"
        for div in soup.find_all('div', class_='text-gray-600'):
            if 'Seneste salgspris' in div.get_text():
                sale_price_text = div.get_text()
                sale_price = ' '.join([s for s in sale_price_text.split() if 'kr' in s or s.replace('.', '').isdigit()])
                break

        # Extract building year from parsed text
        building_year = extract_building_year(soup)

        # Delay to avoid overloading server
        time.sleep(1)

        return {
            'ID': unique_id,
            'Link': full_url,
            'Address': address,
            'Living Area': living_area,
            'Rooms': rooms,
            'Restrooms': restrooms,
            'Sale Price': sale_price,
            'Building Year': building_year
        }

    except requests.exceptions.RequestException as e:
        logging.error(f"Error processing {unique_id}: {e}")
        return None

# Use a pool of processes to fetch data from URLs
if __name__ == '__main__':
    with Pool(cpu_count()) as pool:
        results = pool.map(fetch_property_data, links)

    # Filter out unsuccessful attempts and missing data
    property_data = [result for result in results if result is not None]

    # Convert the data to a DataFrame for further analysis
    properties_df = pd.DataFrame(property_data)
    properties_df.to_csv('property_details.csv', index=False)
    logging.info("Property details have been saved to 'property_details.csv'.")