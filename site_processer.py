import logging
import pandas as pd
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import os
import time
import random
import re
import datetime

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
    if value == "N/A" or value == "Ikke oplyst" or not value:
        return None
    
    if value_type == 'number':
        # Extract numbers from strings like "110 m² (2025)" or "5 værelser" or "2 toiletter"
        match = re.search(r'(\d+(?:\.\d+)?)', value)
        if match:
            return float(match.group(1))
        return None
    
    if value_type == 'price':
        # Extract price value from strings like "4.250.000 kr." or "422.250 kr."
        # Remove all dots and "kr." to get the pure number
        if not value:
            return None
            
        # Remove everything after the first parenthesis if it exists
        value = value.split('(')[0].strip()
        
        # Remove dots and "kr." and any other non-numeric characters
        clean_value = re.sub(r'[^\d]', '', value)
        
        try:
            return float(clean_value)
        except ValueError:
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
        'Street': None,
        'Postal_Code': None,
        'City': None,
        'Living_Area_M2': None,
        'Num_Rooms': None,
        'Num_Toilets': None,
        'Sale_Price_DKK': None,
        'Construction_Year': None,
        'Built_Year': None,
        'Num_Floors': None,
        'Floor_Number': None,
        'Heating_Type': None,
        'Wall_Material': None,
        'Weighted_Area': None,
        'Roof_Type': None
    }
    
    logging.info(f"Processing {unique_id}: {full_url}")

    try:
        # Navigate to the page with a longer timeout
        page.goto(full_url, wait_until='domcontentloaded', timeout=60000)
        
        # Wait for the main content to load
        page.wait_for_selector('div[class*="flex flex-wrap gap-2"]', timeout=30000)
        
        # Add random delay to avoid rate limiting
        time.sleep(random.uniform(2, 4))
        
        # Extract main details from the flex container
        try:
            main_details = page.evaluate('''() => {
                const container = document.querySelector('div[class*="flex flex-wrap gap-2"]');
                if (!container) return null;
                
                const details = {};
                
                // Find living area
                const area_el = container.querySelector('span[class*="text-blue-900"]');
                if (area_el && area_el.textContent.includes('m²')) {
                    details.area = area_el.textContent.trim();
                }
                
                // Find number of rooms
                const rooms_el = Array.from(container.querySelectorAll('span[class*="text-blue-900"]'))
                    .find(el => el.textContent.includes('værelser'));
                if (rooms_el) {
                    details.rooms = rooms_el.textContent.trim();
                }
                
                // Find number of toilets
                const toilets_el = Array.from(container.querySelectorAll('span[class*="text-blue-900"]'))
                    .find(el => el.textContent.includes('toiletter'));
                if (toilets_el) {
                    details.toilets = toilets_el.textContent.trim();
                }
                
                // Try to find construction year in the main view
                const year_el = Array.from(container.querySelectorAll('span[class*="text-blue-900"]'))
                    .find(el => /\d{4}/.test(el.textContent));
                if (year_el) {
                    const year_match = year_el.textContent.match(/\d{4}/);
                    if (year_match) {
                        const year = parseInt(year_match[0]);
                        if (1800 <= year && year <= new Date().getFullYear()) {
                            details.year = year;
                        }
                    }
                }
                
                return details;
            }''')
            
            if main_details:
                if main_details.get('area'):
                    property_data['Living_Area_M2'] = format_value_for_ml(main_details['area'], 'number')
                if main_details.get('rooms'):
                    property_data['Num_Rooms'] = format_value_for_ml(main_details['rooms'], 'number')
                if main_details.get('toilets'):
                    property_data['Num_Toilets'] = format_value_for_ml(main_details['toilets'], 'number')
                if main_details.get('year'):
                    property_data['Construction_Year'] = main_details['year']
                    property_data['Built_Year'] = main_details['year']
        except Exception as e:
            logging.error(f"Error parsing main details for {unique_id}: {e}")
        
        # Extract sale price
        try:
            # Wait for the page to load
            page.wait_for_load_state('networkidle')
            
            # Get all price elements
            price_elements = page.query_selector_all('div[class*="text-blue-900"]')
            
            # Find the price element containing "kr."
            price = None
            for el in price_elements:
                text = el.text_content()
                if "kr." in text:
                    price = text
                    break
            
            if price:
                # Check if this is a shared property (same address but different units)
                is_shared_property = "mf" in relative_link.lower() or "tv" in relative_link.lower() or "th" in relative_link.lower()
                if is_shared_property:
                    # For shared properties, we need to find the specific unit price
                    unit_price = page.evaluate('''() => {
                        const price_el = document.querySelector('div[class*="text-blue-900"]:has-text("kr.")');
                        return price_el ? price_el.textContent.trim() : null;
                    }''')
                    if unit_price:
                        price = unit_price
                
                # Additional check for price in the property details
                if not price:
                    price = page.evaluate('''() => {
                        const price_el = document.querySelector('div[class*="text-blue-900"]:has-text("kr.")');
                        return price_el ? price_el.textContent.trim() : null;
                    }''')
                
                # Format the price
                formatted_price = format_value_for_ml(price, 'price')
                if formatted_price:
                    property_data['Sale_Price_DKK'] = formatted_price
                    logging.info(f"Found price for {unique_id}: {price}")
                else:
                    logging.warning(f"Could not format price for {unique_id}: {price}")
            else:
                logging.warning(f"Could not find price for {unique_id}")
        except Exception as e:
            logging.error(f"Error parsing sale price for {unique_id}: {e}")
        
        # Try to click the "Se flere detaljer" button and wait for the popup
        try:
            # Wait for the button to be visible and clickable
            details_button = page.wait_for_selector('button:has-text("Se flere detaljer")', timeout=10000)
            if details_button:
                details_button.click()
                # Wait for the popup to appear
                page.wait_for_selector('div[class*="bg-white space-y-4"]', timeout=10000)
                time.sleep(2)  # Give the popup time to fully load
                
                # Extract details from the popup
                popup_details = page.evaluate('''() => {
                    const popup = document.querySelector('div[class*="bg-white space-y-4"]');
                    if (!popup) return null;
                    
                    const details = {};
                    const rows = popup.querySelectorAll('div[class*="h-14 flex text-blue-900"]');
                    
                    rows.forEach(row => {
                        const label_div = row.querySelector('div:first-child');
                        const value_div = row.querySelector('div[class*="font-semibold"]');
                        
                        if (label_div && value_div) {
                            const label = label_div.textContent.trim();
                            const value = value_div.textContent.trim();
                            if (value && value !== "Ikke oplyst") {
                                details[label] = value;
                            }
                        }
                    });
                    
                    return details;
                }''')
                
                if popup_details:
                    for label, value in popup_details.items():
                        if 'Seneste ombygningsår' in label:
                            year_match = re.search(r'(\d{4})', value)
                            if year_match:
                                year = int(year_match.group(1))
                                if 1800 <= year <= 2100:
                                    property_data['Construction_Year'] = year
                                    property_data['Built_Year'] = year
                        
                        elif 'Antal plan og etage' in label:
                            floor_match = re.search(r'(\d+)\s*plan', value)
                            if floor_match:
                                property_data['Num_Floors'] = int(floor_match.group(1))
                                # Try to extract floor number
                                floor_num_match = re.search(r'etage\s*(\d+)', value)
                                if floor_num_match:
                                    property_data['Floor_Number'] = int(floor_num_match.group(1))
                                elif '-' not in value:
                                    # For shared properties, try to extract floor from the address
                                    if "mf" in relative_link.lower() or "tv" in relative_link.lower() or "th" in relative_link.lower():
                                        floor_match = re.search(r'(\d+)(?:st|th|mf)', relative_link.lower())
                                        if floor_match:
                                            property_data['Floor_Number'] = int(floor_match.group(1))
                                        else:
                                            # Try to extract floor from the address number
                                            floor_match = re.search(r'(\d+)(?:st|th|mf)', relative_link.lower())
                                            if floor_match:
                                                property_data['Floor_Number'] = int(floor_match.group(1))
                                            else:
                                                property_data['Floor_Number'] = 1
                                    else:
                                        property_data['Floor_Number'] = 1
                        
                        elif 'Antal toiletter' in label:
                            # Only update if we don't already have a value from the main view
                            if property_data['Num_Toilets'] is None:
                                property_data['Num_Toilets'] = format_value_for_ml(value, 'number')
                        
                        elif 'Varmeinstallation' in label:
                            property_data['Heating_Type'] = value if value != "Ikke oplyst" else None
                        
                        elif 'Ydervægge' in label:
                            property_data['Wall_Material'] = value if value != "Ikke oplyst" else None
                        
                        elif 'Vægtet areal' in label:
                            # Extract the numeric value from the weighted area
                            area_match = re.search(r'(\d+(?:\.\d+)?)\s*m²', value)
                            if area_match:
                                property_data['Weighted_Area'] = float(area_match.group(1))
                            else:
                                # If no weighted area, use living area as fallback
                                property_data['Weighted_Area'] = property_data['Living_Area_M2']
                        
                        elif 'Tagtype' in label:
                            property_data['Roof_Type'] = value if value != "Ikke oplyst" else None
                
                # Click the close button
                close_button = page.query_selector('button:has-text("Luk")')
                if close_button:
                    close_button.click()
                    time.sleep(1)
        except Exception as e:
            logging.warning(f"Could not process popup details for {unique_id}: {e}")
        
        # Extract address from schema.org data
        try:
            script_content = page.evaluate('''() => {
                const script = document.querySelector('script[type="application/ld+json"]');
                return script ? script.textContent : null;
            }''')
            
            if script_content:
                import json
                schema_data = json.loads(script_content)
                if isinstance(schema_data, list):
                    schema_data = schema_data[0]
                
                if 'Address' in schema_data:
                    address = schema_data['Address']
                    street = address.get('streetAddress', '').split(',')[0]
                    postal_code = address.get('postalCode')
                    city = address.get('addressLocality')
                    
                    property_data['Street'] = street if street else None
                    property_data['Postal_Code'] = postal_code if postal_code else None
                    property_data['City'] = city if city else None
        except Exception as e:
            logging.error(f"Error parsing schema data for {unique_id}: {e}")
        
    except Exception as e:
        logging.error(f"Error processing {unique_id}: {e}")
    
    # Ensure all empty strings are converted to None
    for key in property_data:
        if property_data[key] == "":
            property_data[key] = None
    
    # Set default values for missing data
    if property_data['Weighted_Area'] is None and property_data['Living_Area_M2'] is not None:
        property_data['Weighted_Area'] = property_data['Living_Area_M2']
    
    if property_data['Floor_Number'] is None and property_data['Num_Floors'] is not None:
        # For shared properties, try to extract floor from the address
        if "mf" in relative_link.lower() or "tv" in relative_link.lower() or "th" in relative_link.lower():
            floor_match = re.search(r'(\d+)(?:st|th|mf)', relative_link.lower())
            if floor_match:
                property_data['Floor_Number'] = int(floor_match.group(1))
            else:
                # Try to extract floor from the address number
                floor_match = re.search(r'(\d+)(?:st|th|mf)', relative_link.lower())
                if floor_match:
                    property_data['Floor_Number'] = int(floor_match.group(1))
                else:
                    property_data['Floor_Number'] = 1
        else:
            property_data['Floor_Number'] = 1
    
    # Validate construction year
    if property_data['Construction_Year'] is not None:
        current_year = datetime.datetime.now().year
        if property_data['Construction_Year'] > current_year:
            property_data['Construction_Year'] = None
            property_data['Built_Year'] = None
    
    return property_data

