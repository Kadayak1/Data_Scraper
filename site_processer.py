import requests
from bs4 import BeautifulSoup
import pandas as pd
from multiprocessing import Pool, cpu_count

# Set the headers with the User-Agent
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/85.0.4183.121 Safari/537.36'
}

# Load the list of property links from the CSV file
df = pd.read_csv('scraped_properties.csv')
links = df['Link'].unique()
unique_ids = df.set_index('Link')['ID'].to_dict()  # Keep track of unique IDs

root_url = 'https://www.boligsiden.dk'

def fetch_property_data(relative_link):
    full_url = root_url + relative_link
    unique_id = unique_ids.get(relative_link, "Unknown ID")
    print(f"Processing {unique_id}: {full_url}")

    try:
        # Now the headers with the user-agent are consistently applied
        response = requests.get(full_url, headers=headers, timeout=10)
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
        restrooms_el = soup.find(lambda tag: tag.name == "span" and "toiletter" in tag.text)
        restrooms = restrooms_el.get_text(strip=True) if restrooms_el else "N/A"

        # Sale price extraction
        sale_price = "N/A"
        for div in soup.find_all('div', class_='text-gray-600'):
            if 'Seneste salgspris' in div.get_text():
                sale_price_text = div.get_text()
                # Extract only number and currency part
                sale_price = ' '.join([s for s in sale_price_text.split() if 'kr' in s or s.replace('.', '').isdigit()])
                break  # Assuming there's only one relevant div

        return {
            'ID': unique_id,
            'Link': full_url,
            'Address': address,
            'Living Area': living_area,
            'Rooms': rooms,
            'Restrooms': restrooms,
            'Sale Price': sale_price
        }

    except requests.exceptions.RequestException as e:
        print(f"Error processing {unique_id}: {e}")
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
    print("Property details have been saved to 'property_details.csv'.")