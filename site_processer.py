import logging
from bs4 import BeautifulSoup
import os
import time
import random
import re
import datetime
from selenium.webdriver.common.by import By
from selenium import webdriver
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
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

def extract_property_details(soup):
    """
    Extract property details from the soup object.
    Returns a dictionary of property details.
    """
    processed_details = {}
    
    # Try multiple selectors for detail sections
    detail_sections = []
    for selector in [
        ".property-details", ".property-specs", ".property-info", 
        "[class*='details']", "[class*='specs']", "[class*='info']",
        "[id*='details']", "[id*='specifications']", "[id*='info']",
        "section", "article", ".facts-table", ".estateFacts", 
        # Add new selectors based on observed HTML structure
        "div.scroll-mt-0", "div[id='oversigt']", 
        # Replace Tailwind-style selectors with more compatible alternatives
        "div.pt-22", ".pt-22", 
        "div.flex", "div.space-y-2",
        "div.whitespace-nowrap"
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
            "div.row", "div.flex", 
            # Add new selectors based on observed HTML structure
            "div.inline-flex", "div.space-y-2", "div.justify-between",
            "div.mt-4", "div.mb-6", "div.whitespace-nowrap",
            "div[class*='tag']", "span[class*='text']"
        ]:
            rows = section.select(row_selector)
            if rows:
                detail_rows.extend(rows)
                logging.info(f"Found {len(rows)} detail rows with selector: {row_selector}")
    
    # Process each detail row
    for row in detail_rows:
        try:
            # Try to find label and value divs in various formats
            label_div = None
            value_div = None
            
            # Method 1: Common class names for label and value
            for label_selector in [".label", ".key", ".name", "dt", "th", "[class*='label']", "[class*='key']", "label", "div.text-xs"]:
                if not label_div:
                    label_div = row.select_one(label_selector)
            
            for value_selector in [".value", ".val", ".data", "dd", "td", "[class*='value']", "[class*='val']", "div.text-sm", "div.text-blue-900", "span.text-blue-900"]:
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
            
            # Method 4: Check for SVG icons with adjacent text
            if not label_div or not value_div:
                # If there's an SVG and text/span element, the text might be a property value
                if row.find("svg") and (row.find("span") or row.get_text().strip()):
                    # The text content after the SVG could be a property value
                    svg = row.find("svg")
                    if svg and svg.next_sibling:
                        if isinstance(svg.next_sibling, str) and svg.next_sibling.strip():
                            # SVG followed by text directly
                            value_div = svg.next_sibling
                        elif svg.next_sibling.name == "span":
                            # SVG followed by span
                            value_div = svg.next_sibling
                            
                    # Try to determine the property type from the SVG
                    if svg and svg.get('class'):
                        svg_classes = ' '.join(svg.get('class'))
                        if 'floor' in svg_classes or 'home' in svg_classes:
                            label_div = "living_area"
                        elif 'bed' in svg_classes or 'bedroom' in svg_classes:
                            label_div = "rooms"
                        elif 'bath' in svg_classes or 'toilet' in svg_classes:
                            label_div = "bathrooms"
            
            # Method 5: For div.inline-flex elements, check for property-specific patterns
            if not label_div or not value_div:
                row_text = row.get_text().strip()
                if 'm²' in row_text:
                    label_div = "living_area"
                    # Extract the number before m²
                    match = re.search(r'(\d+)\s*m²', row_text)
                    if match:
                        value_div = match.group(1)
                elif 'værelser' in row_text:
                    label_div = "rooms"
                    # Extract the number before værelser
                    match = re.search(r'(\d+)\s*værelser', row_text)
                    if match:
                        value_div = match.group(1)
                elif 'toilet' in row_text:
                    label_div = "toilets"
                    # Extract the number before toilet
                    match = re.search(r'(\d+)\s*toilet', row_text)
                    if match:
                        value_div = match.group(1)
                
            # Method 6: Last resort - use first and second divs or spans
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
                # Handle the case where label_div is a string (from our detection logic)
                if isinstance(label_div, str):
                    label = label_div
                else:
                    label = label_div.get_text().strip().lower()
                
                # Handle the case where value_div is a string (from our detection logic)
                if isinstance(value_div, str):
                    value = value_div.strip()
                else:
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
                    'liggetid': 'days_on_market',
                    'toilet': 'toilets',
                    'badeværelse': 'bathrooms',
                    'varme': 'heating_type',
                    'tag': 'roof_type',
                    'ydervæg': 'wall_material',
                    'ydermur': 'wall_material'
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
            ".energy-rating, .energy-class, .energy-certificate",
            # Add new selectors for energy labels
            "svg[class*='w-7'][class*='h-7']", "div.cursor-pointer svg", 
            "div[data-tooltipped] svg", "div.w-10.h-10 svg"
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
                    # Check for SVG title element that might contain energy rating
                    elif element.name == 'svg':
                        title_elem = element.find('title')
                        if title_elem:
                            title_text = title_elem.get_text()
                            if 'energimærke' in title_text.lower() or 'energy' in title_text.lower():
                                energy_match = re.search(r'\b([A-G][+\-]?)\b', title_text, re.IGNORECASE)
                                if energy_match:
                                    processed_details['energy_label'] = energy_match.group(1).upper()
                                    break
                                elif 'intet' in title_text.lower() or 'no' in title_text.lower():
                                    # "Intet energimærke" means "No energy label"
                                    processed_details['energy_label'] = "N/A"
                                    break
                    # Check if it's an element with energy class as text content
                    else:
                        text = element.get_text().strip()
                        energy_match = re.search(r'\b([A-G][+\-]?)\b', text, re.IGNORECASE)
                        if energy_match:
                            processed_details['energy_label'] = energy_match.group(1).upper()
                            break
    
    # Try to extract price specifically from the page
    if 'price' not in processed_details:
        price_selectors = [
            "h2.text-blue-900", 
            "div.text-blue-900.text-28px", 
            "h2.text-28px",
            ".text-blue-900.font-semibold"
        ]
        
        for selector in price_selectors:
            price_elements = soup.select(selector)
            for element in price_elements:
                price_text = element.get_text().strip()
                if 'kr' in price_text or '.' in price_text:
                    # Looks like a price
                    price_match = re.search(r'([\d.,]+)', price_text)
                    if price_match:
                        price = price_match.group(1).replace('.', '').replace(',', '')
                        processed_details['price'] = price
                        break
    
    # Extract property type if not found yet
    if 'property_type' not in processed_details:
        type_selectors = [
            "span.text-gray-700", 
            "p.text-xs span.text-gray-700"
        ]
        
        for selector in type_selectors:
            type_elements = soup.select(selector)
            if type_elements:
                property_type = type_elements[0].get_text().strip()
                processed_details['property_type'] = property_type
                break
    
    # Extract rooms from specific tags if not found yet
    if 'rooms' not in processed_details:
        rooms_selectors = [
            "div.inline-flex span.text-blue-900",
            "div[class*='tag'] span.text-blue-900"
        ]
        
        for selector in rooms_selectors:
            room_elements = soup.select(selector)
            for element in room_elements:
                text = element.get_text().strip()
                if 'værelser' in text:
                    rooms_match = re.search(r'(\d+)', text)
                    if rooms_match:
                        processed_details['rooms'] = rooms_match.group(1)
                        break
    
    # Extract living area from specific tags if not found yet
    if 'living_area' not in processed_details:
        area_selectors = [
            "div.inline-flex span.text-blue-900",
            "div[class*='tag'] span.text-blue-900",
            "span[class*='whitespace-nowrap']"
        ]
        
        for selector in area_selectors:
            area_elements = soup.select(selector)
            for element in area_elements:
                text = element.get_text().strip()
                if 'm²' in text:
                    area_match = re.search(r'(\d+)', text)
                    if area_match:
                        processed_details['living_area'] = area_match.group(1)
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

