import logging
import pandas as pd
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import os
import time
import random
import re

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
    
    # Find the container with all the details
    details_container = soup.find('div', class_='pb-5 px-6 text-sm')
    if details_container:
        # Find all detail rows
        detail_rows = details_container.find_all('div', class_='border-t border-gray-100 flex flex-row justify-between py-3')
        for row in detail_rows:
            # Get the label and value divs
            divs = row.find_all('div')
            if len(divs) >= 2:
                label = divs[0].get_text(strip=True).rstrip(':')  # Remove trailing colon if present
                value = divs[1].get_text(strip=True)
                
                # Update the corresponding detail if it exists in our dictionary
                if label in details:
                    details[label] = value
    
    return details

def parse_address(address_text):
    """Parse address into street, postal code, and city."""
    address_parts = {
        'Street': "N/A",
        'Postal_Code': "N/A",
        'City': "N/A"
    }
    
    if address_text and address_text != "N/A":
        # Try to find postal code (4 digits) and use it as a separator
        postal_match = re.search(r'(\d{4})\s+([^\d]+)$', address_text)
        if postal_match:
            postal_code = postal_match.group(1)
            city = postal_match.group(2).strip()
            street = address_text[:postal_match.start()].strip()
            
            address_parts['Street'] = street
            address_parts['Postal_Code'] = postal_code
            address_parts['City'] = city
    
    return address_parts

def format_value_for_ml(value, value_type='string'):
    """Format values for machine learning."""
    if value == "N/A" or value == "Ikke oplyst":
        return None
    
    if value_type == 'number':
        # Extract numbers from strings like "110 m² (2025)" or "5 værelser"
        match = re.search(r'(\d+(?:\.\d+)?)', value)
        if match:
            return float(match.group(1))
        return None
    
    if value_type == 'price':
        # Extract price value from strings like "422.250 kr."
        match = re.search(r'([\d.]+)', value)
        if match:
            # Remove dots and convert to float
            return float(match.group(1).replace('.', ''))
        return None
    
    if value_type == 'year':
        # Extract year
        match = re.search(r'(\d{4})', value)
        if match:
            return int(match.group(1))
        return None
    
    # For string values, return as is
    return value

