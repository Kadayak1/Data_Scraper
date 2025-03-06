import logging
import pandas as pd
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Function to setup WebDriver
def setup_webdriver():
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    return webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()), options=options)

# Load list of property links from CSV
df = pd.read_csv('scraped_properties.csv')
links = df['Link'].unique()
unique_ids = df.set_index('Link')['ID'].to_dict()
property_types = df.set_index('Link')['Property Type'].to_dict()

root_url = 'https://www.boligsiden.dk'

def extract_latest_renovation_year(soup):
    divs = soup.find_all("div", class_="border-t border-gray-100 flex flex-row justify-between py-3")
    for div in divs:
        children_divs = div.find_all("div")
        if len(children_divs) >= 2:
            label = children_divs[0].get_text(strip=True)
            value = children_divs[1].get_text(strip=True)
            if "Seneste ombygningsår" in label:
                return value if value.isdigit() else "Ikke oplyst"
    return "Ikke oplyst"

def fetch_property_data(driver, relative_link):
    full_url = root_url + relative_link
    unique_id = unique_ids.get(relative_link, "Unknown ID")
    property_data = {
        'ID': unique_id,
        'Link': full_url,
        'Address': "N/A",
        'Living Area': "N/A",
        'Rooms': "N/A",
        'Restrooms': "N/A",
        'Sale Price': "N/A",
        'Building Year': "Ikke oplyst"
    }
    
    logging.info(f"Processing {unique_id}: {full_url}")

    try:
        driver.get(full_url)

        try:
            WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "svg.transition.duration-500"))
            ).click()
        except Exception as e:
            logging.warning(f"Expand button may not be present: {e}")

        WebDriverWait(driver, 10).until(
            EC.presence_of_all_elements_located((By.CSS_SELECTOR, 'div.text-gray-600'))
        )

        soup = BeautifulSoup(driver.page_source, 'html.parser')

        # Extract address
        address_el = soup.find('h1')
        if address_el is not None:
            property_data['Address'] = address_el.get_text(strip=True).replace('\n', ', ')
        else:
            logging.warning(f"Address not found for {unique_id}")

        # Extract living area
        living_area_el = soup.find(lambda tag: tag.name == "span" and "m²" in tag.text)
        if living_area_el is not None:
            property_data['Living Area'] = living_area_el.get_text(strip=True)
        else:
            logging.warning(f"Living area not found for {unique_id}")

        # Extract rooms
        rooms_el = soup.find(lambda tag: tag.name == "span" and "værelser" in tag.text)
        if rooms_el is not None:
            property_data['Rooms'] = rooms_el.get_text(strip=True)
        else:
            logging.warning(f"Rooms not found for {unique_id}")

        # Extract restrooms
        restrooms_el = soup.find(lambda tag: tag.name == "span" and "toilet" in tag.text)
        if restrooms_el is not None:
            property_data['Restrooms'] = restrooms_el.get_text(strip=True)
        else:
            logging.warning(f"Restrooms not found for {unique_id}")

        # Extract sale price
        for div in soup.find_all('div', class_='text-gray-600'):
            if 'Seneste salgspris' in div.get_text():
                sale_price_text = div.get_text()
                property_data['Sale Price'] = ' '.join(
                    [s for s in sale_price_text.split() if 'kr' in s or s.replace('.', '').isdigit()])
                break

        # Extract building year
        property_data['Building Year'] = extract_latest_renovation_year(soup)

    except Exception as e:
        logging.error(f"Error processing {unique_id}: {e}")

    return property_data

# Main execution block
if __name__ == '__main__':
    driver = setup_webdriver()
    all_property_data = []

    try:
        for link in links:
            property_data = fetch_property_data(driver, link)
            all_property_data.append(property_data)
    
    finally:
        driver.quit()

    properties_df = pd.DataFrame(all_property_data)
    properties_df.to_csv('property_details.csv', index=False)
    logging.info("Property details have been saved to 'property_details.csv'.")