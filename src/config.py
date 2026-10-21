import os
import pandas as pd
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import create_engine

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = PROJECT_ROOT / ".env"

load_dotenv(ENV_PATH)

URI = os.getenv('DB_URI')
ENGINE = create_engine(URI, pool_pre_ping=True)

CITIES = pd.read_sql("""
    SELECT city FROM wikipedia.cities_available
""", ENGINE)

class Config:
    DB_URI = URI
    ALLOWED_CITIES = tuple(CITIES['city'].values)
    UPLOAD_FOLDER = os.path.dirname(os.path.realpath(__file__)) + '/files'
    APP_ROOT = '/api_hinterlands'

CONFIG = Config()