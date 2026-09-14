import os

API_TOKEN = os.getenv("API_TOKEN", "test-token")

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "3306"))
DB_USER = os.getenv("DB_USER", "vote")
DB_PASSWORD = os.getenv("DB_PASSWORD", "votepw")
DB_NAME = os.getenv("DB_NAME", "vote")

DATABASE_URL = (
    f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}?charset=utf8mb4"
)
