import discord

# ---------------------------
# Error embed
# ---------------------------
def error_embed(message: str) -> discord.Embed:
    embed = discord.Embed(
        title="❌ Error",
        description=message,
        color=discord.Color.red()
    )
    return embed

# ---------------------------
# Success embed
# ---------------------------
def success_embed(message: str) -> discord.Embed:
    embed = discord.Embed(
        title="✅ Success",
        description=message,
        color=discord.Color.green()
    )
    return embed

# ---------------------------
# Info embed (optional)
# ---------------------------
def info_embed(message: str) -> discord.Embed:
    embed = discord.Embed(
        title="ℹ️ Info",
        description=message,
        color=discord.Color.blue()
    )
    return embed