def fetch_property_data(page, relative_link, unique_id):
    full_url = 'https://www.boligsiden.dk' + relative_link
    property_data = {
        'ID': unique_id,
        'Link': full_url,
        'Street': "N/A",
        'Postal_Code': "N/A",
        'City': "N/A",
        'Living_Area_M2': None,
        'Num_Rooms': None,
        'Num_Toilets': None,
        'Sale_Price_DKK': None,
        'Construction_Year': None,
        'Built_Year': None,
        'Num_Floors': None,
        'Floor_Number': None,
        'Heating_Type': "N/A",
        'Wall_Material': "N/A",
        'Weighted_Area': None,
        'Roof_Type': "N/A"
    }
    
    logging.info(f"Processing {unique_id}: {full_url}")

    try:
        # Navigate to the page with a longer timeout
        page.goto(full_url, wait_until='domcontentloaded', timeout=60000)
        
        # Wait for any dynamic content to load
        try:
            page.wait_for_load_state('networkidle', timeout=30000)
        except Exception as e:
            logging.warning(f"Network idle timeout for {unique_id}, proceeding anyway: {e}")
        
        # Add random delay to avoid rate limiting
        time.sleep(random.uniform(2, 4))
        
        # Try to click the expand button if it exists, with a shorter timeout
        try:
            expand_button = page.locator("button:has-text('Se flere detaljer fra BBR')").first
            if expand_button:
                expand_button.click(timeout=10000)
                time.sleep(1)  # Wait for the content to expand
        except Exception as e:
            logging.warning(f"Expand button interaction failed for {unique_id}: {e}")
        
        # Save screenshot and HTML for debugging
        os.makedirs('debug_screenshots', exist_ok=True)
        os.makedirs('debug_html', exist_ok=True)
        page.screenshot(path=f'debug_screenshots/property_{unique_id}.png')
        
        with open(f'debug_html/property_{unique_id}.html', 'w', encoding='utf-8') as f:
            f.write(page.content())
        
        # Get the page content directly without waiting for specific elements
        html_content = page.content()
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Extract and parse address
        address_el = soup.find('h1')
        if address_el is not None:
            address_text = address_el.get_text(strip=True).replace('\n', ' ')
            address_parts = parse_address(address_text)
            property_data.update(address_parts)
        else:
            logging.warning(f"Address not found for {unique_id}")
        
        # Extract living area
        living_area_el = soup.find(lambda tag: tag.name == "span" and "m²" in tag.text)
        if living_area_el is not None:
            property_data['Living_Area_M2'] = format_value_for_ml(living_area_el.get_text(strip=True), 'number')
        else:
            logging.warning(f"Living area not found for {unique_id}")
        
        # Extract rooms
        rooms_el = soup.find(lambda tag: tag.name == "span" and "værelser" in tag.text)
        if rooms_el is not None:
            property_data['Num_Rooms'] = format_value_for_ml(rooms_el.get_text(strip=True), 'number')
        else:
            logging.warning(f"Rooms not found for {unique_id}")
        
        # Extract sale price
        for div in soup.find_all('div', class_='text-gray-600'):
            if 'Seneste salgspris' in div.get_text():
                sale_price_text = div.get_text()
                property_data['Sale_Price_DKK'] = format_value_for_ml(sale_price_text, 'price')
                break
        
        # Extract built year from the pris_og_udvikling section
        pris_section = soup.find('div', id='pris_og_udvikling')
        if pris_section:
            # Look for the built year information
            built_year_div = pris_section.find(lambda tag: tag.name == 'div' and 
                                             tag.find('p', string='Bygget') and 
                                             tag.get('class') and 
                                             'hidden' in tag.get('class'))
            if built_year_div:
                year_text = built_year_div.find('p', class_='text-sm text-gray-800')
                if year_text:
                    property_data['Built_Year'] = format_value_for_ml(year_text.get_text(strip=True), 'year')
        
        # Extract additional property details
        details = extract_property_details(soup)
        
        # Map the extracted details to our formatted structure
        if details['Seneste ombygningsår'] != "Ikke oplyst":
            property_data['Construction_Year'] = format_value_for_ml(details['Seneste ombygningsår'], 'year')
        
        if details['Antal plan og etage'] != "Ikke oplyst":
            # Parse floor information (e.g., "5 plan - 3" -> floors=5, floor_number=3)
            # Also handle cases like "1 plan - " where floor number is missing
            floor_info = details['Antal plan og etage']
            floor_match = re.search(r'(\d+)\s*plan\s*-\s*(\d+)?', floor_info)
            if floor_match:
                property_data['Num_Floors'] = int(floor_match.group(1))
                if floor_match.group(2):  # Only set floor number if it exists
                    property_data['Floor_Number'] = int(floor_match.group(2))
        
        if details['Antal toiletter'] != "Ikke oplyst":
            property_data['Num_Toilets'] = format_value_for_ml(details['Antal toiletter'], 'number')
        
        property_data['Heating_Type'] = details['Varmeinstallation']
        property_data['Wall_Material'] = details['Ydervægge']
        property_data['Roof_Type'] = details['Tagtype']
        
        if details['Vægtet areal'] != "Ikke oplyst":
            # Extract just the number from "143.15 m²"
            weighted_area_match = re.search(r'([\d.]+)', details['Vægtet areal'])
            if weighted_area_match:
                property_data['Weighted_Area'] = float(weighted_area_match.group(1))
        
    except Exception as e:
        logging.error(f"Error processing {unique_id}: {e}")
    
    return property_data

