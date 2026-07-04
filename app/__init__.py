import os
from pathlib import Path

from dotenv import load_dotenv


load_dotenv(Path(__file__).resolve().parents[1] / ".env")
os.environ.setdefault("LOKY_MAX_CPU_COUNT", "1")
