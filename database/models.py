# models.py
# Create tables using a shared database instance
def create_tables(db):
    # --------------------------
    # PLAYERS TABLE
    # --------------------------
    db.execute("""
    CREATE TABLE IF NOT EXISTS players (
        discord_id INTEGER PRIMARY KEY,
        summoner_name TEXT,
        rank_tier TEXT,
        rank_score INTEGER DEFAULT 0,
        weight REAL DEFAULT 0,
        current_team_id INTEGER,
        peak_team_elo INTEGER DEFAULT 0,
        peak_team_name TEXT,
        FOREIGN KEY (current_team_id) REFERENCES teams(team_id)
    );
    """)
    
    # --------------------------
    # TEAMS TABLE
    # --------------------------
    db.execute("""
    CREATE TABLE IF NOT EXISTS teams (
        team_id INTEGER PRIMARY KEY AUTOINCREMENT,
        team_name TEXT UNIQUE,
        captain_id INTEGER,
        elo INTEGER DEFAULT 1000,
        wins INTEGER DEFAULT 0,
        losses INTEGER DEFAULT 0,
        avg_weight REAL DEFAULT 0,
        FOREIGN KEY (captain_id) REFERENCES players(discord_id)
    );
    """)

    # --------------------------
    # TEAM MEMBERS TABLE
    # --------------------------
    db.execute("""
    CREATE TABLE IF NOT EXISTS team_members (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        team_id INTEGER,
        player_id INTEGER,
        FOREIGN KEY (team_id) REFERENCES teams(team_id),
        FOREIGN KEY (player_id) REFERENCES players(discord_id)
    );
    """)

    # --------------------------
    # MATCHES TABLE
    # --------------------------
    db.execute("""
    CREATE TABLE IF NOT EXISTS matches (
        match_id INTEGER PRIMARY KEY AUTOINCREMENT,
        team1_id INTEGER,
        team2_id INTEGER,
        team1_side TEXT,
        team2_side TEXT,
        expected_team1_elo REAL,
        expected_team2_elo REAL,
        winner_id INTEGER,
        loser_id INTEGER,
        screenshot_url TEXT,
        status TEXT DEFAULT 'pending',
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (team1_id) REFERENCES teams(team_id),
        FOREIGN KEY (team2_id) REFERENCES teams(team_id),
        FOREIGN KEY (winner_id) REFERENCES teams(team_id),
        FOREIGN KEY (loser_id) REFERENCES teams(team_id)
    );
    """)


    print("✅ Database tables created successfully.")