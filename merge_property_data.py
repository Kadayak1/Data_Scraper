#!/usr/bin/env python
# -*- coding: utf-8 -*-

import pandas as pd
import os

def merge_property_data(properties_file, details_file, output_file):
    """
    Merge property transaction data with property attributes data.
    
    Args:
        properties_file: Path to the scraped_properties_expanded.csv file
        details_file: Path to the property_details.csv file
        output_file: Path to save the merged output CSV
    """
    print(f"Reading transaction data from {properties_file}...")
    properties_df = pd.read_csv(properties_file)
    
    print(f"Reading property details from {details_file}...")
    details_df = pd.read_csv(details_file)
    
    # Check the column names in each dataframe
    print(f"\nTransaction data columns: {properties_df.columns.tolist()}")
    print(f"Property details columns: {details_df.columns.tolist()}")
    
    # Get initial row counts
    properties_count = len(properties_df)
    details_count = len(details_df)
    print(f"\nTransaction records: {properties_count}")
    print(f"Property records: {details_count}")
    
    # Rename the Property_ID column in the details dataframe to match the properties dataframe
    details_df = details_df.rename(columns={'Property_ID': 'Property ID'})
    
    # Perform a left join to keep all transaction records
    print("\nMerging datasets...")
    merged_df = pd.merge(
        properties_df, 
        details_df, 
        on='Property ID', 
        how='left',
        suffixes=('', '_details')
    )
    
    # Get the merged row count
    merged_count = len(merged_df)
    print(f"Merged records: {merged_count}")
    
    # Check for missing property attributes
    # Count rows where any property attribute is missing
    property_attrs = ['Living_Area', 'Heating_Type', 'Roof_Type', 'Wall_Material']
    missing_attrs = merged_df[property_attrs].isna().any(axis=1).sum()
    print(f"Transactions with missing property attributes: {missing_attrs} ({missing_attrs / merged_count:.2%})")
    
    # Fill missing values with 'N/A'
    print("\nFilling missing values with 'N/A'...")
    merged_df = merged_df.fillna('N/A')
    
    # Save the merged dataframe to a new CSV file
    print(f"\nSaving merged data to {output_file}...")
    merged_df.to_csv(output_file, index=False)
    
    print(f"\nSuccess! Merged data saved to {output_file}")
    print(f"Total records: {merged_count}")
    
    # Return stats for additional use if needed
    return {
        'properties_count': properties_count,
        'details_count': details_count,
        'merged_count': merged_count,
        'missing_attrs': missing_attrs
    }

if __name__ == "__main__":
    # File paths
    properties_file = "data/scraped_properties_expanded.csv"
    details_file = "data/property_details.csv"
    output_file = "data/property_details_per_sale.csv"
    
    # Check if input files exist
    if not os.path.exists(properties_file):
        print(f"Error: {properties_file} not found!")
        exit(1)
        
    if not os.path.exists(details_file):
        print(f"Error: {details_file} not found!")
        exit(1)
    
    # Run the merge function
    merge_property_data(properties_file, details_file, output_file) 