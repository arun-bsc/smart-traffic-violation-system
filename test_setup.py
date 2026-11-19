import os
import mysql.connector
from dotenv import load_dotenv

load_dotenv()   # reads the .env file

connection = mysql.connector.connect(
    host=os.getenv("DB_HOST"),
    user=os.getenv("DB_USER"),
    password=os.getenv("DB_PASSWORD")
)

if connection.is_connected():
    print("MySQL connection: SUCCESS")

connection.close()