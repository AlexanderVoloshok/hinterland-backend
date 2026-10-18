import os
import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine

env_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), '.env')
load_dotenv(env_path)

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