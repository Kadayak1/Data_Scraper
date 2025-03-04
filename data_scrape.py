import csv
import uuid
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup

# Set up Chrome options
chrome_options = Options()
chrome_options.add_argument('--headless')  # Run in headless mode
chrome_options.add_argument('--disable-gpu')

# Initialize the driver
driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)

# List to store data
data_list = []

try:
    # Iterate over the number of pages you want to scrape, e.g., 29 pages
    for page_number in range(1, 30):  # Adjust the range for 29 pages
        # Modify the URL to include the current page number
        url = f'https://www.boligsiden.dk/landsdel/koebenhavns-omegn/solgte/alle?sortAscending=false&registrationTypes=auction&latestRegistrationType=auction&page={page_number}'
        print(f"Loading page {page_number}: {url}")
        driver.get(url)

        # Let the page load
        driver.implicitly_wait(10)

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

                        data_list.append({
                            'ID': unique_id,
                            'Link': link,
                            'Address': address,
                            'Sale Type': sale_type,
                            'Sale Date': sale_date,
                            'Price': price,
                            'Page Number': page_number
                        })

finally:
    driver.quit()

# Write the data to a CSV file
csv_columns = ['ID', 'Link', 'Address', 'Sale Type', 'Sale Date', 'Price', 'Page Number']
with open('scraped_properties.csv', 'w', newline='', encoding='utf-8') as csvfile:
    writer = csv.DictWriter(csvfile, fieldnames=csv_columns)
    writer.writeheader()
    for data in data_list:
        writer.writerow(data)

print("Scraped data with unique IDs and page numbers per property has been saved to 'scraped_properties.csv'.")