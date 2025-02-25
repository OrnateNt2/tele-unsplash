import sqlite3
import json

DB_PATH = "subscriptions.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS subscriptions (
        user_id INTEGER PRIMARY KEY,
        chat_id INTEGER NOT NULL
    )
    ''')
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS user_settings (
        user_id INTEGER PRIMARY KEY,
        settings TEXT
    )
    ''')
    conn.commit()
    conn.close()

def add_subscription(user_id: int, chat_id: int):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO subscriptions (user_id, chat_id) VALUES (?, ?)", (user_id, chat_id))
    conn.commit()
    conn.close()

def remove_subscription(user_id: int):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM subscriptions WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

def check_subscription(user_id: int) -> bool:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM subscriptions WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    conn.close()
    return bool(result)

def get_all_subscriptions():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, chat_id FROM subscriptions")
    results = cursor.fetchall()
    conn.close()
    return results

def get_user_settings(user_id: int) -> dict:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT settings FROM user_settings WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return json.loads(row[0])
    return {}

def set_user_settings(user_id: int, settings: dict):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    settings_json = json.dumps(settings)
    cursor.execute("INSERT OR REPLACE INTO user_settings (user_id, settings) VALUES (?, ?)", (user_id, settings_json))
    conn.commit()
    conn.close()
