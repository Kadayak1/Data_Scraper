import logging
import pandas as pd
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import os
import time
import random

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def setup_browser():
    playwright = sync_playwright().start()
    browser = playwright.chromium.launch(headless=True)
    return browser, playwright

def extract_property_details(soup):
    details = {
        'Seneste ombygningsår': "Ikke oplyst",
        'Antal plan og etage': "Ikke oplyst",
        'Antal toiletter': "Ikke oplyst",
        'Varmeinstallation': "Ikke oplyst",
        'Ydervægge': "Ikke oplyst",
        'Vægtet areal': "Ikke oplyst",
        'Tagtype': "Ikke oplyst"
    }
    
    divs = soup.find_all("div", class_="border-t border-gray-100 flex flex-row justify-between py-3")
    for div in divs:
        children_divs = div.find_all("div")
        if len(children_divs) >= 2:
            label = children_divs[0].get_text(strip=True)
            value = children_divs[1].get_text(strip=True)
            if label in details:
                details[label] = value
    
    return details

def fetch_property_data(page, relative_link, unique_id):
    full_url = 'https://www.boligsiden.dk' + relative_link
    property_data = {
        'ID': unique_id,
        'Link': full_url,
        'Address': "N/A",
        'Living Area': "N/A",
        'Rooms': "N/A",
        'Restrooms': "N/A",
        'Sale Price': "N/A",
        'Property Type': "N/A",
        'Seneste ombygningsår': "Ikke oplyst",
        'Antal plan og etage': "Ikke oplyst",
        'Antal toiletter': "Ikke oplyst",
        'Varmeinstallation': "Ikke oplyst",
        'Ydervægge': "Ikke oplyst",
        'Vægtet areal': "Ikke oplyst",
        'Tagtype': "Ikke oplyst"
    }
    
    logging.info(f"Processing {unique_id}: {full_url}")

    try:
        # Navigate to the page
        page.goto(full_url, wait_until='networkidle')
        
        # Add random delay to avoid rate limiting
        time.sleep(random.uniform(2, 4))
        
        # Try to click the expand button if it exists
        try:
            expand_button = page.locator("button:has-text('Se flere detaljer fra BBR')").first
            if expand_button:
                expand_button.click()
                page.wait_for_load_state('networkidle')
                time.sleep(1)  # Wait for the content to expand
        except Exception as e:
            logging.warning(f"Expand button may not be present: {e}")
        
        # Wait for content to load
        page.wait_for_selector('div.text-gray-600', timeout=10000)
        
        # Save screenshot and HTML for debugging
        os.makedirs('debug_screenshots', exist_ok=True)
        os.makedirs('debug_html', exist_ok=True)
        page.screenshot(path=f'debug_screenshots/property_{unique_id}.png')
        
        with open(f'debug_html/property_{unique_id}.html', 'w', encoding='utf-8') as f:
            f.write(page.content())
        
        soup = BeautifulSoup(page.content(), 'html.parser')
        
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
        
        # Extract property type
        property_type_el = soup.find('div', class_='text-gray-600')
        if property_type_el:
            property_data['Property Type'] = property_type_el.text.strip()
        
        # Extract additional property details
        details = extract_property_details(soup)
        property_data.update(details)
        
    except Exception as e:
        logging.error(f"Error processing {unique_id}: {e}")
    
    return property_data

def main():
    # Load list of property links from CSV
    df = pd.read_csv('scraped_properties.csv')
    links = df['Link'].unique()
    unique_ids = df.set_index('Link')['ID'].to_dict()
    
    browser, playwright = setup_browser()
    context = browser.new_context()
    page = context.new_page()
    all_property_data = []
    
    try:
        for link in links:
            unique_id = unique_ids.get(link, "Unknown ID")
            property_data = fetch_property_data(page, link, unique_id)
            all_property_data.append(property_data)
            
            # Add a small delay between requests
            time.sleep(random.uniform(1, 3))
    
    finally:
        context.close()
        browser.close()
        playwright.stop()
    
    properties_df = pd.DataFrame(all_property_data)
    properties_df.to_csv('property_details.csv', index=False)
    logging.info("Property details have been saved to 'property_details.csv'")

if __name__ == '__main__':
    main()