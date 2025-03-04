from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup

# Set up Chrome options
chrome_options = Options()
chrome_options.add_argument('--headless')  # Run in headless mode
chrome_options.add_argument('--disable-gpu')

# Initialize the driver
driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)

try:
    # Load the webpage
    url = 'https://www.boligsiden.dk/landsdel/koebenhavns-omegn/solgte/alle?sortAscending=false&registrationTypes=auction&latestRegistrationType=auction'
    driver.get(url)
    print("Page loaded. Waiting for content.")

    # Let the page load, adjust timeout according to need
    driver.implicitly_wait(10)

    # Get the HTML content after JavaScript has been executed
    html = driver.page_source

    # Use BeautifulSoup to parse the HTML content
    soup = BeautifulSoup(html, 'html.parser')

    # Finding containers
    containers = soup.find_all('div', class_='shadow overflow-hidden mx-4')
    print(f"Found {len(containers)} target containers.")

    # Open the text file for writing
    with open("scraped_data.txt", "w", encoding="utf-8") as file:
        for i, container in enumerate(containers, 1):
            print(f"\nProcessing container #{i}")
            link_tag = container.find('a')
            if link_tag:
                link = link_tag['href']
                print(f"Link: {link}")
                file.write(f"Link: {link}\n")

            address_tag = container.find('div', class_='font-black text-sm')
            if address_tag:
                address = address_tag.text.strip()
                print(f"Address: {address}")
                file.write(f"Address: {address}\n")

            table_rows = container.find_all('tr')
            for row in table_rows:
                cells = row.find_all('td')
                if cells:
                    sale_type = cells[1].text.strip()
                    sale_date = cells[2].text.strip()
                    price = cells[3].text.strip()
                    print(f"Sale Type: {sale_type}, Sale Date: {sale_date}, Price: {price}")
                    file.write(f"Sale Type: {sale_type}, Sale Date: {sale_date}, Price: {price}\n")
            file.write("\n")  # Add a newline to separate records

finally:
    driver.quit()