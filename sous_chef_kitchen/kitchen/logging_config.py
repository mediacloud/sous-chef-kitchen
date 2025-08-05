"""
Logging configuration for Sous Chef Kitchen.
"""

import logging
import sys
import os

def setup_logging():
    """Setup logging configuration for the application."""
    
    # Get log level from environment or default to INFO
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    
    # Configure logging
    logging.basicConfig(
        level=getattr(logging, log_level),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout)
        ],
        force=True  # Override any existing configuration
    )
    
    # Set specific logger levels
    logging.getLogger("sous_chef_kitchen").setLevel(getattr(logging, log_level))
    logging.getLogger("uvicorn").setLevel(getattr(logging, log_level))
    logging.getLogger("fastapi").setLevel(getattr(logging, log_level))
    
    # Create logger for this module
    logger = logging.getLogger("sous_chef_kitchen.logging")
    logger.info(f"Logging configured with level: {log_level}")
    
    return logger 