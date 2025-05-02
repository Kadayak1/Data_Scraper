import csv
import uuid
from playwright.sync_api import sync_playwright, TimeoutError
from bs4 import BeautifulSoup
import time
import random
import os
import logging
from typing import List, Dict, Optional
from datetime import datetime, timedelta
import sys
from tqdm import tqdm
import urllib.parse
import json
import re

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('scraper.log'),
        logging.StreamHandler(sys.stdout)
    ]
)

class ProgressTracker:
    def __init__(self, total_pages: int):
        self.start_time = datetime.now()
        self.total_pages = total_pages
        self.processed_pages = 0
        self.total_containers = 0
        self.processed_containers = 0
        self.container_times = []
        self.page_times = []
        
    def start_page(self, page_number: int):
        self.page_start_time = datetime.now()
        logging.info(f"\n{'='*50}")
        logging.info(f"Starting page {page_number}/{self.total_pages}")
        
    def end_page(self, containers_count: int):
        page_time = (datetime.now() - self.page_start_time).total_seconds()
        self.page_times.append(page_time)
        self.processed_pages += 1
        self.total_containers += containers_count
        
        avg_page_time = sum(self.page_times) / len(self.page_times)
        remaining_pages = self.total_pages - self.processed_pages
        estimated_remaining_time = avg_page_time * remaining_pages
        
        logging.info(f"Page completed in {page_time:.2f}s")
        logging.info(f"Found {containers_count} containers")
        logging.info(f"Average page time: {avg_page_time:.2f}s")
        logging.info(f"Estimated remaining time: {timedelta(seconds=int(estimated_remaining_time))}")
        logging.info(f"Progress: {self.processed_pages}/{self.total_pages} pages ({self.processed_pages/self.total_pages*100:.1f}%)")
        
    def start_container(self):
        self.container_start_time = datetime.now()
        
    def end_container(self):
        container_time = (datetime.now() - self.container_start_time).total_seconds()
        self.container_times.append(container_time)
        self.processed_containers += 1
        
        if self.processed_containers % 10 == 0:  # Update progress every 10 containers
            avg_container_time = sum(self.container_times) / len(self.container_times)
            remaining_containers = self.total_containers - self.processed_containers
            estimated_remaining_time = avg_container_time * remaining_containers
            
            logging.info(f"Processed {self.processed_containers}/{self.total_containers} containers")
            logging.info(f"Average container time: {avg_container_time:.2f}s")
            logging.info(f"Estimated remaining time: {timedelta(seconds=int(estimated_remaining_time))}")
            
    def get_summary(self):
        total_time = (datetime.now() - self.start_time).total_seconds()
        avg_page_time = sum(self.page_times) / len(self.page_times) if self.page_times else 0
        avg_container_time = sum(self.container_times) / len(self.container_times) if self.container_times else 0
        
        logging.info("\n" + "="*50)
        logging.info("Scraping Summary:")
        logging.info(f"Total time: {timedelta(seconds=int(total_time))}")
        logging.info(f"Total pages processed: {self.processed_pages}")
        logging.info(f"Total containers processed: {self.processed_containers}")
        logging.info(f"Average page time: {avg_page_time:.2f}s")
        logging.info(f"Average container time: {avg_container_time:.2f}s")
        logging.info("="*50)

def setup_browser():
    playwright = sync_playwright().start()
    browser = playwright.chromium.launch(
        headless=True,
        args=[
            '--disable-blink-features=AutomationControlled',
            '--disable-features=IsolateOrigins,site-per-process',
            '--disable-site-isolation-trials',
            '--disable-web-security',
            '--disable-features=IsolateOrigins,site-per-process'
        ]
    )
    return browser, playwright

def wait_for_network_idle(page, timeout=30000):
    """Wait for network activity to settle down"""
    try:
        page.wait_for_load_state('networkidle', timeout=timeout)
    except TimeoutError:
        logging.warning("Network idle timeout, continuing anyway")

