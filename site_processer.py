import logging
import pandas as pd
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import os
import time
import random
import re
import datetime
import json
from selenium.webdriver.common.by import By
from selenium import webdriver
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import concurrent.futures
import multiprocessing
import csv

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Compile regex patterns once for better performance
REGEX_PATTERNS = {
    'living_area': [
        re.compile(r'(?:Boligareal|Bolig|Areal|Living area|Area)(?:\s*:)?\s*(\d+(?:[,.]\d+)?)\s*(?:m²|kvm|sqm)', re.IGNORECASE),
        re.compile(r'(\d+(?:[,.]\d+)?)\s*(?:m²|kvm|sqm)(?:\s*bolig|-areal|boligareal|living area|area)', re.IGNORECASE),
        re.compile(r'areal(?:\s*:)?\s*(\d+(?:[,.]\d+)?)\s*(?:m²|kvm|sqm)', re.IGNORECASE),
        re.compile(r'(?:etageareal|ejendomsareal)(?:\s*:)?\s*(\d+(?:[,.]\d+)?)\s*(?:m²|kvm|sqm)', re.IGNORECASE)
    ],
    'rooms': [
        re.compile(r'(?:Værelser|Rum|Rooms)(?:\s*:)?\s*(\d+(?:[,.]\d+)?)', re.IGNORECASE),
        re.compile(r'(\d+(?:[,.]\d+)?)\s*(?:værelser|vær|rum|rooms)', re.IGNORECASE),
        re.compile(r'antal\s*(?:rum|værelser)(?:\s*:)?\s*(\d+(?:[,.]\d+)?)', re.IGNORECASE)
    ],
    'build_year': [
        re.compile(r'(?:Byggeår|Bygget|Opført|Built|Construction year)(?:\s*:)?\s*(\d{4})', re.IGNORECASE),
        re.compile(r'(?:opført|bygget)(?:\s+i)?\s*(?:år)?\s*(\d{4})', re.IGNORECASE),
        re.compile(r'(?:year|år)(?:\s+of)?\s*(?:construction|built|opført)(?:\s*:)?\s*(\d{4})', re.IGNORECASE)
    ],
    'energy_label': [
        re.compile(r'(?:Energimærke|Energimaerke|Energy label|Energy rating|Energy class)(?:\s*:)?\s*\b([A-G](?:[+\d]*))\b', re.IGNORECASE),
        re.compile(r'(?:energy|energi)(?:\s*[-:])?\s*\b([A-G](?:[+\d]*))\b', re.IGNORECASE),
        re.compile(r'\b([A-G](?:[+\d]*))-?mærk(?:e|ning)?', re.IGNORECASE)
    ],
    'price': [
        re.compile(r'(?:Pris|Kontantpris|Price|Asking price)(?:\s*:)?\s*(?:kr\.?|DKK|€)?\s*([\d.,]+)(?:\s*(?:kr\.?|DKK|€))?', re.IGNORECASE),
        re.compile(r'(?:kr\.?|DKK|€)\s*([\d.,]+)(?:\s*(?:kr\.?|DKK|€|v/|inkl))?', re.IGNORECASE),
        re.compile(r'(?:salgspris|købspris|handelspris)(?:\s*:)?\s*(?:kr\.?|DKK|€)?\s*([\d.,]+)', re.IGNORECASE)
    ]
}

def setup_browser():
    """Sets up a browser with appropriate configuration for JavaScript-heavy sites."""
    playwright = sync_playwright().start()
    
    # Use non-headless mode for debugging if needed
    headless = True  # Set to False for debugging
    
    # Configure browser with appropriate settings
    browser = playwright.chromium.launch(
        headless=headless,
        args=[
            '--disable-web-security',  # Bypasses CORS for better data extraction
            '--disable-features=IsolateOrigins,site-per-process',  # Helps with some complex sites
            '--disable-site-isolation-trials',
            '--disable-setuid-sandbox',
            '--no-sandbox'
        ],
        timeout=60000  # Increase launch timeout to 60 seconds
    )
    
    return browser, playwright

