import psycopg2
from config.config import Config

conn = None  # biến toàn cục

def connect_db():
    """Kết nối DB 1 lần, dùng cho toàn app"""
    global conn
    if conn is None:
        conn = psycopg2.connect(Config.get_db_connection_string())
        print("Database connected")
    return conn

def disconnect_db():
    """Đóng kết nối khi app tắt"""
    global conn
    if conn:
        conn.close()
        conn = None
        print("Database disconnected")
