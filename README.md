# Web Scraping Project for Property Data

This project is designed to scrape property data from the boligsiden.dk website, focusing on properties in the Københavns omegn area. The project is divided into two main components:

1. **Data Scraping**: Using Selenium to navigate and retrieve property links and initial data from multiple pages.
2. **Data Processing**: Using requests and BeautifulSoup to extract detailed property information from the links obtained.

## Table of Contents

- [Project Structure](#project-structure)
- [Setup Instructions](#setup-instructions)
- [How to Use](#how-to-use)
- [Dependencies](#dependencies)
- [Contributing](#contributing)
- [License](#license)

## Project Structure

- **data_scrape.py**: This script uses Selenium to scrape the initial property data and store it in a CSV file.
- **site_processor.py**: This script processes the CSV file and extracts detailed data using requests and BeautifulSoup.
- **scraped_properties.csv**: The output file from `data_scrape.py` containing initial property data.
- **property_details.csv**: The output file from `site_processor.py` with detailed property information.

## Setup Instructions

1. **Clone the repository**:
    ```bash
    git clone https://github.com/yourusername/yourrepo.git
    cd yourrepo
    ```

2. **Set up Python environment**:
    Ensure you have Python 3 installed on your machine. It's a good practice to use virtual environments:

    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows use `venv\Scripts\activate`
    ```

3. **Install necessary dependencies**:
    ```bash
    pip install -r requirements.txt
    ```

## How to Use

1. **Running Data Scraping**:
    Use `data_scrape.py` to gather initial property data:

    ```bash
    python data_scrape.py
    ```

    This will generate `scraped_properties.csv`.

2. **Processing Data**:
    Use `site_processor.py` to process links from the CSV for detailed data:

    ```bash
    python site_processor.py
    ```

    This will generate `property_details.csv`.

## Dependencies

The project requires the following Python libraries:

- requests
- beautifulsoup4
- pandas
- selenium
- webdriver-manager

These should be installed using the `requirements.txt` file.

## Contributing

Contributions are welcome! If you have any suggestions or improvements, feel free to fork the repository and submit a pull request.

## License

This project is licensed under the MIT License - see the [LICENSE.md](LICENSE.md) file for details.