def extract_property_details(soup):
    """
    Extract property details from the soup object.
    Returns a dictionary of property details.
    """
    details = {}
    
    # Try multiple selectors for detail sections
    detail_sections = []
    for selector in [
        ".property-details", ".property-specs", ".property-info", 
        "[class*='details']", "[class*='specs']", "[class*='info']",
        "[id*='details']", "[id*='specifications']", "[id*='info']",
        "section", "article", ".facts-table", ".estateFacts"
    ]:
        sections = soup.select(selector)
        if sections:
            detail_sections.extend(sections)
            logging.info(f"Found {len(sections)} detail sections with selector: {selector}")
    
    # Try various selectors for detail rows
    detail_rows = []
    for section in detail_sections:
        for row_selector in [
            "tr", ".fact-row", ".detail-row", "li", ".item", 
            "[class*='row']", "[class*='item']", "[class*='field']",
            "div.row", "div.flex"
        ]:
            rows = section.select(row_selector)
            if rows:
                detail_rows.extend(rows)
                logging.info(f"Found {len(rows)} detail rows with selector: {row_selector}")
    
    # Process each detail row
    processed_details = {}
    for row in detail_rows:
        try:
            # Try to find label and value divs in various formats
            label_div = None
            value_div = None
            
            # Method 1: Common class names for label and value
            for label_selector in [".label", ".key", ".name", "dt", "th", "[class*='label']", "[class*='key']"]:
                if not label_div:
                    label_div = row.select_one(label_selector)
            
            for value_selector in [".value", ".val", ".data", "dd", "td", "[class*='value']", "[class*='val']"]:
                if not value_div:
                    value_div = row.select_one(value_selector)
            
            # Method 2: If not found, look for strong/span pairs
            if not label_div or not value_div:
                if row.find("strong") and row.find("span"):
                    label_div = row.find("strong")
                    # Assume value is in the span that's not the label
                    spans = row.find_all("span")
                    if spans:
                        for span in spans:
                            if label_div not in span.descendants:
                                value_div = span
                                break
            
            # Method 3: Look for h3/p or h4/p pairs
            if not label_div or not value_div:
                headers = row.select("h3, h4, h5")
                if headers and row.find("p"):
                    label_div = headers[0]
                    value_div = row.find("p")
            
            # Method 4: Last resort - use first and second divs or spans
            if not label_div or not value_div:
                divs = row.find_all("div", recursive=False)
                if len(divs) >= 2:
                    label_div = divs[0]
                    value_div = divs[1]
                else:
                    spans = row.find_all("span", recursive=False)
                    if len(spans) >= 2:
                        label_div = spans[0]
                        value_div = spans[1]
            
            # If we have both label and value
            if label_div and value_div:
                label = label_div.get_text().strip().lower()
                value = value_div.get_text().strip()
                
                # Clean up the label by removing any trailing colons
                label = label.rstrip(":").strip()
                
                # Map common Danish property terms to English
                danish_to_english = {
                    'boligareal': 'living_area',
                    'areal': 'area',
                    'grundareal': 'plot_area',
                    'værelser': 'rooms',
                    'rum': 'rooms',
                    'byggeår': 'build_year',
                    'opført': 'build_year',
                    'energimærke': 'energy_label',
                    'energi': 'energy_label',
                    'sagsnr': 'case_number',
                    'kontantpris': 'price',
                    'pris': 'price',
                    'ejerudgift': 'owner_cost',
                    'brutto/netto': 'gross_net',
                    'udbetaling': 'down_payment',
                    'grundskyld': 'property_tax',
                    'boligtype': 'property_type',
                    'etage': 'floor',
                    'kælder': 'basement',
                    'liggetid': 'days_on_market'
                }
                
                # Map the label to English if possible
                mapped_label = None
                for danish, english in danish_to_english.items():
                    if danish in label:
                        mapped_label = english
                        break
                
                # Use the mapped label or the original if no mapping found
                if mapped_label:
                    label = mapped_label
                
                # Clean the value - remove any non-breaking spaces and extra whitespace
                value = value.replace('\xa0', ' ').strip()
                
                # Handle common units and formats
                if 'm²' in value or 'kvm' in value:
                    value = clean_numerical_value(value, 'area')
                elif 'kr' in value.lower() or 'dkk' in value.lower() or '€' in value:
                    value = clean_numerical_value(value, 'price')
                elif re.search(r'\b\d{4}\b', value) and ('år' in label.lower() or 'year' in label.lower() or 'opført' in label.lower() or 'bygget' in label.lower()):
                    value = clean_numerical_value(value, 'year')
                elif any(w in label.lower() for w in ['antal', 'rooms', 'værelser', 'rum', 'bedrooms']):
                    value = clean_numerical_value(value, 'number')
                
                processed_details[label] = value
                logging.debug(f"Extracted detail: {label} = {value}")
        
        except Exception as e:
            logging.error(f"Error processing detail row: {str(e)}")
    
    # Special handling for energy label which might be in an image
    if 'energy_label' not in processed_details:
        # Try to find energy label images or special elements
        energy_selectors = [
            "img[src*='energy'], img[alt*='energy'], img[src*='energi'], img[alt*='energi']",
            "[class*='energy-label'], [class*='energi'], [id*='energy'], [id*='energi']",
            ".energy-rating, .energy-class, .energy-certificate"
        ]
        
        for selector in energy_selectors:
            energy_elements = soup.select(selector)
            if energy_elements:
                for element in energy_elements:
                    # Check if it's an image with energy rating in alt text or src
                    if element.name == 'img':
                        alt_text = element.get('alt', '')
                        src_text = element.get('src', '')
                        
                        # Look for energy rating (A-G) in alt text or src
                        energy_match = re.search(r'\b([A-G][+\-]?)\b', alt_text + ' ' + src_text, re.IGNORECASE)
                        if energy_match:
                            processed_details['energy_label'] = energy_match.group(1).upper()
                            break
                    
                    # Check if it's an element with energy class as text content
                    else:
                        text = element.get_text().strip()
                        energy_match = re.search(r'\b([A-G][+\-]?)\b', text, re.IGNORECASE)
                        if energy_match:
                            processed_details['energy_label'] = energy_match.group(1).upper()
                            break
    
    return processed_details

def parse_address(address_text):
    """Parse address into street, postal code, and city with improved handling."""
    address_parts = {
        'Street': "N/A",
        'Postal_Code': "N/A",
        'City': "N/A"
    }
    
    if not address_text or address_text == "N/A":
        return address_parts
        
    # First try to match the standard format: Street, Postal_Code City
    match = re.match(r'^(.*?),?\s+(\d{4})\s+([^,]+)(?:,\s*(.+))?$', address_text)
    
    if match:
        street = match.group(1).strip()
        postal = match.group(2)
        city = match.group(3).strip()
        
        # Handle additional location info
        if match.group(4):
            city = f"{city}, {match.group(4).strip()}"
            
        address_parts['Street'] = street
        address_parts['Postal_Code'] = postal
        address_parts['City'] = city
    else:
        # Fallback: Try to find postal code and work backwards/forwards
        postal_match = re.search(r'(\d{4})', address_text)
        if postal_match:
            postal = postal_match.group(1)
            parts = address_text.split(postal)
            
            if len(parts) >= 2:
                street = parts[0].strip().rstrip(',')
                city = parts[1].strip().lstrip(',')
                
                address_parts['Street'] = street
                address_parts['Postal_Code'] = postal
                address_parts['City'] = city
    
    # If no postal code was found, but we have what looks like a street name
    if address_parts['Postal_Code'] == "N/A" and len(address_text) > 5:
        address_parts['Street'] = address_text.strip()
    
    return address_parts