def extract_modal_data(driver):
    """
    Extracts property data from the modal dialog that appears after clicking 'Se flere detaljer'.
    """
    try:
        # Find and click the "Se flere detaljer" button
        try:
            # Try multiple selectors to find the button
            detail_button_selectors = [
                "//button[contains(., 'Se flere detaljer')]",
                "//button[contains(., 'detaljer')]",
                "//span[contains(., 'Se flere detaljer')]/parent::button",
                "//button[contains(@class, 'text-blue-900')][.//span[contains(text(), 'Se flere detaljer')]]",
                # Adding new selectors based on the provided HTML
                "//button[contains(@class, 'flex justify-center items-center')][.//span[contains(text(), 'Se flere detaljer')]]",
                "//div[contains(@class, 'sm:hidden')]//button[.//span[contains(text(), 'Se flere detaljer')]]",
                "//div[contains(@class, 'hidden sm:flex')]//button[.//span[contains(text(), 'Se flere detaljer')]]"
            ]
            
            button_found = False
            for selector in detail_button_selectors:
                buttons = driver.find_elements(By.XPATH, selector)
                for button in buttons:
                    if button.is_displayed():
                        logging.info("Found 'Se flere detaljer' button, clicking...")
                        driver.execute_script("arguments[0].click();", button)
                        button_found = True
                        break
                if button_found:
                    break
            
            if not button_found:
                logging.warning("Could not find 'Se flere detaljer' button")
                return {}
                
            # Wait for the modal to appear - updated selectors
            WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.XPATH, "//div[@id='modal-root'] | //div[contains(@class, 'modal')] | //div[contains(@role, 'dialog')]"))
            )
            logging.info("Modal dialog appeared successfully")
        except Exception as e:
            logging.warning(f"Error clicking 'Se flere detaljer' button: {e}")
            return {}
        
        # Wait a moment for modal to be fully rendered
        time.sleep(1)
        
        # Initialize the result dictionary
        modal_data = {}
        property_id = None
        
        # Extract the property ID from the URL
        try:
            current_url = driver.current_url
            url_parts = current_url.split('/')
            if len(url_parts) > 0:
                last_part = url_parts[-1]
                property_id = last_part
                modal_data['Property_ID'] = property_id
        except Exception as e:
            logging.warning(f"Error extracting property ID from URL: {e}")
        
        # Look for all the property detail rows in the modal - updated selectors to match new structure
        try:
            # Try multiple selectors for the modal content based on observed HTML
            modal_content_selectors = [
                "//div[@id='modal-root']//div[contains(@class, 'divide-y')]/div[contains(@class, 'flex')]",
                "//div[contains(@class, 'modal')]//div[contains(@class, 'divide-y')]/div",
                "//div[contains(@role, 'dialog')]//div[contains(@class, 'divide-y')]/div",
                "//div[contains(@role, 'dialog')]//div[contains(@class, 'grid')]/div",
                "//div[contains(@id, 'modal')]//tbody/tr",
                "//div[contains(@class, 'modal')]//div[contains(@class, 'flex justify-between')]"
            ]
            
            detail_rows = []
            for selector in modal_content_selectors:
                rows = driver.find_elements(By.XPATH, selector)
                if rows:
                    detail_rows = rows
                    break
            
            if detail_rows:
                logging.info(f"Found {len(detail_rows)} detail rows in modal")
                
                # Map Danish property terms to standardized English field names
                field_mapping = {
                    'Seneste ombygningsår': 'Last_Remodel_Year',
                    'Antal plan og etage': 'Floor_Count',
                    'Antal plan': 'Floor_Count',
                    'Etage': 'Floor_Count',
                    'Antal toiletter': 'Toilets',
                    'Toiletter': 'Toilets',
                    'Varmeinstallation': 'Heating_Type',
                    'Varme': 'Heating_Type',
                    'Ydervægge': 'Wall_Material',
                    'Ydermur': 'Wall_Material',
                    'Vægtet areal': 'Weighted_Area',
                    'Tagtype': 'Roof_Type',
                    'Tag': 'Roof_Type',
                    'Boligareal': 'Living_Area',
                    'Areal': 'Living_Area',
                    'Grundareal': 'Lot_Size',
                    'Grund': 'Lot_Size',
                    'Opførelsesår': 'Built_Year',
                    'Byggeår': 'Built_Year',
                    'Opført': 'Built_Year',
                    'Antal værelser': 'Rooms',
                    'Værelser': 'Rooms',
                    'Antal badeværelser': 'Bathrooms',
                    'Badeværelser': 'Bathrooms',
                    'Kælderareal': 'Basement_Size',
                    'Kælder': 'Basement_Size',
                    'Energimærke': 'Energy_Label',
                    'Boligtype': 'Property_Type',
                    'Ejendomstype': 'Property_Type',
                    'Type': 'Property_Type'
                }
                
                # Process each detail row
                for row in detail_rows:
                    try:
                        # Skip the last row which contains the buttons
                        if "Luk" in row.text or "Ok" in row.text or "Lukk" in row.text:
                            continue
                            
                        # Try different approaches to extract label and value
                        row_text = row.text.strip()
                        if not row_text:
                            continue
                            
                        # Try direct XPath to find label and value
                        labels = row.find_elements(By.XPATH, ".//div[1] | .//th | .//dt")
                        values = row.find_elements(By.XPATH, ".//div[2] | .//td | .//dd")
                        
                        # If XPath didn't work, try parsing the text
                        if (not labels or not values) and ":" in row_text:
                            parts = row_text.split(":", 1)
                            label = parts[0].strip()
                            value = parts[1].strip() if len(parts) > 1 else ""
                        elif labels and values:
                            label = labels[0].text.strip()
                            value = values[0].text.strip()
                        else:
                            # For cases where the structure is different
                            # Try to identify by common patterns
                            for known_label in field_mapping.keys():
                                if known_label.lower() in row_text.lower():
                                    # Extract value after the known label
                                    label_pos = row_text.lower().find(known_label.lower())
                                    label = known_label
                                    value = row_text[label_pos + len(known_label):].strip()
                                    if value.startswith(":"):
                                        value = value[1:].strip()
                                    break
                            else:
                                # If we can't identify the row format, log and continue
                                logging.debug(f"Could not parse row text: {row_text}")
                                continue
                            
                        # Map the Danish field name to English
                        field_name = None
                        for danish_term, english_field in field_mapping.items():
                            if danish_term.lower() in label.lower():
                                field_name = english_field
                                break
                                
                        if field_name:
                            # Clean the value - extract numbers for numerical fields
                            if field_name in ['Living_Area', 'Lot_Size', 'Weighted_Area', 'Basement_Size']:
                                # Extract number from strings like "189.75 m²"
                                match = re.search(r'(\d+(?:[,.]\d+)?)', value)
                                if match:
                                    value = match.group(1).replace(',', '.')
                            elif field_name in ['Rooms', 'Floor_Count', 'Toilets', 'Bathrooms']:
                                # Extract number from strings like "2 plan" or just "2"
                                match = re.search(r'(\d+)', value)
                                if match:
                                    value = match.group(1)
                            
                            # Store the value in our result dictionary
                            modal_data[field_name] = value
                            logging.info(f"Extracted {field_name}: {value}")
                    except Exception as e:
                        logging.warning(f"Error processing detail row: {e}")
            else:
                logging.warning("No detail rows found in modal")
        except Exception as e:
            logging.warning(f"Error extracting details from modal: {e}")
            
        # Check for additional information in the main page
        try:
            # Extract property type - updated selectors for new structure
            property_type_selectors = [
                "//span[contains(@class, 'text-gray-700')][1]",
                "//p[contains(@class, 'text-xs')]/span[contains(@class, 'text-gray-700')]",
                "//div[contains(@class, 'text-xs')]//span[contains(@class, 'text-gray-700')]"
            ]
            
            for selector in property_type_selectors:
                property_type_elems = driver.find_elements(By.XPATH, selector)
                if property_type_elems:
                    property_type = property_type_elems[0].text.strip()
                    modal_data['Property_Type'] = property_type
                    logging.info(f"Extracted Property_Type: {property_type}")
                    break
                
            # Extract address - updated selectors for new structure
            address_selectors = [
                "//h1[contains(@class, 'text-blue-900')]//span[contains(@class, 'text-lg')]",
                "//h1[contains(@class, 'text-blue-900')]/span[1]",
                "//h1[contains(@class, 'space-y-1')]/span[1]"
            ]
            
            for selector in address_selectors:
                address_elems = driver.find_elements(By.XPATH, selector)
                if address_elems:
                    address = address_elems[0].text.strip()
                    modal_data['Address'] = address
                    logging.info(f"Extracted Address: {address}")
                    break
                
            # Extract postal code and city - updated selectors for new structure
            city_postal_selectors = [
                "//h1[contains(@class, 'text-blue-900')]//span[contains(@class, 'block')]",
                "//h1[contains(@class, 'space-y-1')]/span[2]"
            ]
            
            for selector in city_postal_selectors:
                city_postal_elems = driver.find_elements(By.XPATH, selector)
                if city_postal_elems:
                    city_postal = city_postal_elems[0].text.strip()
                    # Extract postal code and city separately
                    postal_match = re.search(r'(\d{4})\s+(.*)', city_postal)
                    if postal_match:
                        postal_code = postal_match.group(1)
                        city = postal_match.group(2)
                        modal_data['Postal_Code'] = postal_code
                        modal_data['City'] = city
                        logging.info(f"Extracted Postal_Code: {postal_code}, City: {city}")
                    else:
                        modal_data['City'] = city_postal
                    break
            
            # Extract price - updated selectors for new structure
            price_selectors = [
                "//h2[contains(@class, 'text-blue-900')]",
                "//div[contains(@class, 'text-blue-900')][contains(@class, 'text-28px')]",
                "//h2[contains(@class, 'text-28px')]"
            ]
            
            for selector in price_selectors:
                price_elems = driver.find_elements(By.XPATH, selector)
                if price_elems:
                    price_text = price_elems[0].text.strip()
                    # Clean price value
                    price_match = re.search(r'([\d.,]+)', price_text)
                    if price_match:
                        price = price_match.group(1).replace('.', '').replace(',', '')
                        modal_data['Price'] = price
                        logging.info(f"Extracted Price: {price}")
                    break
                    
            # Extract living area from tags - updated selectors for new structure
            living_area_selectors = [
                "//span[contains(text(), 'm²')]",
                "//div[contains(@class, 'inline-flex')][contains(., 'm²')]//span[contains(@class, 'text-blue-900')]"
            ]
            
            for selector in living_area_selectors:
                living_area_elems = driver.find_elements(By.XPATH, selector)
                if living_area_elems:
                    for elem in living_area_elems:
                        living_area_text = elem.text.strip()
                        area_match = re.search(r'(\d+)', living_area_text)
                        if area_match and 'Living_Area' not in modal_data:
                            modal_data['Living_Area'] = area_match.group(1)
                            logging.info(f"Extracted Living_Area from tag: {area_match.group(1)}")
                            break
                    if 'Living_Area' in modal_data:
                        break
                    
            # Extract rooms - updated selectors for new structure
            rooms_selectors = [
                "//span[contains(text(), 'værelser')]",
                "//div[contains(@class, 'inline-flex')][contains(., 'værelser')]//span[contains(@class, 'text-blue-900')]"
            ]
            
            for selector in rooms_selectors:
                rooms_elems = driver.find_elements(By.XPATH, selector)
                if rooms_elems:
                    for elem in rooms_elems:
                        rooms_text = elem.text.strip()
                        rooms_match = re.search(r'(\d+)', rooms_text)
                        if rooms_match and 'Rooms' not in modal_data:
                            modal_data['Rooms'] = rooms_match.group(1)
                            logging.info(f"Extracted Rooms from tag: {rooms_match.group(1)}")
                            break
                    if 'Rooms' in modal_data:
                        break
        except Exception as e:
            logging.warning(f"Error extracting additional information: {e}")
            
        # Take a screenshot of the modal for debugging
        try:
            screenshot_dir = "debug_screenshots"
            os.makedirs(screenshot_dir, exist_ok=True)
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            screenshot_path = f"{screenshot_dir}/modal_{timestamp}.png"
            driver.save_screenshot(screenshot_path)
            logging.info(f"Modal screenshot saved to {screenshot_path}")
        except Exception as e:
            logging.warning(f"Failed to save modal screenshot: {e}")
            
        # Close the modal
        try:
            close_button_selectors = [
                "//button[contains(text(), 'Luk')]", 
                "//button[contains(text(), 'Ok')]", 
                "//button[contains(text(), 'Lukk')]",
                "//div[@id='modal-root']//button[contains(@class, 'float-right')]",
                "//div[contains(@role, 'dialog')]//button"
            ]
            
            for selector in close_button_selectors:
                close_buttons = driver.find_elements(By.XPATH, selector)
                for button in close_buttons:
                    if button.is_displayed():
                        driver.execute_script("arguments[0].click();", button)
                        logging.info("Closed modal dialog")
                        break
        except Exception as e:
            logging.warning(f"Error closing modal: {e}")
        
        return modal_data
    except Exception as e:
        logging.error(f"Error in extract_modal_data: {e}")
        logging.error("Stack trace:", exc_info=True)
        return {}

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
    # Validate URL before proceeding
    if not listing_url or not isinstance(listing_url, str) or listing_url.strip() == '':
        logging.error("Empty or invalid URL provided to fetch_property_data")
        return None
    
    if not listing_url.startswith('http'):
        original_url = listing_url
        listing_url = f"https://www.boligsiden.dk{listing_url if listing_url.startswith('/') else '/' + listing_url}"
        logging.info(f"URL transformed in fetch_property_data: '{original_url}' -> '{listing_url}'")
    
    # Log the final URL being used
    logging.info(f"Fetching data from URL: '{listing_url}'")
    
    options = webdriver.ChromeOptions()
    # Enable headless mode
    options.add_argument('--headless=new')
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
    
    # Basic performance optimizations - reducing the number to minimize complexity
    options.add_argument('--disable-gpu')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-extensions')
    options.add_argument('--blink-settings=imagesEnabled=true')  # Enable images for modal interaction
    
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
        
        # Log that we're opening the URL
        logging.info(f"Opening URL in Chrome: '{listing_url}'")
        
        # Navigate to the page
        driver.get(listing_url)
        
        # Set an implicit wait
        driver.implicitly_wait(5)
        
        # Check if we ended up on a data: URL, which indicates an issue
        current_url = driver.current_url
        if current_url.startswith('data:'):
            logging.error(f"Navigation failed - redirected to data: URL. Original URL: '{listing_url}'")
            return None
        
        # Wait for the page to load
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.TAG_NAME, 'body'))
        )
        
        # Short fixed wait
        time.sleep(wait_time_seconds)
        
        # Handle cookie consent (simplified version)
        try:
            # Try to accept cookie consent
            consent_buttons = driver.find_elements(By.XPATH, "//button[contains(text(), 'Accept') or contains(text(), 'Accepter') or contains(text(), 'OK') or contains(@id, 'accept')]")
            for button in consent_buttons:
                if button.is_displayed():
                    try:
                        logging.info(f"Clicking consent button: {button.text}")
                        driver.execute_script("arguments[0].click();", button)
                        time.sleep(1)
                    except Exception as e:
                        logging.warning(f"Failed to click consent button: {e}")
        except Exception as e:
            logging.warning(f"Error handling cookie consent: {e}")
        
        # First extract data from the modal dialog - this is the most reliable source
        modal_data = extract_modal_data(driver)
        
        if modal_data:
            logging.info(f"Successfully extracted data from modal dialog: {len(modal_data)} fields")
            # Update our property data with the modal data
            property_data.update(modal_data)
        else:
            logging.warning("No data extracted from modal dialog, falling back to page scraping")
        
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
        
        # Map details to property_data only for fields not already populated by modal data
        for detail_key, prop_key in detail_mapping.items():
            if detail_key in details and details[detail_key] and (prop_key not in property_data or property_data[prop_key] == 'N/A'):
                property_data[prop_key] = details[detail_key]
                
        logging.info(f"Extracted and mapped property details: {details}")
        
        # Extract property ID from URL if not already set
        if 'Property_ID' not in property_data or property_data['Property_ID'] == 'N/A':
            try:
                url_parts = listing_url.split('/')
                if len(url_parts) > 0:
                    last_part = url_parts[-1]
                    if last_part:
                        property_data['Property_ID'] = last_part
            except Exception as e:
                logging.warning(f"Error extracting property ID from URL: {e}")
            
        return property_data
    
    except Exception as e:
        logging.error(f"Error in fetch_property_data: {str(e)}")
        logging.error("Stack trace:", exc_info=True)
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
    
    # Get link and validate it
    link = property_row.get('Link', '')
    logging.info(f"Raw link from CSV: '{link}'")
    
    # Skip if link is empty or just whitespace
    if not link or link.strip() == '':
        logging.warning(f"No valid link found for property {property_id}, skipping")
        return None
    
    # Ensure proper URL formatting
    if not link.startswith('http'):
        if link.startswith('/'):
            link = f"https://www.boligsiden.dk{link}"
        else:
            link = f"https://www.boligsiden.dk/{link}"
        logging.info(f"URL transformed: '{property_row.get('Link')}' -> '{link}'")
    
    # Final validation check
    if not link.startswith('http'):
        logging.error(f"Invalid URL format after transformation: '{link}'")
        return None
    
    try:
        # Use a consistent header for all requests
        header = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.110 Safari/537.36"
        }
        
        # Add a small delay between requests
        time.sleep(2)
        
        # Fetch property data
        property_data = fetch_property_data(
            link, 
            header, 
            site_name='boligsiden', 
            wait_time_seconds=3,
            retries=2,
            params_info={'Property_ID': property_id}
        )
        
        if not property_data:
            logging.warning(f"No data extracted for property {property_id}")
            return None
            
        # Validate the extracted data
        required_fields = ['URL', 'Source_Site', 'Scrape_Date', 'Address', 'City', 'Postal_Code']
        missing_fields = [field for field in required_fields if field not in property_data]
        if missing_fields:
            logging.warning(f"Missing required fields for property {property_id}: {', '.join(missing_fields)}")
        
        return property_data
    except Exception as e:
        logging.error(f"Error processing property {property_id}: {str(e)}")
        logging.error("Stack trace:", exc_info=True)
        return None

