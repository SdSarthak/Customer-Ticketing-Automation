"""
Data Loader Module
Handles loading, preprocessing, and managing customer support ticket data
"""

import pandas as pd
import os
from typing import List, Dict, Optional, Tuple
from tqdm import tqdm


def _text(value) -> str:
    """
    Coerce a cell to clean text.

    `str(value or "")` looked equivalent but turned a float NaN into the literal
    string "nan" (NaN is truthy) and a numeric 0 into "", so malformed rows were
    embedded as the word "nan" and indexed as if they were real content.
    """
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        # Arrays and other non-scalars: fall through to str()
        pass
    return str(value).strip()


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
        if not os.path.isfile(self.data_path):
            raise ValueError(f"Data path is not a file: {self.data_path}")

        try:
            self.data = pd.read_csv(self.data_path)
        except pd.errors.EmptyDataError as e:
            raise ValueError(f"Data file is empty: {self.data_path}") from e
        except pd.errors.ParserError as e:
            raise ValueError(
                f"Data file {self.data_path} is not valid CSV: {e}"
            ) from e
        except UnicodeDecodeError:
            # Exported spreadsheets are frequently latin-1/cp1252 rather than UTF-8
            self.data = pd.read_csv(self.data_path, encoding="latin-1")

        if self.data.empty:
            raise ValueError(
                f"Data file {self.data_path} has a header but no rows — "
                "nothing can be indexed from it."
            )

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
        
        # Clean text columns. astype(str) first: a mixed-type object column
        # (numbers alongside text) makes .str.strip() return NaN for every
        # non-string cell, silently re-introducing the nulls fillna just removed.
        text_columns = df.select_dtypes(include=['object']).columns
        for col in text_columns:
            df[col] = df[col].astype(str).str.strip()
            df[col] = df[col].str.replace(r'\s+', ' ', regex=True)
        
        self.processed_data = df
        print(f"✅ Preprocessing complete. {len(df)} records ready.")
        return df
    
    def create_documents(self, instruction_col: str = "instruction",
                        response_col: str = "response",
                        category_col: Optional[str] = "category") -> List[Dict]:
        """
        Create document dictionaries for embedding

        Args:
            instruction_col: Column name for customer instructions/queries
            response_col: Column name for support responses
            category_col: Column name for ticket categories. Defaults to
                "category" and is silently ignored when the CSV has no such
                column, so datasets with only instruction/response still work.

        Returns:
            List of document dictionaries
        """
        if self.processed_data is None:
            self.preprocess_data()

        df = self.processed_data

        missing = [c for c in (instruction_col, response_col) if c not in df.columns]
        if missing:
            raise ValueError(
                f"Data file {self.data_path} is missing required column(s): "
                f"{', '.join(missing)}. Found: {', '.join(df.columns)}"
            )

        # Only use the category column if it is actually present
        has_category = bool(category_col) and category_col in df.columns

        documents = []
        blank_rows = 0
        for idx, row in tqdm(df.iterrows(), total=len(df), desc="Creating documents"):
            instruction = _text(row[instruction_col])
            response = _text(row[response_col])

            # A row with neither a question nor an answer still produced a
            # document whose text was just the two template labels. That costs
            # an embedding API call and then sits in the index as a document
            # every query can weakly match. Drop it instead.
            if not instruction and not response:
                blank_rows += 1
                continue

            category = (_text(row[category_col]) or "General") if has_category else "General"
            documents.append({
                "id": str(idx),
                "instruction": instruction,
                "response": response,
                "category": category,
                "combined_text": f"Customer Query: {instruction}\nSupport Response: {response}",
            })

        if not documents:
            raise ValueError(
                f"No usable rows in {self.data_path}: every row had an empty "
                f"'{instruction_col}' and '{response_col}'."
            )

        print(f"✅ Created {len(documents)} documents for embedding")
        if blank_rows:
            print(f"ℹ️ Skipped {blank_rows} row(s) with no query and no response")
        if not has_category:
            print(f"ℹ️ No '{category_col}' column found — all documents tagged 'General'")
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
