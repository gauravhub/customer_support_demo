"""Configuration class for database settings."""


class Configuration:
    """Simple configuration class for database path."""
    
    def __init__(self, database_path: str = "./data/temp/order-management.db"):
        """Initialize configuration with database path.
        
        Args:
            database_path: Path to the SQLite database file
        """
        self._database_path = database_path
    
    @property
    def database_path(self) -> str:
        """Get the database path."""
        return self._database_path