def main(sample_size=None):
    """Main function to process property links."""
    try:
        # Load list of property links from CSV
        with open('data/scraped_properties.csv', 'r', encoding='utf-8') as f:
            all_properties = list(csv.DictReader(f))
        
        logging.info(f"Loaded {len(all_properties)} properties from CSV")
        
        # Validate that the CSV has the required columns
        if not all_properties or 'Link' not in all_properties[0]:
            logging.error("CSV file does not contain 'Link' column. Cannot proceed.")
            return
            
        # Validate URLs in the CSV
        valid_properties = []
        invalid_links = []
        
        for prop in all_properties:
            link = prop.get('Link', '')
            if not link or link.strip() == '':
                invalid_links.append((prop.get('Property ID', 'unknown'), link))
            else:
                valid_properties.append(prop)
                
        if invalid_links:
            logging.warning(f"Found {len(invalid_links)} properties with invalid links:")
            for prop_id, link in invalid_links[:10]:  # Show first 10 only
                logging.warning(f"  Property ID: {prop_id}, Link: '{link}'")
            if len(invalid_links) > 10:
                logging.warning(f"  ...and {len(invalid_links) - 10} more")
                
        logging.info(f"Found {len(valid_properties)} properties with valid links")
        
        # Use only valid properties
        all_properties = valid_properties
        
        if not all_properties:
            logging.error("No valid property links found in CSV. Cannot proceed.")
            return
        
        # Take a sample if requested
        if sample_size:
            if sample_size < len(all_properties):
                all_properties = random.sample(all_properties, sample_size)
                logging.info(f"Taking a random sample of {sample_size} links")
            else:
                logging.info(f"Sample size {sample_size} is larger than available properties ({len(all_properties)}), using all properties")
        
        # For debugging, just process one property in visible mode
        if sample_size == 1:
            logging.info("Running in debug mode with a single property")
            property_row = all_properties[0]
            result = process_property(property_row, 1, 1)
            
            if result:
                output_file = 'data/property_details_debug.csv'
                # Define the column order with Property_ID first
                ordered_fields = ['Property_ID']
                for field in sorted(result.keys()):
                    if field != 'Property_ID':
                        ordered_fields.append(field)
                
                with open(output_file, 'w', encoding='utf-8', newline='') as f:
                    writer = csv.DictWriter(f, fieldnames=ordered_fields)
                    writer.writeheader()
                    writer.writerow(result)
                logging.info(f"Saved debug result to {output_file}")
            return
        
        # Start timer for regular processing
        start_time = time.time()
        all_results = []
        
        # Process properties sequentially to avoid overwhelming the server
        for i, prop in enumerate(all_properties, 1):
            result = process_property(prop, i, len(all_properties), start_time)
            if result:
                all_results.append(result)
            logging.info(f"Successfully processed property {i}/{len(all_properties)}")
        
        # Summarize results
        total_time = time.time() - start_time
        logging.info(f"Processed {len(all_results)} properties in {total_time/60:.2f} minutes")
        
        # Save results to CSV
        if all_results:
            output_file = 'data/property_details.csv'
            logging.info(f"Saving {len(all_results)} property details to {output_file}")
            
            # Get all unique keys for the CSV header
            all_keys = set()
            for result in all_results:
                all_keys.update(result.keys())
            
            # Define the column order with Property_ID first
            ordered_fields = ['Property_ID']
            for field in sorted(all_keys):
                if field != 'Property_ID':
                    ordered_fields.append(field)
            
            with open(output_file, 'w', encoding='utf-8', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=ordered_fields)
                writer.writeheader()
                writer.writerows(all_results)
            
            logging.info(f"Data successfully saved to {output_file}")
        else:
            logging.warning("No property details were collected")
            
    except Exception as e:
        logging.error(f"Error in main function: {str(e)}")
        logging.error("Stack trace:", exc_info=True)
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