def construct_page_url(base_url: str, page_number: int) -> str:
    """Properly construct a URL with page parameter"""
    parsed_url = urllib.parse.urlparse(base_url)
    query_params = urllib.parse.parse_qs(parsed_url.query)
    
    # Update the page parameter
    query_params['page'] = [str(page_number)]
    
    # Rebuild the query string
    new_query = urllib.parse.urlencode(query_params, doseq=True)
    
    # Reconstruct the URL
    new_url = urllib.parse.urlunparse((
        parsed_url.scheme,
        parsed_url.netloc,
        parsed_url.path,
        parsed_url.params,
        new_query,
        parsed_url.fragment
    ))
    
    return new_url

def format_price(price_text: str) -> float:
    """Format and convert price string to numeric value"""
    if not price_text or price_text == "N/A":
        return None
    
    # Remove any non-numeric characters except for decimal points
    price_text = price_text.replace("kr.", "").replace(".", "").strip()
    # Keep only digits and decimal points
    price_text = re.sub(r'[^\d,]', '', price_text)
    # Replace comma with dot for decimal
    price_text = price_text.replace(",", ".")
    
    try:
        return float(price_text)
    except ValueError:
        logging.warning(f"Could not convert price: {price_text}")
        return None

def format_date(date_text: str) -> str:
    """Format and validate date string"""
    if not date_text or date_text == "N/A":
        return None
    
    # Check if it contains a date pattern DD-MM-YYYY
    date_match = re.search(r'(\d{2})[.-](\d{2})[.-](\d{4})', date_text)
    if date_match:
        day, month, year = date_match.groups()
        return f"{day}-{month}-{year}"
    
    # Check for numeric date format like DDMMYYYY
    num_match = re.search(r'(\d{1,2})(\d{2})(\d{4})', date_text)
    if num_match:
        day, month, year = num_match.groups()
        # Pad day with leading zero if needed
        if len(day) == 1:
            day = f"0{day}"
        # Ensure month is valid (01-12)
        if 1 <= int(month) <= 12:
            return f"{day}-{month}-{year}"
    
    return date_text

def determine_sale_type(sale_type_text: str) -> str:
    """Clean and standardize the sale type"""
    if not sale_type_text or sale_type_text == "N/A":
        return "N/A"
    
    # Lowercase for comparison
    sale_type_lower = sale_type_text.lower()
    
    # Map of known sale types
    sale_type_mapping = {
        "fri handel": "Fri handel",
        "tvangsauktion": "Tvangsauktion",
        "familie handel": "Familie handel",
        "andet": "Andet"
    }
    
    # Check each known sale type
    for key, value in sale_type_mapping.items():
        if key in sale_type_lower:
            return value
    
    return sale_type_text

