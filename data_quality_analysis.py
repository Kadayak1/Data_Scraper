import pandas as pd
import numpy as np
import json
from datetime import datetime

def load_and_clean_data():
    # Load the main datasets
    properties_df = pd.read_csv('data/scraped_properties.csv')
    details_df = pd.read_csv('data/property_details.csv')
    
    # Merge the datasets on Property ID
    merged_df = pd.merge(properties_df, details_df, 
                        left_on='Property ID', 
                        right_on='ID', 
                        how='inner')
    
    # Convert Sales column from string to list of dictionaries
    merged_df['Sales'] = merged_df['Sales'].apply(lambda x: json.loads(x) if pd.notna(x) else [])
    
    # Extract sale dates and prices
    merged_df['Sale_Dates'] = merged_df['Sales'].apply(lambda x: [sale['Sale Date'] for sale in x])
    merged_df['Sale_Prices'] = merged_df['Sales'].apply(lambda x: [sale['Price'] for sale in x])
    
    # Calculate data quality metrics
    print("\n=== Data Quality Analysis ===")
    print("\nMissing Values Analysis:")
    print(merged_df.isnull().sum())
    
    print("\nData Types:")
    print(merged_df.dtypes)
    
    print("\nBasic Statistics for Numerical Columns:")
    print(merged_df.describe())
    
    # Create a clean dataset by removing rows with missing values
    # We'll keep rows where essential features are present
    essential_columns = [
        'Property ID', 'Address', 'Property Type', 'Living_Area_M2',
        'Num_Rooms', 'Construction_Year', 'Sale_Prices'
    ]
    
    clean_df = merged_df.dropna(subset=essential_columns)
    
    # Additional cleaning steps
    # Remove rows where living area is 0 or negative
    clean_df = clean_df[clean_df['Living_Area_M2'] > 0]
    
    # Remove rows where number of rooms is 0 or negative
    clean_df = clean_df[clean_df['Num_Rooms'] > 0]
    
    # Remove rows where construction year is in the future
    current_year = datetime.now().year
    clean_df = clean_df[clean_df['Construction_Year'] <= current_year]
    
    # Save the clean dataset
    clean_df.to_csv('data/clean_property_data.csv', index=False)
    
    print(f"\nOriginal dataset size: {len(merged_df)} rows")
    print(f"Clean dataset size: {len(clean_df)} rows")
    print(f"Removed {len(merged_df) - len(clean_df)} rows due to missing or invalid data")
    
    # Print some examples of cleaned data
    print("\nSample of cleaned data:")
    print(clean_df[['Property ID', 'Address', 'Property Type', 'Living_Area_M2', 
                   'Num_Rooms', 'Construction_Year']].head())

if __name__ == "__main__":
    load_and_clean_data() 