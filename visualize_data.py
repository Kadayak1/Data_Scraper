import pandas as pd
import matplotlib.pyplot as plt
import os
import glob
from tabulate import tabulate

def list_csv_files():
    """List all CSV files in the data directory"""
    csv_files = glob.glob('data/*.csv')
    if not csv_files:
        print("No CSV files found in the data directory.")
        return None
    
    print("\nAvailable CSV files:")
    for i, file in enumerate(csv_files, 1):
        file_size = os.path.getsize(file) / 1024  # Size in KB
        print(f"{i}. {os.path.basename(file)} ({file_size:.1f} KB)")
    return csv_files

def get_file_choice(csv_files):
    """Get user's file choice"""
    while True:
        try:
            choice = int(input("\nEnter the number of the file you want to visualize (or 0 to exit): "))
            if choice == 0:
                return None
            if 1 <= choice <= len(csv_files):
                return csv_files[choice - 1]
            print("Invalid choice. Please try again.")
        except ValueError:
            print("Please enter a valid number.")

def analyze_data_quality(df):
    """Analyze and display data quality metrics"""
    print("\nData Quality Analysis:")
    print("-" * 50)
    
    # Basic statistics
    print(f"Total rows: {len(df)}")
    print(f"Total columns: {len(df.columns)}")
    
    # Column-wise analysis
    quality_metrics = []
    for column in df.columns:
        non_null = df[column].notna().sum()
        percentage = (non_null / len(df)) * 100
        unique_values = df[column].nunique()
        quality_metrics.append([column, non_null, f"{percentage:.1f}%", unique_values])
    
    # Display quality metrics in a table
    print("\nColumn-wise Data Quality:")
    print(tabulate(quality_metrics, 
                  headers=['Column', 'Non-Null Count', 'Completeness', 'Unique Values'],
                  tablefmt='grid'))
    
    # Data type analysis
    print("\nData Types:")
    print(tabulate([[col, str(dtype)] for col, dtype in df.dtypes.items()],
                  headers=['Column', 'Data Type'],
                  tablefmt='grid'))

def visualize_data(df):
    """Create visualizations for the data"""
    # Create a figure with multiple subplots
    fig, axes = plt.subplots(2, 2, figsize=(15, 12))
    fig.suptitle('Data Visualization', fontsize=16)
    
    # Plot 1: Numeric columns distribution
    numeric_cols = df.select_dtypes(include=['int64', 'float64']).columns
    if len(numeric_cols) > 0:
        df[numeric_cols].hist(ax=axes[0, 0], bins=20)
        axes[0, 0].set_title('Numeric Columns Distribution')
        plt.setp(axes[0, 0].get_xticklabels(), rotation=45)
    
    # Plot 2: Categorical columns distribution
    categorical_cols = df.select_dtypes(include=['object']).columns
    if len(categorical_cols) > 0:
        for col in categorical_cols[:5]:  # Limit to first 5 categorical columns
            value_counts = df[col].value_counts().head(10)  # Top 10 values
            value_counts.plot(kind='bar', ax=axes[0, 1])
        axes[0, 1].set_title('Top 10 Values in Categorical Columns')
        plt.setp(axes[0, 1].get_xticklabels(), rotation=45)
    
    # Plot 3: Missing values heatmap
    missing_data = df.isnull()
    axes[1, 0].matshow(missing_data, aspect='auto', cmap='viridis')
    axes[1, 0].set_title('Missing Values Heatmap')
    axes[1, 0].set_xlabel('Columns')
    axes[1, 0].set_ylabel('Rows')
    
    # Plot 4: Correlation heatmap for numeric columns
    if len(numeric_cols) > 1:
        correlation = df[numeric_cols].corr()
        im = axes[1, 1].matshow(correlation, cmap='coolwarm')
        axes[1, 1].set_title('Correlation Heatmap')
        plt.colorbar(im, ax=axes[1, 1])
    
    plt.tight_layout()
    plt.savefig('data_visualization.png', dpi=300, bbox_inches='tight')
    print("\nVisualization saved as 'data_visualization.png'")

def main():
    print("Data Visualization Tool")
    print("=" * 50)
    
    csv_files = list_csv_files()
    if not csv_files:
        return
    
    selected_file = get_file_choice(csv_files)
    if not selected_file:
        return
    
    try:
        # Read the CSV file
        print(f"\nReading {os.path.basename(selected_file)}...")
        df = pd.read_csv(selected_file)
        
        # Analyze data quality
        analyze_data_quality(df)
        
        # Create visualizations
        visualize_data(df)
        
    except Exception as e:
        print(f"Error processing file: {e}")

if __name__ == "__main__":
    main() 