def fetch_page_data(page, page_number: int, base_url: str, max_retries: int = 3) -> List[Dict]:
    page_data_list = []
    processed_property_ids = set()  # Track processed property IDs
    
    for attempt in range(max_retries):
        try:
            # Construct URL with page number
            url = construct_page_url(base_url, page_number)
            logging.info(f"Loading page {page_number} (attempt {attempt + 1}/{max_retries}): {url}")
            
            # Navigate to the page and wait for network idle
            page.goto(url, wait_until='domcontentloaded', timeout=60000)
            wait_for_network_idle(page)
            
            # Wait for the main content to load with specific selector
            page.wait_for_selector('div[class*="shadow overflow-hidden mx-4"]', timeout=30000)
            
            # Add a random delay to help with server load
            time.sleep(random.uniform(3, 6))
            
            # Save screenshot and HTML for debugging (only for first and failed pages)
            if page_number == 1 or attempt > 0:
                os.makedirs('debug/screenshots', exist_ok=True)
                page.screenshot(path=f'debug/screenshots/page_{page_number}_attempt_{attempt+1}.png')
                
                os.makedirs('debug/html', exist_ok=True)
                with open(f'debug/html/page_{page_number}_attempt_{attempt+1}.html', 'w', encoding='utf-8') as f:
                    f.write(page.content())
            
            # Get the HTML content after JavaScript has been executed
            html = page.content()
            
            # Use BeautifulSoup to parse the HTML content
            soup = BeautifulSoup(html, 'html.parser')
            
            # Find property containers with specific selector
            containers = soup.select('div[class*="shadow overflow-hidden mx-4"]')
            
            logging.info(f"Page {page_number}: Found {len(containers)} property containers.")
            
            if not containers:
                logging.warning(f"No containers found on page {page_number}, retrying...")
                time.sleep(random.uniform(5, 10))
                continue
            
            # Extract information from each container with progress tracking
            for container in tqdm(containers, desc="Containers", position=1, leave=False):
                try:
                    # Find link with specific selector
                    link_tag = container.select_one('a[href*="/adresse/"]')
                    if not link_tag:
                        continue
                        
                    link = link_tag['href']
                    # Use the link as the unique identifier for the property
                    property_id = link.split('/')[-1]
                    
                    # Skip if we've already processed this property
                    if property_id in processed_property_ids:
                        continue
                        
                    processed_property_ids.add(property_id)
                    
                    # Default values
                    property_type = "N/A"
                    address = "N/A"
                    postal_code = "N/A"
                    
                    # Extract postal code from property_id
                    # Format is typically: address-postalcode-city-id
                    if '-' in property_id:
                        parts = property_id.split('-')
                        for i, part in enumerate(parts):
                            # Postal code is typically a 4-digit number
                            if part.isdigit() and len(part) == 4:
                                postal_code = part
                                break
                    
                    # Find the property type - using the parent div of the property type content
                    type_container = container.select_one('div.text-gray-600.font-normal.text-sm')
                    if type_container:
                        property_type = type_container.text.strip()
                    
                    # Find the address
                    address_div = container.select_one('div.font-black.text-sm')
                    if address_div:
                        address = address_div.text.strip()
                    
                    # Look in the desktop view table as backup
                    table = container.find('table')
                    if table:
                        # Try to find property type from table header
                        thead_type = table.select_one('thead th:first-child div')
                        if thead_type and (property_type == "N/A" or not property_type):
                            property_type = thead_type.text.strip()
                        
                        # Find address from tbody if not already found
                        if address == "N/A":
                            tbody = table.find('tbody')
                            if tbody:
                                first_row = tbody.find('tr')
                                if first_row:
                                    address_cell = first_row.select_one('td[rowspan]')
                                    if address_cell:
                                        address_divs = address_cell.find_all('div')
                                        if len(address_divs) >= 1:
                                            address = address_divs[0].text.strip()
            
                    # Process sale records within the container
                    sales = []
                    
                    if table:
                        # Get only the tbody rows (skip thead)
                        tbody = table.find('tbody')
                        if tbody:
                            table_rows = tbody.find_all('tr')
                            
                            for row in table_rows:
                                cells = row.find_all('td')
                                
                                # Each row should have at least 3 cells (sale type, date, price)
                                if len(cells) < 3:
                                    continue
                                    
                                # If the first cell has rowspan, it's the address cell (skip it)
                                # The sale data starts from index 0 or 1 depending on the row
                                start_idx = 0
                                
                                # Check if the first cell has address info (has rowspan)
                                first_cell = cells[0]
                                if 'rowspan' in first_cell.attrs:
                                    # This is the address cell, sale data starts at index 1
                                    start_idx = 1
                                    
                                # Extract the sale data from the correct indices
                                if start_idx + 2 < len(cells):  # Make sure we have enough cells
                                    sale_type = cells[start_idx].text.strip()
                                    sale_date = cells[start_idx + 1].text.strip()
                                    price_text = cells[start_idx + 2].text.strip()
                                    
                                    # Format and clean the data
                                    sale_type_clean = determine_sale_type(sale_type)
                                    sale_date_clean = format_date(sale_date)
                                    price_clean = format_price(price_text)
                                    
                                    sales.append({
                                        'Sale Type': sale_type_clean,
                                        'Raw Sale Type': sale_type,
                                        'Sale Date': sale_date_clean,
                                        'Raw Sale Date': sale_date,
                                        'Price': price_clean,
                                        'Raw Price': price_text
                                    })
            
                    # If no sales records were found, add a record with N/A values
                    if not sales:
                        sales.append({
                            'Sale Type': 'N/A',
                            'Raw Sale Type': 'N/A',
                            'Sale Date': None,
                            'Raw Sale Date': 'N/A',
                            'Price': None,
                            'Raw Price': 'N/A'
                        })
                    
                    # Create a single entry for this property with all sales data
                    property_data = {
                        'Property ID': property_id,
                        'Link': link,
                        'Address': address,
                        'Postal_Code': postal_code,
                        'Property_Type': property_type,
                        'Sales': json.dumps(sales),  # Store all sales as JSON
                        'First Sale Type': sales[0]['Sale Type'] if sales else 'N/A',
                        'First Sale Date': sales[0]['Sale Date'] if sales else 'N/A',
                        'First Sale Price': sales[0]['Price'] if sales else 'N/A',
                        'Sales Count': len(sales),
                        'Page Number': page_number
                    }
                    
                    page_data_list.append(property_data)
                        
                except Exception as e:
                    logging.error(f"Error processing container: {str(e)}")
                    continue
            
            # Log the actual number of unique properties processed
            logging.info(f"Processed {len(processed_property_ids)} unique properties on page {page_number}")
            
            return page_data_list
            
        except TimeoutError:
            logging.warning(f"Timeout on page {page_number}, attempt {attempt + 1}/{max_retries}")
            if attempt < max_retries - 1:
                time.sleep(random.uniform(10, 15))
                continue
            else:
                logging.error(f"All retries failed for page {page_number}")
                return []
        except Exception as e:
            logging.error(f"Error processing page {page_number}: {e}")
            if attempt < max_retries - 1:
                time.sleep(random.uniform(5, 10))
                continue
            else:
                return []
    
    return page_data_list

