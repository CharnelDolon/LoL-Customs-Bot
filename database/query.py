import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "league.db")
conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# Show all players with their weight
cursor.execute("SELECT summoner_name, rank_tier, weight, current_team_id FROM players;")
players = cursor.fetchall()
for p in players:
    print(p)

# Show all teams with their average weight
cursor.execute("SELECT team_name, avg_weight FROM teams;")
teams = cursor.fetchall()
for t in teams:
    print(t)

conn.close()