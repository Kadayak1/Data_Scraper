import csv
import uuid
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import time
import random
import os
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def setup_browser():
    playwright = sync_playwright().start()
    browser = playwright.chromium.launch(headless=True)
    return browser, playwright

def fetch_page_data(page, page_number, base_url):
    page_data_list = []
    
    try:
        # Construct URL with page number
        url = f'{base_url}&page={page_number}'
        logging.info(f"Loading page {page_number}: {url}")
        
        # Navigate to the page
        page.goto(url, wait_until='networkidle')
        
        # Add a random delay to help with server load
        time.sleep(random.uniform(2, 5))
        
        # Wait for the property containers to be visible
        page.wait_for_selector('div.shadow.overflow-hidden.mx-4', timeout=10000)
        
        # Save screenshot for debugging
        os.makedirs('debug_screenshots', exist_ok=True)
        page.screenshot(path=f'debug_screenshots/page_{page_number}.png')
        
        # Save HTML for debugging
        os.makedirs('debug_html', exist_ok=True)
        with open(f'debug_html/page_{page_number}.html', 'w', encoding='utf-8') as f:
            f.write(page.content())
        
        # Get the HTML content after JavaScript has been executed
        html = page.content()
        
        # Use BeautifulSoup to parse the HTML content
        soup = BeautifulSoup(html, 'html.parser')
        
        # Find property containers
        containers = soup.find_all('div', class_='shadow overflow-hidden mx-4')
        logging.info(f"Page {page_number}: Found {len(containers)} target containers.")
        
        # Extract information from each container
        for container in containers:
            # Generate a unique ID for each property container
            unique_id = str(uuid.uuid4())
            link_tag = container.find('a')
            link = link_tag['href'] if link_tag else ""
            
            # Extract property type
            property_type_el = container.find('div', class_='text-gray-600')
            property_type = property_type_el.text.strip().split(' ', 1)[-1] if property_type_el else "N/A"
            
            # Extract address
            address_div = link_tag.find('div', class_='font-black text-sm') if link_tag else None
            address_details = address_div.find_all('font') if address_div else []
            address_lines = [line.text for line in address_details]
            address = ', '.join(address_lines) if address_lines else ""
            
            # Process sale records within the container
            table = container.find('table')
            if table:
                table_rows = table.find_all('tr')
                for row in table_rows:
                    cells = row.find_all('td')
                    if len(cells) >= 4:
                        sale_type = cells[0].text.strip()
                        sale_date = cells[1].text.strip()
                        price = cells[2].text.strip()
                        
                        page_data_list.append({
                            'ID': unique_id,
                            'Link': link,
                            'Address': address,
                            'Property Type': property_type,
                            'Sale Type': sale_type,
                            'Sale Date': sale_date,
                            'Price': price,
                            'Page Number': page_number
                        })
                        
    except Exception as e:
        logging.error(f"Error processing page {page_number}: {e}")
    
    return page_data_list

def main():
    browser, playwright = setup_browser()
    context = browser.new_context()
    page = context.new_page()
    all_data_list = []
    
    # Define the base URLs to scrape
    base_urls = [
        'https://www.boligsiden.dk/landsdel/koebenhavns-omegn/solgte/alle?sortAscending=false&registrationTypes=auction&latestRegistrationType=auction',
        'https://www.boligsiden.dk/omraade/sjaelland/solgte?sortAscending=false&registrationTypes=auction&latestRegistrationType=auction',
        'https://www.boligsiden.dk/omraade/jylland/solgte?sortAscending=false&registrationTypes=auction&latestRegistrationType=auction',
        'https://www.boligsiden.dk/landsdel/fyn/solgte?sortAscending=false&registrationTypes=auction&latestRegistrationType=auction'
    ]
    
    try:
        # Process each base URL
        for base_url in base_urls:
            logging.info(f"Processing URL: {base_url}")
            # Process pages sequentially for each URL
            for page_number in range(1, 30):  # Keep the same page limit for each URL
                try:
                    page_data = fetch_page_data(page, page_number, base_url)
                    if not page_data:  # If no data was found, we've reached the end of pages
                        logging.info(f"No more data found for URL: {base_url}")
                        break
                    all_data_list.extend(page_data)
                    # Add a small delay between pages
                    time.sleep(random.uniform(1, 3))
                except Exception as e:
                    logging.error(f"Error processing page {page_number} for URL {base_url}: {e}")
                    continue
            
            # Add a longer delay between different URLs
            time.sleep(random.uniform(5, 8))
        
        # Write the data to a CSV file
        csv_columns = ['ID', 'Link', 'Address', 'Property Type', 'Sale Type', 'Sale Date', 'Price', 'Page Number']
        with open('scraped_properties.csv', 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=csv_columns)
            writer.writeheader()
            for data in all_data_list:
                writer.writerow(data)
        
        logging.info(f"Scraped data has been saved to 'scraped_properties.csv'. Total properties: {len(all_data_list)}")
        
    finally:
        context.close()
        browser.close()
        playwright.stop()

if __name__ == "__main__":
    main()