def main():
    all_data_list = []
    all_property_ids = set()  # Track all unique property IDs
    
    # Define the base URLs to scrape
    base_urls = [
        'https://www.boligsiden.dk/landsdel/koebenhavns-omegn/solgte/alle?sortAscending=false&mapBounds=12.144761,55.587612,12.609994,55.82086&registrationTypes=auction&latestRegistrationType=auction',
        #'https://www.boligsiden.dk/omraade/jylland/solgte?sortAscending=false&registrationTypes=auction&latestRegistrationType=auction',
        #'https://www.boligsiden.dk/landsdel/fyn/solgte?sortAscending=false&registrationTypes=auction&latestRegistrationType=auction'
    ]
    
    # Set up browser outside the try block so we can refer to it in the finally block
    browser = None
    playwright = None
    
    try:
        browser, playwright = setup_browser()
        context = browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        )
        page = context.new_page()
        
        # Process each base URL
        for base_url in base_urls:
            logging.info(f"\n{'='*50}")
            logging.info(f"Starting to process URL: {base_url}")
            
            try:
                # First, determine the total number of pages
                page.goto(base_url, wait_until='domcontentloaded', timeout=60000)
                wait_for_network_idle(page)
                
                # Try to find the total number of pages
                try:
                    # Look for pagination elements
                    pagination = page.query_selector('div[class*="pagination"]')
                    if pagination:
                        # Try to find the last page number
                        page_links = pagination.query_selector_all('a')
                        if page_links:
                            last_page = page_links[-2].text_content()
                            total_pages = int(last_page)
                            logging.info(f"Found {total_pages} total pages in pagination")
                        else:
                            # If no page links found, check if there's a "next" button
                            next_button = pagination.query_selector('a[class*="next"]')
                            if next_button:
                                # If there's a next button, we'll need to determine pages dynamically
                                total_pages = 29  # Default to known value
                                logging.info("Found pagination with next button, using default of 29 pages")
                            else:
                                total_pages = 29
                                logging.info("No pagination links found, assuming single page")
                    else:
                        # Check if there are any results at all
                        no_results = page.query_selector('div[class*="no-results"]')
                        if no_results:
                            logging.warning("No results found for this URL")
                            continue
                        else:
                            total_pages = 29  # Default to known value
                            logging.info("No pagination found, using default of 29 pages")
                except Exception as e:
                    logging.warning(f"Could not determine total pages: {e}")
                    total_pages = 29 # Default to known value
                    logging.info("Using default of 29 pages")
                
                progress_tracker = ProgressTracker(total_pages)
                page_number = 1
                consecutive_empty_pages = 0
                has_next_page = True
                
                with tqdm(total=total_pages, desc="Pages", position=0) as pbar:
                    while has_next_page and consecutive_empty_pages < 3:
                        try:
                            progress_tracker.start_page(page_number)
                            page_data = fetch_page_data(page, page_number, base_url)
                            
                            if not page_data:
                                consecutive_empty_pages += 1
                                logging.warning(f"Empty page {page_number}, consecutive empty pages: {consecutive_empty_pages}")
                                # Call end_page with 0 containers if no data
                                progress_tracker.end_page(0)
                            else:
                                consecutive_empty_pages = 0
                                # Count unique properties for this page
                                page_property_ids = set()
                                for data in page_data:
                                    page_property_ids.add(data['Property ID'])
                                    all_property_ids.add(data['Property ID'])
                                
                                all_data_list.extend(page_data)
                                logging.info(f"Successfully processed page {page_number}, total unique properties: {len(all_property_ids)}")
                                
                                # Update progress tracker with actual count of unique properties on this page
                                progress_tracker.end_page(len(page_property_ids))
                            
                            pbar.update(1)
                            
                            # Check if there's a next page
                            if page_number < total_pages:
                                # Add a small delay between pages
                                time.sleep(random.uniform(3, 6))
                                page_number += 1
                            else:
                                has_next_page = False
                            
                        except Exception as e:
                            logging.error(f"Error processing page {page_number} for URL {base_url}: {e}")
                            consecutive_empty_pages += 1
                            # Call end_page with 0 containers on error
                            progress_tracker.end_page(0)
                            
                            # Check if we need to restart the browser due to a crash
                            try:
                                # Try a simple operation to check if browser is still usable
                                page.evaluate("1 + 1")
                            except Exception:
                                logging.error("Browser appears to have crashed, restarting...")
                                # Close and restart browser
                                try:
                                    if context:
                                        context.close()
                                    if browser:
                                        browser.close()
                                    if playwright:
                                        playwright.stop()
                                except Exception as close_error:
                                    logging.error(f"Error closing browser: {close_error}")
                                
                                # Restart browser
                                browser, playwright = setup_browser()
                                context = browser.new_context(
                                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
                                )
                                page = context.new_page()
                                logging.info("Browser restarted successfully")
                            
                            time.sleep(random.uniform(10, 15))
                            continue
                
                progress_tracker.get_summary()
                logging.info(f"Finished processing URL: {base_url}")
                
                # Save intermediate results after each base URL is processed
                save_data_to_csv(all_data_list, f"data/scraped_properties_intermediate_{len(all_property_ids)}_properties.csv")
                
                time.sleep(random.uniform(10, 15))
            except Exception as url_error:
                logging.error(f"Error processing URL {base_url}: {url_error}")
                # Continue with the next URL
                continue
        
        # Write final data to CSV file
        save_data_to_csv(all_data_list, "data/scraped_properties.csv")
        
        # Also save a separate file with expanded sales data (one row per sale)
        save_expanded_sales_data(all_data_list, "data/scraped_properties_expanded.csv")
        
        # Calculate and log summary statistics
        unique_properties = len(all_property_ids)
        total_sales = sum(data['Sales Count'] for data in all_data_list)
        logging.info(f"\n{'='*50}")
        logging.info("Scraping Summary:")
        logging.info(f"Total unique properties: {unique_properties}")
        logging.info(f"Total sale records: {total_sales}")
        if unique_properties > 0:
            logging.info(f"Average sales per property: {total_sales/unique_properties:.2f}")
        logging.info(f"Scraped data has been saved to 'data/scraped_properties.csv'")
        logging.info(f"Expanded sales data has been saved to 'data/scraped_properties_expanded.csv'")
        logging.info(f"{'='*50}")
        
    except Exception as e:
        logging.critical(f"Critical error in main function: {e}")
        # Save any data we've collected so far
        if all_data_list:
            save_data_to_csv(all_data_list, "data/scraped_properties_error_recovery.csv")
            logging.info(f"Saved {len(all_data_list)} records to error recovery file")
    
    finally:
        # Clean up resources
        try:
            if 'context' in locals() and context:
                context.close()
            if browser:
                browser.close()
            if playwright:
                playwright.stop()
        except Exception as close_error:
            logging.error(f"Error during cleanup: {close_error}")