def format_value_for_ml(value, value_type='string'):
    """Enhanced value formatting with better handling of edge cases."""
    if not value or value in ["N/A", "Ikke oplyst"]:
        return None
        
    if value_type == 'number':
        # Handle decimal numbers and ranges
        matches = re.findall(r'(\d+(?:[,.]\d+)?)', value)
        if matches:
            # If multiple numbers found, take the first one
            num_str = matches[0].replace(',', '.')
            try:
                return float(num_str)
            except ValueError:
                return None
        return None
        
    if value_type == 'price':
        if not value:
            return None
            
        # Remove parenthetical content
        value = re.sub(r'\([^)]*\)', '', value)
        
        # Extract price value, handling different formats
        price_match = re.search(r'([\d.,]+)(?:\s*(?:kr\.?|DKK))?', value)
        if price_match:
            price_str = price_match.group(1)
            # Remove dots and replace comma with dot
            price_str = price_str.replace('.', '').replace(',', '.')
            try:
                return float(price_str)
            except ValueError:
                return None
        return None
        
    if value_type == 'year':
        # Extract year, handling ranges and approximate years
        year_match = re.search(r'(\d{4})', value)
        if year_match:
            try:
                year = int(year_match.group(1))
                current_year = datetime.datetime.now().year
                # Basic validation
                if 1500 <= year <= current_year + 5:  # Allow for planned construction
                    return year
            except ValueError:
                pass
        return None
        
    # For string values, clean and standardize
    return value.strip()

def extract_modal_data(driver):
    """Extracts property data from a modal dialog that has been opened."""
    try:
        # Initialize the dictionary to store extracted modal data
        modal_data = {}
        
        # Dictionary mapping Danish field names to our standardized field names
        field_mapping = {
            'Boligareal': 'Living_Area',
            'Grundareal': 'Lot_Size',
            'Vægtet areal': 'Weighted_Area',
            'Opførelsesår': 'Built_Year',
            'Antal værelser': 'Rooms',
            'Antal toiletter': 'Toilets',
            'Antal badeværelser': 'Bathrooms',
            'Antal etager': 'Floor_Count',
            'Seneste ombygningsår': 'Last_Remodel_Year',
            'Kælderareal': 'Basement_Size',
            'Energimærke': 'Energy_Label'
        }
        
        # Wait briefly for the modal to be fully visible
        time.sleep(1)
        
        # Find all rows in the modal that might contain property information
        try:
            # Try different approaches to find the rows
            rows = driver.find_elements(By.XPATH, "//div[@role='dialog']//div[contains(@class, 'row')] | //div[@role='dialog']//div[contains(@class, 'grid')] | //div[@id='modal-root']//div[contains(@class, 'flex')]")
            
            if not rows:
                # If no rows found with class-based approach, try more general approach
                rows = driver.find_elements(By.XPATH, "//div[@role='dialog']//div | //div[@id='modal-root']//div")
                
            # Process each row
            for row in rows:
                row_text = row.text.strip()
                
                # Skip empty rows or very short text (probably not a data row)
                if not row_text or len(row_text) < 3:
                    continue
                
                # Check if this row contains any of our field names
                for danish_name, field_name in field_mapping.items():
                    if danish_name in row_text:
                        # Found a match, extract the value
                        # The value is typically after the field name, separated by a delimiter
                        value_text = row_text.split(danish_name, 1)[1].strip()
                        if value_text:
                            # Remove any common delimiters like ":" at the beginning
                            value_text = value_text.lstrip(':').strip()
                            modal_data[field_name] = value_text
                            logging.debug(f"Found {field_name}: {value_text}")
                            break
        except Exception as e:
            logging.error(f"Error processing rows in modal: {e}")
        
        # If we didn't find rows with the above approach, try looking for labels and values
        if not modal_data:
            try:
                # Find all label elements
                labels = driver.find_elements(By.XPATH, "//div[@role='dialog']//span | //div[@role='dialog']//div | //div[@id='modal-root']//span | //div[@id='modal-root']//div")
                
                for label in labels:
                    label_text = label.text.strip()
                    
                    # Check if this label matches any of our field names
                    for danish_name, field_name in field_mapping.items():
                        if danish_name in label_text:
                            # Try to find the value in the next element
                            try:
                                # Find the parent of this label
                                parent_element = driver.execute_script("return arguments[0].parentNode;", label)
                                
                                # Find all elements within the parent that might contain the value
                                value_elements = parent_element.find_elements(By.XPATH, ".//div | .//span | .//p")
                                
                                for value_elem in value_elements:
                                    value_text = value_elem.text.strip()
                                    
                                    # Skip if it's the label itself or too short
                                    if value_text == label_text or not value_text or len(value_text) < 2:
                                        continue
                                    
                                    # Skip if it contains other field names (likely another label)
                                    if any(name in value_text for name in field_mapping.keys()):
                                        continue
                                    
                                    modal_data[field_name] = value_text
                                    logging.debug(f"Found {field_name}: {value_text}")
                                    break
                            except Exception as e:
                                logging.error(f"Error finding value for {field_name}: {e}")
                            break
            except Exception as e:
                logging.error(f"Error finding labels in modal: {e}")
        
        # Special handling for energy label which might be displayed differently
        if 'Energy_Label' not in modal_data:
            try:
                # Try to find energy label directly
                energy_elements = driver.find_elements(By.XPATH, "//div[contains(@class, 'energy')] | //div[contains(text(), 'Energimærke')] | //span[contains(text(), 'Energimærke')]")
                
                for element in energy_elements:
                    element_text = element.text.strip()
                    if "Energimærke" in element_text:
                        # Extract the energy rating (usually a letter A-G, possibly with +/-)
                        energy_match = re.search(r'[A-G][+\-]?', element_text, re.IGNORECASE)
                        if energy_match:
                            modal_data['Energy_Label'] = energy_match.group(0)
                            break
                        
                        # If no match with regex, try to extract the part after "Energimærke"
                        parts = element_text.split("Energimærke", 1)
                        if len(parts) > 1 and parts[1].strip():
                            # Take the first word/character after "Energimærke"
                            energy_value = parts[1].strip().split()[0]
                            if energy_value:
                                modal_data['Energy_Label'] = energy_value
                                break
            except Exception as e:
                logging.error(f"Error extracting energy label: {e}")
        
        return modal_data
    except Exception as e:
        logging.error(f"Error extracting data from modal: {e}")
        return {}