def main(sample_size=None):
    # Load list of property links from CSV
    df = pd.read_csv('data/scraped_properties.csv')
    
    # Get unique properties (since we now have consolidated data)
    unique_properties = df[['Property ID', 'Link']].drop_duplicates()
    links = unique_properties['Link'].tolist()
    unique_ids = unique_properties.set_index('Link')['Property ID'].to_dict()
    
    # Take a random sample if sample_size is specified
    if sample_size and sample_size < len(links):
        logging.info(f"Taking a random sample of {sample_size} links from {len(links)} total links")
        links = pd.Series(links).sample(n=sample_size, random_state=42).tolist()
    
    browser, playwright = setup_browser()
    context = browser.new_context()
    page = context.new_page()
    all_property_data = []
    
    start_time = time.time()
    total_links = len(links)
    
    try:
        for i, link in enumerate(links):
            unique_id = unique_ids.get(link, "Unknown ID")
            max_retries = 3
            retry_count = 0
            
            # Calculate progress
            progress = (i + 1) / total_links * 100
            elapsed_time = time.time() - start_time
            avg_time_per_item = elapsed_time / (i + 1) if i > 0 else 0
            remaining_items = total_links - (i + 1)
            estimated_remaining_time = remaining_items * avg_time_per_item
            
            logging.info(f"Processing property {i+1}/{total_links} ({progress:.1f}%)")
            logging.info(f"ID: {unique_id}")
            logging.info(f"Estimated time remaining: {estimated_remaining_time/60:.1f} minutes")
            
            while retry_count < max_retries:
                try:
                    property_data = fetch_property_data(page, link, unique_id)
                    all_property_data.append(property_data)
                    
                    # Add a longer delay every 10 requests
                    if i > 0 and i % 10 == 0:
                        logging.info(f"Taking a longer break after {i} requests...")
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
                temp_df.to_csv(f'data/property_details_partial_{i}.csv', index=False, encoding='utf-8-sig')
                logging.info(f"Saved partial progress after processing {i} items")
    
    except KeyboardInterrupt:
        logging.info("Received keyboard interrupt, saving current progress...")
        if all_property_data:
            pd.DataFrame(all_property_data).to_csv('data/property_details_interrupted.csv', index=False, encoding='utf-8-sig')
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
        output_file = 'data/property_details_sample.csv' if sample_size else 'data/property_details.csv'
        properties_df.to_csv(output_file, index=False, encoding='utf-8-sig')
        logging.info(f"Property details have been saved to '{output_file}'")
        
        # Log summary statistics
        total_properties = len(properties_df)
        properties_with_area = properties_df['Living_Area_M2'].notna().sum()
        properties_with_rooms = properties_df['Num_Rooms'].notna().sum()
        properties_with_year = properties_df['Construction_Year'].notna().sum()
        
        logging.info("\nScraping Summary:")
        logging.info(f"Total properties processed: {total_properties}")
        logging.info(f"Properties with area information: {properties_with_area} ({properties_with_area/total_properties*100:.1f}%)")
        logging.info(f"Properties with room count: {properties_with_rooms} ({properties_with_rooms/total_properties*100:.1f}%)")
        logging.info(f"Properties with construction year: {properties_with_year} ({properties_with_year/total_properties*100:.1f}%)")

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