def save_data_to_csv(data_list: List[Dict], filepath: str):
    """Save data to a CSV file"""
    if not data_list:
        logging.warning(f"No data to save to {filepath}")
        return
        
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    csv_columns = ['Property ID', 'Link', 'Address', 'Postal_Code', 'Property_Type', 'Sales', 
                   'First Sale Type', 'First Sale Date', 'First Sale Price', 
                   'Sales Count', 'Page Number']
    
    try:
        with open(filepath, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=csv_columns)
            writer.writeheader()
            for data in data_list:
                writer.writerow(data)
        logging.info(f"Successfully saved {len(data_list)} records to {filepath}")
    except Exception as e:
        logging.error(f"Error saving to CSV {filepath}: {e}")

def save_expanded_sales_data(data_list: List[Dict], filepath: str):
    """Save expanded sales data with one row per sale"""
    if not data_list:
        logging.warning(f"No data to save to {filepath}")
        return
        
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    expanded_data = []
    
    # Expand the sales data
    for property_data in data_list:
        try:
            sales = json.loads(property_data['Sales'])
            for i, sale in enumerate(sales):
                expanded_row = {
                    'Property ID': property_data['Property ID'],
                    'Address': property_data['Address'],
                    'Postal_Code': property_data['Postal_Code'],
                    'Property_Type': property_data['Property_Type'],
                    'Sale Type': sale['Sale Type'],
                    'Sale Date': sale['Sale Date'],
                    'Price': sale['Price'],
                    'Sale Index': i + 1,
                    'Total Sales': len(sales)
                }
                expanded_data.append(expanded_row)
        except Exception as e:
            logging.error(f"Error expanding sales data for property {property_data['Property ID']}: {e}")
    
    # Define columns for the expanded data
    csv_columns = ['Property ID', 'Address', 'Postal_Code', 'Property_Type',
                   'Sale Type', 'Sale Date', 'Price',
                   'Sale Index', 'Total Sales']
    
    try:
        with open(filepath, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=csv_columns)
            writer.writeheader()
            for data in expanded_data:
                writer.writerow(data)
        logging.info(f"Successfully saved {len(expanded_data)} expanded sales records to {filepath}")
    except Exception as e:
        logging.error(f"Error saving expanded data to CSV {filepath}: {e}")

if __name__ == "__main__":
    main()