def handle_didomi_consent(driver):
    """Handle Didomi cookie consent using direct JavaScript methods to bypass UI interactions"""
    try:
        # Try to set Didomi cookies and preferences using JavaScript
        didomi_script = """
        try {
            // Try to auto-accept all cookies via Didomi API if available
            if (window.Didomi) {
                console.log("Didomi found, setting consent...");
                window.didomiSettings = {
                    notice: {
                        enable: false
                    }
                };
                window.Didomi.setUserAgreeToAll();
                
                // Hide popup if still present
                var popup = document.getElementById('didomi-popup');
                if (popup) {
                    popup.style.display = 'none';
                    console.log("Hid Didomi popup");
                }
                return true;
            }
            
            // If Didomi object not available, try to click the accept button
            var acceptButtons = document.querySelectorAll('button.didomi-button-highlight, button.didomi-button-accept, #didomi-notice-agree-button');
            for (var i = 0; i < acceptButtons.length; i++) {
                if (acceptButtons[i].offsetParent !== null) {  // Check if visible
                    console.log("Clicking accept button:", acceptButtons[i]);
                    acceptButtons[i].click();
                    return true;
                }
            }
            
            // If we reach here, try to hide the popup elements
            var elements = document.querySelectorAll('#didomi-popup, .didomi-popup-backdrop, .didomi-notice-popup');
            var removed = false;
            for (var j = 0; j < elements.length; j++) {
                elements[j].style.display = 'none';
                console.log("Hid Didomi element");
                removed = true;
            }
            
            return removed;
        } catch (e) {
            console.error("Error in Didomi consent handling:", e);
            return false;
        }
        """
        
        result = driver.execute_script(didomi_script)
        if result:
            logging.info("Successfully handled Didomi consent via JavaScript")
            time.sleep(1)  # Allow time for changes to take effect
            return True
        return False
    except Exception as e:
        logging.warning(f"Error in JavaScript Didomi consent handling: {str(e)}")
        return False

def extract_regex_data(html_source):
    """
    Extract property data using regex patterns for faster processing
    """
    extracted_data = {}
    
    # Extract data using regex patterns
    for field, patterns in REGEX_PATTERNS.items():
        for pattern in patterns:
            match = pattern.search(html_source)
            if match:
                value = match.group(1).strip()
                # Clean the value based on field type
                if field in ['living_area', 'rooms']:
                    value = clean_numerical_value(value, 'area' if field == 'living_area' else 'number')
                elif field == 'price':
                    value = clean_numerical_value(value, 'price')
                elif field == 'build_year':
                    value = clean_numerical_value(value, 'year')
                
                extracted_data[field] = value
                break
    
    # Add more specialized patterns for specific sites
    try:
        # Try to extract prices from multiple formats
        price_matches = re.findall(r'(?:kr\.?|DKK)\s*([\d.,]+)', html_source, re.IGNORECASE)
        if price_matches:
            extracted_data['price'] = clean_numerical_value(price_matches[0], 'price')
        
        # Try to extract living area in square meters
        area_matches = re.findall(r'(\d+)\s*(?:m²|kvm)', html_source)
        if area_matches and 'living_area' not in extracted_data:
            extracted_data['living_area'] = area_matches[0]
        
        # Try to find property type in the HTML
        property_types = ['Villa', 'Lejlighed', 'Rækkehus', 'Ejerlejlighed', 'Fritidshus', 'Andelsbolig']
        for prop_type in property_types:
            if prop_type in html_source:
                extracted_data['property_type'] = prop_type
                break
        
        # Look for energy label with a specific format (A-G)
        energy_match = re.search(r'[Ee]nergimærke:?\s*([A-G][+\d]*)', html_source)
        if energy_match:
            extracted_data['energy_label'] = energy_match.group(1)
    except Exception as e:
        logging.warning(f"Error in additional regex extraction: {e}")
        
    return extracted_data

