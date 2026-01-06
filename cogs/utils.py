import aiosqlite

DB_PATH = "league.db"

async def get_team_by_captain(captain_id):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT team_id, team_name FROM teams WHERE captain_id=?", (captain_id,))
        return await cursor.fetchone()

async def get_team_name(team_id):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT team_name FROM teams WHERE team_id=?", (team_id,))
        row = await cursor.fetchone()
        return row[0] if row else None

async def get_players_on_team(team_id):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("""
            SELECT summoner_name, rank_tier, rank_score, is_captain 
            FROM players 
            WHERE team_id=?
        """, (team_id,))
        return await cursor.fetchall()