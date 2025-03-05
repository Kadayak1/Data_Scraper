import csv
import uuid
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import random

# Set up Chrome options
chrome_options = Options()
chrome_options.add_argument('--headless')  # Run in headless mode
chrome_options.add_argument('--disable-gpu')

def fetch_page_data(page_number):
    # Initialize the driver
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
    page_data_list = []
    try:
        url = f'https://www.boligsiden.dk/landsdel/koebenhavns-omegn/solgte/alle?sortAscending=false&registrationTypes=auction&latestRegistrationType=auction&page={page_number}'
        print(f"Loading page {page_number}: {url}")
        driver.get(url)

        # Let the page load
        driver.implicitly_wait(10)

        # Add a random delay to help with server load
        time.sleep(random.uniform(2, 5))  # Waits between 2 and 5 seconds

        # Get the HTML content after JavaScript has been executed
        html = driver.page_source

        # Use BeautifulSoup to parse the HTML content
        soup = BeautifulSoup(html, 'html.parser')

        # Find property containers
        containers = soup.find_all('div', class_='shadow overflow-hidden mx-4')
        print(f"Page {page_number}: Found {len(containers)} target containers.")

        # Extract information from each container
        for container in containers:
            # Generate a unique ID for each property container
            unique_id = str(uuid.uuid4())
            link_tag = container.find('a')
            link = link_tag['href'] if link_tag else ""

            # Extract property type
            property_type_el = container.find('div', class_='text-gray-600').text.strip()
            property_type = property_type_el.split(' ', 1)[-1] if property_type_el else "N/A"

            address_div = link_tag.find('div', class_='font-black text-sm')
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
                            'Property Type': property_type,  # Include the property type
                            'Sale Type': sale_type,
                            'Sale Date': sale_date,
                            'Price': price,
                            'Page Number': page_number
                        })
    finally:
        driver.quit()

    return page_data_list

# List to store all the data
all_data_list = []

# Use ThreadPoolExecutor to scrape data from multiple pages concurrently with limited threads
with ThreadPoolExecutor(max_workers=3) as executor:  # Reduced number of threads
    # Submit tasks to load each page in the specified range
    future_to_page = {executor.submit(fetch_page_data, page_number): page_number for page_number in range(1, 30)}
    
    # Collect the results as they complete
    for future in as_completed(future_to_page):
        page_number = future_to_page[future]
        try:
            page_data = future.result()
            all_data_list.extend(page_data)
        except Exception as e:
            print(f"Error processing page {page_number}: {e}")

# Write the data to a CSV file
csv_columns = ['ID', 'Link', 'Address', 'Property Type', 'Sale Type', 'Sale Date', 'Price', 'Page Number']
with open('scraped_properties.csv', 'w', newline='', encoding='utf-8') as csvfile:
    writer = csv.DictWriter(csvfile, fieldnames=csv_columns)
    writer.writeheader()
    for data in all_data_list:
        writer.writerow(data)

print("Scraped data with unique IDs and page numbers per property has been saved to 'scraped_properties.csv'.")