def fetch_property_data(listing_url, header, site_name='unknown', wait_time_seconds=2, retries=3, params_info={}):
    """
    Fetch property data from a given URL.
    
    Args:
        listing_url: URL of the property listing
        header: Header to use for the request
        site_name: Name of the site (for attribution)
        wait_time_seconds: Time to wait between retries
        retries: Number of times to retry if the page fails to load
        params_info: Additional parameters to add to the property data
        
    Returns:
        Dictionary containing property data
    """
    if not listing_url.startswith('http'):
        original_url = listing_url
        listing_url = f"https://www.boligsiden.dk{listing_url}"
        logging.info(f"URL transformed (added protocol): {original_url} -> {listing_url}")
    
    options = webdriver.ChromeOptions()
    # Run in visible mode for debugging
    # options.add_argument('--headless')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-extensions')
    
    # Fix for None header - provide default User-Agent if header is None
    if header is None:
        user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.110 Safari/537.36'
    else:
        user_agent = header.get("User-Agent", 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.110 Safari/537.36')
    
    options.add_argument(f'user-agent={user_agent}')
    
    # Performance optimizations
    options.add_argument('--disable-gpu')
    options.add_argument('--disable-software-rasterizer')
    options.add_argument('--disable-webgl')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-browser-side-navigation')
    options.add_argument('--disable-infobars')
    options.add_argument('--disable-extensions')
    options.add_argument('--disable-notifications')
    options.add_argument('--disable-popup-blocking')
    options.add_argument('--blink-settings=imagesEnabled=false')  # Disable images for faster loading
    
    # Reduce logging noise
    options.add_argument('--log-level=3')  # Only show fatal errors
    options.add_experimental_option('excludeSwitches', ['enable-logging'])
    
    driver = None
    property_data = {
        'URL': listing_url,
        'Source_Site': site_name,
        'Scrape_Date': datetime.datetime.now().strftime('%Y-%m-%d'),
        'Address': 'N/A',
        'City': 'N/A',
        'Postal_Code': 'N/A',
        'Price': 'N/A',
        'Property_Type': 'N/A',
        'Bedrooms': 'N/A',
        'Living_Area': 'N/A',
        'Lot_Size': 'N/A',
        'Built_Year': 'N/A',
        'Rooms': 'N/A',
        'Bathrooms': 'N/A',
        'Toilets': 'N/A',
        'Floor_Count': 'N/A',
        'Basement_Size': 'N/A',
        'Energy_Label': 'N/A',
        'Weighted_Area': 'N/A',
        'Last_Remodel_Year': 'N/A'
    }
    
    # Add any additional parameters from params_info
    for key, value in params_info.items():
        if key not in property_data:
            property_data[key] = value
    
    try:
        driver = webdriver.Chrome(options=options)
        
        # Optimize wait time - reduce from current value
        wait_time_seconds = max(1, wait_time_seconds - 1)  # Ensure minimum of 1 second
        
        # Set an implicit wait - reduced from 10
        driver.implicitly_wait(5)
        
        # Wait for the page to load (reduced timeout from 15)
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.TAG_NAME, 'body'))
        )
        
        # Shorter fixed wait - reduced from 2 seconds
        time.sleep(1)
        
        # Find all "Se flere detaljer" buttons more efficiently
        detail_buttons_clicked = False
        
        try:
            # Use a more aggressive approach to find and click detail buttons
            logging.info("Using aggressive approach to find and click detail buttons")
            
            # First try clicking any 'Se flere detaljer' buttons directly
            detail_button_js = """
                // Find and click all possible detail buttons
                var clickedAny = false;
                var buttonSelectors = [
                    'button:contains("Se flere detaljer")', 
                    'button:contains("detaljer")', 
                    'button:contains("Vis mere")',
                    'button.showMore', 
                    'button[class*="details"]', 
                    'button[class*="expand"]'
                ];
                
                // Simulate jQuery-like :contains selector since it's not standard
                function contains(selector, text) {
                    var elements = document.querySelectorAll(selector);
                    return Array.prototype.filter.call(elements, function(element) {
                        return element.textContent.indexOf(text) > -1;
                    });
                }
                
                // Find all buttons with the text "Se flere detaljer"
                var detailButtons = contains('button', 'Se flere detaljer');
                detailButtons = detailButtons.concat(contains('button', 'detaljer'));
                detailButtons = detailButtons.concat(contains('button', 'Vis mere'));
                
                // Also find buttons by class
                document.querySelectorAll('button.showMore, button[class*="details"], button[class*="expand"]').forEach(function(btn) {
                    if (!detailButtons.includes(btn)) {
                        detailButtons.push(btn);
                    }
                });
                
                console.log("Found " + detailButtons.length + " potential detail buttons");
                
                // Click all buttons
                detailButtons.forEach(function(btn) {
                    try {
                        console.log("Clicking button: " + btn.textContent);
                        btn.click();
                        clickedAny = true;
                    } catch(e) {
                        console.log("Failed to click button: " + e);
                    }
                });
                
                return clickedAny;
            """
            
            # Attempt to click buttons with JavaScript
            buttons_clicked = driver.execute_script(detail_button_js)
            if buttons_clicked:
                logging.info("Successfully clicked detail buttons with JavaScript")
                time.sleep(2)  # Allow time for content to expand
            
            # Now use enhanced DOM manipulation script to force visibility of all elements
            logging.info("Using enhanced DOM manipulation to reveal all hidden details")
            
            # Execute DOM manipulation script to reveal all hidden elements
            driver.execute_script("""
                // Helper function to make an element and all its children visible
                function makeVisible(el) {
                    if (!el) return;
                    
                    // Make the element itself visible
                    el.style.display = 'block';
                    el.style.visibility = 'visible';
                    el.style.maxHeight = 'none';
                    el.style.height = 'auto';
                    el.style.opacity = '1';
                    el.style.overflow = 'visible';
                    
                    // Remove classes that might hide it
                    el.classList.remove('hidden', 'collapsed', 'folded', 'hide');
                    el.classList.add('expanded', 'visible', 'details-expanded', 'show');
                    
                    // Set attributes that control visibility
                    if (el.hasAttribute('aria-hidden')) {
                        el.setAttribute('aria-hidden', 'false');
                    }
                    if (el.hasAttribute('aria-expanded')) {
                        el.setAttribute('aria-expanded', 'true');
                    }
                    
                    // Make all children visible too
                    Array.from(el.children).forEach(makeVisible);
                }
                
                // Process all elements that might contain details
                var allDetailSelectors = [
                    // Direct detail containers
                    'div[class*="details"], div[class*="property-detail"], div[id*="details"]',
                    'div[class*="collapse"], div[class*="hidden"], div[class*="fold"]',
                    'section[class*="detail"], div[class*="more"], div[class*="expandable"]',
                    '.property-details, .facts, .property-info, .specifications',
                    'div[id*="facts"], div[id*="info"], div[id*="specifications"]',
                    
                    // Common containers for property information
                    '.ejendomsoplysninger, .boligspecifikationer, .facts-table',
                    'article.property, section.property, div.property-card',
                    'div[class*="property"], div[class*="house"], div[class*="estate"]',
                    
                    // Always check these common containers that might have hidden content
                    'div.container, section, article, main, div.content',
                    'div[role="tabpanel"], div[id*="panel"], div[aria-hidden="true"]',
                    'div[class*="accordion"], div[class*="tab-content"]',
                    'div.row, div.grid, div.flex, div.card'
                ];
                
                var elementsProcessed = 0;
                
                // First, click all buttons that might reveal content
                document.querySelectorAll('button, a[role="button"], div[role="button"], span[role="button"]').forEach(function(btn) {
                    try {
                        // Click any button that might expand content
                        var text = (btn.textContent || '').toLowerCase();
                        if (text.includes('detaljer') || text.includes('details') || 
                            text.includes('mere') || text.includes('more') || 
                            text.includes('vis') || text.includes('show') || 
                            text.includes('oplysninger') || text.includes('information') ||
                            text.includes('data') || text.includes('fakta') ||
                            text.includes('fold') || text.includes('expand')) {
                            
                            console.log("Auto-clicking button:", btn.textContent);
                            btn.click();
                        }
                    } catch (e) {
                        // Ignore click errors and continue
                    }
                });
                
                // Process all potential detail elements
                allDetailSelectors.forEach(function(selector) {
                    try {
                        document.querySelectorAll(selector).forEach(function(el) {
                            makeVisible(el);
                            elementsProcessed++;
                        });
                    } catch (e) {
                        console.error("Error processing selector " + selector + ": " + e);
                    }
                });
                
                // Try to expand any React/Angular/Vue controlled elements
                document.querySelectorAll('[data-expanded="false"], [data-collapse="true"], [data-show="false"]').forEach(function(el) {
                    el.setAttribute('data-expanded', 'true');
                    el.setAttribute('data-collapse', 'false');
                    el.setAttribute('data-show', 'true');
                    makeVisible(el);
                    elementsProcessed++;
                });
                
                console.log("Processed " + elementsProcessed + " elements");
                
                // Force all detail sections to be visible regardless of their original state
                var sectionsFound = document.querySelectorAll('*').length;
                return sectionsFound;
            """)
            
            # Wait a little longer for DOM changes to take effect
            time.sleep(2)
            
            # Check if details are visible now (use any element that might be part of details)
            expanded_sections = driver.find_elements(By.XPATH, "//div[contains(@class, 'expanded') or contains(@class, 'details') or contains(@class, 'facts') or contains(@class, 'property')]")
            if expanded_sections:
                logging.info(f"Successfully found {len(expanded_sections)} potential detail sections")
                detail_buttons_clicked = True
            else:
                # Try one more direct approach - find content by common property labels
                property_labels = driver.find_elements(By.XPATH, 
                    "//div[contains(text(), 'Boligareal') or contains(text(), 'Byggeår') or " +
                    "contains(text(), 'Værelser') or contains(text(), 'Grundareal') or " + 
                    "contains(text(), 'Energimærke')]")
                
                if property_labels:
                    logging.info(f"Found {len(property_labels)} property labels directly")
                    detail_buttons_clicked = True
                else:
                    logging.info("No detail sections found after DOM manipulation, continuing anyway")
                    
            # Take a screenshot for debugging
            try:
                screenshot_dir = "debug_screenshots"
                os.makedirs(screenshot_dir, exist_ok=True)
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                screenshot_path = f"{screenshot_dir}/property_screen_{timestamp}.png"
                driver.save_screenshot(screenshot_path)
                logging.info(f"Screenshot saved to {screenshot_path}")
                
                # Also save the HTML for debugging
                html_dir = "debug_html"
                os.makedirs(html_dir, exist_ok=True)
                html_path = f"{html_dir}/property_html_{timestamp}.html"
                with open(html_path, 'w', encoding='utf-8') as f:
                    f.write(driver.page_source)
                logging.info(f"HTML saved to {html_path}")
            except Exception as e:
                logging.warning(f"Failed to save debug files: {e}")
                
        except Exception as e:
            logging.warning(f"Error during DOM manipulation: {e}")
        
        # First, try to handle Didomi consent with direct JavaScript approach
        handle_didomi_consent(driver)
        
        # Handle cookie consent popups more aggressively
        try:
            # First check for Didomi specific popup which is blocking clicks
            didomi_popup = driver.find_elements(By.XPATH, "//div[@id='didomi-popup']")
            if didomi_popup and didomi_popup[0].is_displayed():
                logging.info("Found Didomi cookie consent popup, attempting to accept...")
                
                # Try multiple approaches to click accept
                accept_selectors = [
                    "//button[contains(@id, 'accept') or contains(@id, 'agree')]",
                    "//button[contains(., 'Accept') or contains(., 'Accepter') or contains(., 'Tillad')]",
                    "//button[contains(@class, 'didomi-button-highlight') or contains(@class, 'didomi-button-accept')]",
                    "//div[@id='didomi-popup']//button",
                    "//button[@id='didomi-notice-agree-button']",
                    "//button[contains(@class, 'didomi-consent-button')]"
                ]
                
                for selector in accept_selectors:
                    try:
                        buttons = driver.find_elements(By.XPATH, selector)
                        for button in buttons:
                            if button.is_displayed():
                                logging.info(f"Clicking Didomi consent button: {button.text}")
                                driver.execute_script("arguments[0].click();", button)
                                time.sleep(1)
                                if not (driver.find_elements(By.XPATH, "//div[@id='didomi-popup']") and 
                                       driver.find_elements(By.XPATH, "//div[@id='didomi-popup']")[0].is_displayed()):
                                    logging.info("Successfully closed Didomi popup")
                                    break
                    except Exception as e:
                        logging.warning(f"Error clicking Didomi button with selector {selector}: {str(e)}")
                    continue
        
            # Check for any other consent banners
            consent_buttons = driver.find_elements(By.XPATH, "//button[contains(text(), 'Accept') or contains(text(), 'Accepter') or contains(text(), 'OK') or contains(text(), 'Ja') or contains(@id, 'consent') or contains(@class, 'consent')]")
            if consent_buttons:
                for button in consent_buttons:
                    if button.is_displayed():
                        try:
                            logging.info(f"Clicking consent button: {button.text}")
                            button.click()
                        except:
                            # Use JavaScript as fallback
                            driver.execute_script("arguments[0].click();", button)
                        time.sleep(0.5)
        except Exception as e:
            logging.warning(f"Failed to handle consent banner: {str(e)}")
        
        # Try to detect if page has finished loading key content
        try:
            # Wait for price element which is usually one of the last to load
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.XPATH, 
                    "//div[contains(@class, 'price')] | //span[contains(@class, 'price')] | //h2[contains(text(), 'kr')] | //h3[contains(text(), 'kr')] | //div[contains(text(), 'Villa')] | //div[contains(text(), 'Lejlighed')]"))
            )
        except:
            # If we can't find price, wait briefly and continue anyway
            pass
        
        # Get the page source and parse with BeautifulSoup for static content
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        
        # Extract data using regular expressions first for speed
        html_source = driver.page_source
        regex_details = extract_regex_data(html_source)
        
        # Extract property details from the page using the more thorough method
        extracted_details = extract_property_details(soup)
        
        # Initialize details dictionary to combine all sources
        details = {}
        
        # Add regex-based details as a baseline
        details.update(regex_details)
        
        # Add extracted details (will override regex details if they exist)
        details.update(extracted_details)
        
        # Map the extracted details to our standard property data keys
        detail_mapping = {
            'living_area': 'Living_Area',
            'area': 'Living_Area',
            'plot_area': 'Lot_Size',
            'rooms': 'Rooms',
            'build_year': 'Built_Year',
            'energy_label': 'Energy_Label',
            'price': 'Price',
            'owner_cost': 'Monthly_Cost',
            'case_number': 'Reference',
            'property_type': 'Property_Type',
            'floor': 'Floor_Count',
            'basement': 'Basement_Size',
            'days_on_market': 'Days_On_Market',
            'bathrooms': 'Bathrooms',
            'toilets': 'Toilets',
            'weighted_area': 'Weighted_Area',
            'last_remodel_year': 'Last_Remodel_Year'
        }
        
        # Map details to property_data using our mapping
        for detail_key, prop_key in detail_mapping.items():
            if detail_key in details and details[detail_key]:
                property_data[prop_key] = details[detail_key]
                
        logging.info(f"Extracted and mapped property details: {details}")
        
        # For debugging, keep the browser open for a while before returning
        if not options.arguments or '--headless' not in options.arguments:
            logging.info("Browser window will stay open for 30 seconds for inspection...")
            time.sleep(30)
            
        return property_data
    
    except Exception as e:
        logging.error(f"Error in fetch_property_data: {str(e)}")
        return property_data
    finally:
        if driver:
            driver.quit()

