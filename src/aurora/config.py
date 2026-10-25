from pathlib import Path

from dotenv import load_dotenv
from google.genai import types

ROOT_DIR = Path(__file__).resolve().parents[2]
load_dotenv(ROOT_DIR / ".env")

DADOS_DIR = ROOT_DIR / "dados"
DB_PATH = ROOT_DIR / "data" / "aurora.db"
DB_URL = f"sqlite+aiosqlite:///{DB_PATH.as_posix()}"

MODEL = "gemini-3.8-flash"
APP_NAME = "aurora"
USER_ID = "morador"

RETRY_OPTIONS = types.HttpRetryOptions(http_status_codes=[429, 503])