def main(sample_size=None):
    # Load list of property links from CSV
    df = pd.read_csv('scraped_properties.csv')
    links = df['Link'].unique()
    
    # Take a random sample if sample_size is specified
    if sample_size and sample_size < len(links):
        logging.info(f"Taking a random sample of {sample_size} links from {len(links)} total links")
        links = pd.Series(links).sample(n=sample_size, random_state=42).tolist()
    
    unique_ids = df.set_index('Link')['ID'].to_dict()
    
    browser, playwright = setup_browser()
    context = browser.new_context()
    page = context.new_page()
    all_property_data = []
    
    start_time = time.time()
    
    try:
        for i, link in enumerate(links):
            unique_id = unique_ids.get(link, "Unknown ID")
            max_retries = 3
            retry_count = 0
            
            while retry_count < max_retries:
                try:
                    property_data = fetch_property_data(page, link, unique_id)
                    all_property_data.append(property_data)
                    
                    # Add a longer delay every 10 requests
                    if i > 0 and i % 10 == 0:
                        elapsed_time = time.time() - start_time
                        avg_time_per_item = elapsed_time / (i + 1)
                        remaining_items = len(links) - (i + 1)
                        estimated_remaining_time = remaining_items * avg_time_per_item
                        
                        logging.info(f"Taking a longer break after {i} requests...")
                        logging.info(f"Average time per item: {avg_time_per_item:.2f} seconds")
                        logging.info(f"Estimated remaining time: {estimated_remaining_time/60:.2f} minutes")
                        time.sleep(random.uniform(10, 15))
                    else:
                        time.sleep(random.uniform(3, 5))
                    
                    break  # Success, exit retry loop
                    
                except Exception as e:
                    retry_count += 1
                    if retry_count < max_retries:
                        logging.warning(f"Attempt {retry_count} failed for {unique_id}, retrying in 10 seconds... Error: {e}")
                        time.sleep(10)
                    else:
                        logging.error(f"All retries failed for {unique_id}: {e}")
            
            # Save progress every 20 items
            if i > 0 and i % 20 == 0:
                temp_df = pd.DataFrame(all_property_data)
                temp_df.to_csv(f'property_details_partial_{i}.csv', index=False, encoding='utf-8-sig')
                logging.info(f"Saved partial progress after processing {i} items")
    
    except KeyboardInterrupt:
        logging.info("Received keyboard interrupt, saving current progress...")
        if all_property_data:
            pd.DataFrame(all_property_data).to_csv('property_details_interrupted.csv', index=False, encoding='utf-8-sig')
        raise
    
    finally:
        try:
            context.close()
            browser.close()
            playwright.stop()
        except Exception as e:
            logging.error(f"Error during cleanup: {e}")
    
    # Save final results
    if all_property_data:
        properties_df = pd.DataFrame(all_property_data)
        output_file = 'property_details_sample.csv' if sample_size else 'property_details.csv'
        properties_df.to_csv(output_file, index=False, encoding='utf-8-sig')
        logging.info(f"Property details have been saved to '{output_file}'")

def get_user_choice():
    while True:
        print("\nPlease select a run mode:")
        print("1. Small sample (5 properties, ~3 minutes)")
        print("2. Medium sample (50 properties, ~20 minutes)")
        print("3. Full dataset (552 properties, ~3.5 hours)")
        choice = input("Enter your choice (1-3): ").strip()
        
        if choice == "1":
            return 5
        elif choice == "2":
            return 50
        elif choice == "3":
            return None
        else:
            print("Invalid choice. Please enter 1, 2, or 3.")

if __name__ == '__main__':
    try:
        sample_size = get_user_choice()
        if sample_size is None:
            print("\nStarting full dataset run (552 properties)...")
            print("Estimated time: 3.5 hours")
        else:
            print(f"\nStarting sample run with {sample_size} properties...")
        
        main(sample_size=sample_size)
    except KeyboardInterrupt:
        print("\nProcess interrupted by user. Check property_details_interrupted.csv for partial results.")
    except Exception as e:
        print(f"\nAn error occurred: {e}")
        raise