def process_property(property_row, index, total, start_time=None):
    """Process a single property and extract its details"""
    property_id = property_row.get('Property ID', 'unknown')
    logging.info(f"Processing property {index}/{total} ({index/total*100:.1f}%)")
    logging.info(f"ID: {property_id}")
    
    # Calculate and display remaining time based on average processing time
    if start_time and index > 1:
        elapsed_time = time.time() - start_time
        avg_time_per_property = elapsed_time / (index - 1)
        remaining_properties = total - index
        remaining_time = remaining_properties * avg_time_per_property / 60  # minutes
        logging.info(f"Estimated time remaining: {remaining_time:.1f} minutes")
    
    link = property_row.get('Link', '')
    if not link:
        logging.warning(f"No link found for property {property_id}, skipping")
        return None
    
    # Transform relative URLs to absolute URLs
    if link.startswith('/'):
        link = f"https://www.boligsiden.dk{link}"
        logging.info(f"URL transformed from relative: {property_row.get('Link')} -> {link}")
    
    try:
        # Use a separate header for each property to avoid detection
        header = {
            "User-Agent": f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{random.randint(80, 110)}.0.{random.randint(1000, 9999)}.{random.randint(10, 999)} Safari/537.36"
        }
        
        # Fetch property data with reduced wait time (1-2 seconds)
        property_data = fetch_property_data(
            link, 
            header, 
            site_name='boligsiden', 
            wait_time_seconds=1, 
            retries=2,
            params_info={'Property_ID': property_id}
        )
        
        return property_data
    except Exception as e:
        logging.error(f"Error processing property {property_id}: {str(e)}")
        return None

