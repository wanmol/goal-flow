from dotenv import load_dotenv
import os

from goalflow.config import get_logger

logger = get_logger(__name__)

def load_env():
    """Load environment variables."""
    
    env = os.getenv("ENV", "development")
    
    logger.info(f"Loading environment: {env}")
    
    if env == "production":
        load_dotenv(".env_prod")
    elif env == "uat":
        load_dotenv(".env_uat")
    elif env == "test":
        load_dotenv(".env_test")
    else:  # development or default
        load_dotenv(".env")