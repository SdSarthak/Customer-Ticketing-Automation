"""
Data Loader Module
Handles loading, preprocessing, and managing customer support ticket data
"""

import pandas as pd
import os
from typing import List, Dict, Optional, Tuple
from tqdm import tqdm


class DataLoader:
    """Class to handle data loading and preprocessing for customer support tickets"""
    
    def __init__(self, data_path: str):
        """
        Initialize DataLoader
        
        Args:
            data_path: Path to the CSV file containing support tickets
        """
        self.data_path = data_path
        self.data = None
        self.processed_data = None
        
    def load_data(self) -> pd.DataFrame:
        """
        Load data from CSV file
        
        Returns:
            DataFrame containing the loaded data
        """
        if not os.path.exists(self.data_path):
            raise FileNotFoundError(f"Data file not found: {self.data_path}")
        
        self.data = pd.read_csv(self.data_path)
        print(f"✅ Loaded {len(self.data)} records from {self.data_path}")
        return self.data
    
    def preprocess_data(self) -> pd.DataFrame:
        """
        Preprocess the loaded data
        
        Returns:
            Preprocessed DataFrame
        """
        if self.data is None:
            raise ValueError("Data not loaded. Call load_data() first.")
        
        df = self.data.copy()
        
        # Remove duplicates
        initial_count = len(df)
        df = df.drop_duplicates()
        print(f"📊 Removed {initial_count - len(df)} duplicate records")
        
        # Handle missing values
        df = df.fillna("")
        
        # Clean text columns
        text_columns = df.select_dtypes(include=['object']).columns
        for col in text_columns:
            df[col] = df[col].str.strip()
            df[col] = df[col].str.replace(r'\s+', ' ', regex=True)
        
        self.processed_data = df
        print(f"✅ Preprocessing complete. {len(df)} records ready.")
        return df
    
    def create_documents(self, instruction_col: str = "instruction", 
                        response_col: str = "response",
                        category_col: Optional[str] = None) -> List[Dict]:
        """
        Create document dictionaries for embedding
        
        Args:
            instruction_col: Column name for customer instructions/queries
            response_col: Column name for support responses
            category_col: Optional column name for ticket categories
            
        Returns:
            List of document dictionaries
        """
        if self.processed_data is None:
            self.preprocess_data()
        
        documents = []
        df = self.processed_data
        
        for idx, row in tqdm(df.iterrows(), total=len(df), desc="Creating documents"):
            doc = {
                "id": str(idx),
                "instruction": row.get(instruction_col, ""),
                "response": row.get(response_col, ""),
                "category": row.get(category_col, "General") if category_col else "General",
                "combined_text": f"Customer Query: {row.get(instruction_col, '')}\nSupport Response: {row.get(response_col, '')}"
            }
            documents.append(doc)
        
        print(f"✅ Created {len(documents)} documents for embedding")
        return documents
    
    def get_statistics(self) -> Dict:
        """
        Get statistics about the loaded data
        
        Returns:
            Dictionary containing data statistics
        """
        if self.data is None:
            raise ValueError("Data not loaded. Call load_data() first.")
        
        stats = {
            "total_records": len(self.data),
            "columns": list(self.data.columns),
            "missing_values": self.data.isnull().sum().to_dict(),
            "data_types": self.data.dtypes.astype(str).to_dict()
        }
        
        # Add text length statistics if applicable
        text_columns = self.data.select_dtypes(include=['object']).columns
        for col in text_columns:
            stats[f"{col}_avg_length"] = self.data[col].str.len().mean()
        
        return stats
    
    def split_data(self, test_size: float = 0.2, 
                   random_state: int = 42) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        Split data into training and testing sets
        
        Args:
            test_size: Proportion of data for testing
            random_state: Random seed for reproducibility
            
        Returns:
            Tuple of (train_df, test_df)
        """
        if self.processed_data is None:
            self.preprocess_data()
        
        df = self.processed_data.sample(frac=1, random_state=random_state).reset_index(drop=True)
        split_idx = int(len(df) * (1 - test_size))
        
        train_df = df[:split_idx]
        test_df = df[split_idx:]
        
        print(f"✅ Data split: {len(train_df)} training, {len(test_df)} testing")
        return train_df, test_df


def load_and_prepare_data(data_path: str) -> Tuple[pd.DataFrame, List[Dict]]:
    """
    Convenience function to load and prepare data in one step
    
    Args:
        data_path: Path to the CSV file
        
    Returns:
        Tuple of (processed_df, documents)
    """
    loader = DataLoader(data_path)
    loader.load_data()
    df = loader.preprocess_data()
    documents = loader.create_documents()
    return df, documents


if __name__ == "__main__":
    # Test the data loader
    import sys
    
    if len(sys.argv) > 1:
        data_path = sys.argv[1]
    else:
        data_path = "data/customer_support_tickets.csv"
    
    try:
        loader = DataLoader(data_path)
        loader.load_data()
        stats = loader.get_statistics()
        print("\n📈 Data Statistics:")
        for key, value in stats.items():
            print(f"  {key}: {value}")
    except FileNotFoundError as e:
        print(f"❌ Error: {e}")