def main(sample_size=None):
    """Main function to process property links."""
    
    # Load list of property links from CSV
    try:
        all_properties = []
        with open('data/scraped_properties.csv', 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                all_properties.append(row)
        
        logging.info(f"Loaded {len(all_properties)} properties from CSV")
        
        # Take a sample if requested
        if sample_size:
            if sample_size < len(all_properties):
                all_properties = random.sample(all_properties, sample_size)
                logging.info(f"Taking a random sample of {sample_size} links from {len(all_properties)} total links")
            else:
                logging.info(f"Sample size {sample_size} is larger than available properties ({len(all_properties)}), using all properties")
        
        # For debugging, just process one property in visible mode without threading
        if sample_size == 1:
            logging.info("Running in debug mode with a single property")
            # Get the first property in the sample
            property_row = all_properties[0]
            property_id = property_row.get('Property ID', 'unknown')
            link = property_row.get('Link', '')
            
            if link:
                # Transform relative URLs to absolute URLs
                if link.startswith('/'):
                    link = f"https://www.boligsiden.dk{link}"
                    logging.info(f"Debug URL: {link}")
                
                header = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.110 Safari/537.36"
                }
                
                # Process this single property with more time for debugging
                logging.info(f"Processing single property for debugging: {property_id}")
                result = fetch_property_data(
                    link, 
                    header, 
                    site_name='boligsiden',
                    wait_time_seconds=5,  # longer wait time for debugging
                    retries=1,
                    params_info={'Property_ID': property_id}
                )
                
                if result:
                    logging.info(f"Debug result: {result}")
                    output_file = 'data/property_details_debug.csv'
                    with open(output_file, 'w', encoding='utf-8', newline='') as f:
                        writer = csv.DictWriter(f, fieldnames=sorted(result.keys()))
                        writer.writeheader()
                        writer.writerow(result)
                    
                    logging.info(f"Saved debug result to {output_file}")
                
                return
        
        # Start timer for regular processing
        start_time = time.time()
        
        # Initialize results list
        all_results = []
        
        # Use ThreadPoolExecutor instead of ProcessPoolExecutor for better sharing of resources
        max_workers = min(4, multiprocessing.cpu_count())
        logging.info(f"Using {max_workers} concurrent workers")
        
        # Process properties in parallel
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all properties for processing
            futures = [
                executor.submit(process_property, prop, i+1, len(all_properties), start_time) 
                for i, prop in enumerate(all_properties)
            ]
            
            # Process results as they complete
            for future in concurrent.futures.as_completed(futures):
                try:
                    result = future.result()
                    if result:
                        all_results.append(result)
                except Exception as e:
                    logging.error(f"Error processing property in parallel: {str(e)}")
        
        # Summarize results
        total_time = time.time() - start_time
        logging.info(f"Processed {len(all_results)} properties in {total_time/60:.2f} minutes")
        
        # Handle the case where no results were collected to avoid division by zero
        if all_results:
            logging.info(f"Average time per property: {total_time/len(all_results):.2f} seconds")
        else:
            logging.warning("No properties were successfully processed")
        
        # Save results to CSV
        if all_results:
            output_file = 'data/property_details.csv'
            logging.info(f"Saving {len(all_results)} property details to {output_file}")
            
            # Get all unique keys for the CSV header
            all_keys = set()
            for result in all_results:
                all_keys.update(result.keys())
            
            with open(output_file, 'w', encoding='utf-8', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=sorted(all_keys))
                writer.writeheader()
                writer.writerows(all_results)
            
            logging.info(f"Data successfully saved to {output_file}")
        else:
            logging.warning("No property details were collected")
            
    except Exception as e:
        logging.error(f"Error in main function: {str(e)}")
        raise

