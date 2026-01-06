import os
import logging
import discord
from discord.ext import commands
from dotenv import load_dotenv
import importlib

from database.db import Database        # your Database wrapper
from database.models import create_tables  # table creation function

# --------------------------
# Load environment variables
# --------------------------
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise ValueError("DISCORD_TOKEN environment variable not set!")

# --------------------------
# Logging
# --------------------------
logging.basicConfig(level=logging.INFO)

# --------------------------
# Bot Setup
# -------------------------- 
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True
bot = commands.Bot(command_prefix="!", intents=intents)

# --------------------------
# Database Setup
# --------------------------
db = Database()
create_tables(db)  # pass db instance to create tables
logging.info("✅ Database tables created successfully.")

# --------------------------
# Cog Loader
# --------------------------
async def setup_all_cogs():
    cogs = [
        "cogs.players",
        "cogs.teams",
        "cogs.matches",
        "cogs.admin"
    ]
    for cog_path in cogs:
        mod = importlib.import_module(cog_path)
        await mod.setup(bot, db)  # call setup(bot, db) in each cog

# --------------------------
# Events
# --------------------------
@bot.event
async def on_ready():
    logging.info(f"✅ Logged in as {bot.user}")
    await setup_all_cogs()
    await bot.tree.sync()
    logging.info("✅ Synced slash commands.")

# --------------------------
# Run Bot
# --------------------------
bot.run(TOKEN)