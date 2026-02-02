from dotenv import load_dotenv
import os

load_dotenv()  

SERVER_URL = os.getenv("SERVER_URL", "http://localhost:8000")
SECRET_KEY = os.getenv("SECRET_KEY", "...")