def get_user_choice():
    print("\nPlease select a run mode:")
    print("1. Small sample (5 properties, ~3 minutes)")
    print("2. Medium sample (50 properties, ~20 minutes)")
    print("3. Full dataset (552 properties, ~3.5 hours)")
    print("4. Debug mode (1 property, visible browser)")
    
    while True:
        try:
            choice = input("Enter your choice (1-4): ")
            
            if choice == '1':
                print("\nStarting sample run with 5 properties...")
                return 5
            elif choice == '2':
                print("\nStarting medium run with 50 properties...")
                return 50
            elif choice == '3':
                print("\nStarting full run with all properties...")
                return None  # None means process all properties
            elif choice == '4':
                print("\nStarting debug mode with 1 property and visible browser...")
                return 1
            else:
                print("Invalid choice. Please enter 1, 2, 3, or 4.")
        except ValueError:
            print("Invalid input. Please enter a number between 1 and 4.")

def clean_numerical_value(value, value_type='number'):
    """
    Clean and format numerical values from scraped text.
    
    Args:
        value: The string value to clean
        value_type: 'number', 'price', 'area', or 'year'
        
    Returns:
        A cleaned string value
    """
    if not value or value == 'N/A':
        return value
        
    # Handle various non-breaking spaces and whitespace
    value = value.replace('\xa0', ' ').strip()
    
    if value_type == 'price':
        # Remove currency symbols and separators
        value = re.sub(r'[^\d]', '', value)
    elif value_type == 'area':
        # Remove everything except digits and decimal separator
        value = re.sub(r'[^\d.,]', '', value)
        # Standardize decimal separator to dot
        value = value.replace(',', '.')
    elif value_type == 'year':
        # Extract 4-digit year if present
        year_match = re.search(r'\d{4}', value)
        if year_match:
            value = year_match.group(0)
        else:
            # Remove non-digits if no 4-digit year found
            value = re.sub(r'[^\d]', '', value)
    else:  # Generic number
        # Remove everything except digits and decimal separator
        value = re.sub(r'[^\d.,]', '', value)
        # Standardize decimal separator to dot
        value = value.replace(',', '.')
        
    return value

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