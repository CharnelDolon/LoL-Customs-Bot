import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "league.db")

class Database:
    def __init__(self):
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        self.conn = sqlite3.connect(DB_PATH)
        self.conn.row_factory = sqlite3.Row
        self.cursor = self.conn.cursor()

    def execute(self, query, params=tuple()):
        self.cursor.execute(query, params)
        self.conn.commit()

    def executemany(self, query, params_list):
        self.cursor.executemany(query, params_list)
        self.conn.commit()

    def fetch_one(self, query, params=tuple()):
        self.cursor.execute(query, params)
        return self.cursor.fetchone()

    def fetch_all(self, query, params=tuple()):
        self.cursor.execute(query, params)
        return self.cursor.fetchall()

    def commit(self):
        self.conn.commit()