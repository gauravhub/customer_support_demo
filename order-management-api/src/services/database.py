"""Database service for SQLite operations and data import.

This service provides methods for:
1. Database initialization from JSON files
2. Querying customer, order, transaction, and refund data
"""

from contextlib import closing
from pathlib import Path
from sqlite3 import connect
from typing import Any, Optional, Union

import pandas as pd

from src.config import Configuration


class DatabaseService:
    """Service for interacting with SQLite database.
    
    Provides methods for:
    - Database initialization and data import from JSON files
    - Querying customer, order, transaction, and refund data
    """
    
    def __init__(self, config: Configuration):
        """Initialize database service with configuration.
        
        Args:
            config: Configuration object containing database settings
            
        Note:
            Creates the database directory if it doesn't exist.
        """
        self.config = config
        self.database_path = Path(config.database_path)
        
        # Create database directory if it doesn't exist
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
    
    def _get_connection(self):
        """Get a database connection.
        
        Returns:
            SQLite connection object
        """
        return connect(str(self.database_path))
    
    def import_from_json(self, table_name: str, json_file_path: Union[str, Path]) -> int:
        """Import JSON data into a database table.
        
        Creates or replaces the table with data from the JSON file.
        
        Args:
            table_name: Name of the table to create/update
            json_file_path: Path to the JSON file containing the data
            
        Returns:
            Number of rows imported
            
        Raises:
            FileNotFoundError: If JSON file doesn't exist
            ValueError: If JSON file is invalid or empty
        """
        json_path = Path(json_file_path)
        if not json_path.exists():
            raise FileNotFoundError(f"JSON file not found: {json_file_path}")
        
        try:
            df = pd.read_json(json_path)
            
            if df.empty:
                print(f"Warning: JSON file {json_file_path} is empty")
                return 0
            
            with closing(self._get_connection()) as conn:
                df.to_sql(table_name, conn, if_exists='replace', index=False)
            
            row_count = len(df)
            print(f"Imported {row_count} rows into table '{table_name}' from {json_file_path}")
            return row_count
        except pd.errors.EmptyDataError as e:
            raise ValueError(f"JSON file is empty or invalid: {json_file_path}") from e
    
    def initialize(self, data_path: Optional[Union[str, Path]] = None) -> dict[str, Any]:
        """Initialize database with all data tables from JSON files.
        
        Imports customers, orders, transactions, and refunds tables.
        Should be called on application startup.
        
        Args:
            data_path: Optional path to data directory. If None, uses project data folder.
            
        Returns:
            Dictionary with import results for each table
            
        Raises:
            FileNotFoundError: If data directory doesn't exist
        """
        if data_path is None:
            project_root = Path(__file__).parent.parent.parent
            data_path = project_root / "data"
        else:
            data_path = Path(data_path)
        
        if not data_path.exists():
            raise FileNotFoundError(f"Data directory not found: {data_path}")
        
        results: dict[str, Any] = {}
        tables = ['customers', 'orders', 'transactions', 'refunds']
        
        for table_name in tables:
            json_file = data_path / f"{table_name}.json"
            try:
                row_count = self.import_from_json(table_name, json_file)
                results[table_name] = {
                    "status": "SUCCESS",
                    "rows_imported": row_count,
                    "source_file": str(json_file)
                }
            except FileNotFoundError:
                results[table_name] = {
                    "status": "SKIPPED",
                    "reason": f"JSON file not found: {json_file}"
                }
            except Exception as e:
                results[table_name] = {
                    "status": "ERROR",
                    "error": str(e)
                }
        
        return results
    
    def query(self, sql: str, params: Optional[list] = None) -> list[dict[str, Any]]:
        """Execute a SQL query and return results as a list of dictionaries.
        
        Supports parameterized queries for SQL injection prevention.
        
        Args:
            sql: SQL query string (supports parameterized queries with ?)
            params: Optional list of parameters for parameterized queries
            
        Returns:
            List of dictionaries, where each dict represents a row
            
        Raises:
            Exception: If query execution fails
        """
        try:
            with closing(self._get_connection()) as conn:
                df = pd.read_sql_query(sql=sql, con=conn, params=params)
            return df.to_dict(orient='records') if not df.empty else []
        except Exception as e:
            error_msg = f"Error executing query: {str(e)}"
            print(f"ERROR: {error_msg}")
            raise Exception(error_msg) from e
    
    def find_order(self, order_no: str) -> Optional[dict[str, Any]]:
        """Find an order by order number.
        
        Args:
            order_no: Order number to search for
            
        Returns:
            Order dictionary if found, None otherwise
        """
        results = self.query("SELECT * FROM orders WHERE order_no = ? LIMIT 1", params=[order_no])
        return results[0] if results else None
    
    def find_transaction(self, transaction_id: str) -> Optional[dict[str, Any]]:
        """Find a transaction by transaction ID.
        
        Args:
            transaction_id: Transaction ID to search for
            
        Returns:
            Transaction dictionary if found, None otherwise
        """
        results = self.query("SELECT * FROM transactions WHERE transaction_id = ? LIMIT 1", params=[transaction_id])
        return results[0] if results else None
    
    def get_transaction_for_order(self, order_no: str) -> Optional[dict[str, Any]]:
        """Get transaction information for an order.
        
        Args:
            order_no: Order number to search for
            
        Returns:
            Transaction dictionary if found, None otherwise
        """
        results = self.query("SELECT * FROM transactions WHERE order_no = ? LIMIT 1", params=[order_no])
        return results[0] if results else None
    
    def get_refund_for_order(self, order_no: str) -> Optional[dict[str, Any]]:
        """Get refund information for an order.
        
        Args:
            order_no: Order number to search for
            
        Returns:
            Refund dictionary if found, None otherwise
        """
        results = self.query("SELECT * FROM refunds WHERE order_no = ? LIMIT 1", params=[order_no])
        return results[0] if results else None
    
    def find_customer(self, customer_id: Optional[str] = None, email: Optional[str] = None) -> Optional[dict[str, Any]]:
        """Find a customer by customer ID or email.
        
        Args:
            customer_id: Customer ID to search for (optional)
            email: Email address to search for (optional)
            
        Returns:
            Customer dictionary if found, None otherwise
            
        Raises:
            ValueError: If neither customer_id nor email is provided
        """
        if not customer_id and not email:
            raise ValueError("Either customer_id or email must be provided")
        
        sql = "SELECT * FROM customers WHERE customer_id = ? LIMIT 1" if customer_id else "SELECT * FROM customers WHERE email = ? LIMIT 1"
        params = [customer_id] if customer_id else [email]
        
        results = self.query(sql, params=params)
        return results[0] if results else None
    
