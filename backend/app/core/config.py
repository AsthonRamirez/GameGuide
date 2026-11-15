import os
from dotenv import load_dotenv
load_dotenv()
APP_NAME = "GameGuide AI API"
FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")
