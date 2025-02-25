import sqlite3

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
