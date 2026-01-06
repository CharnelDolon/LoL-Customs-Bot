import discord
from discord.ext import commands

RANK_WEIGHTS = {
    "iron": 1,
    "bronze": 2,
    "silver": 3,
    "gold": 4,
    "platinum": 5,
    "emerald": 6,
    "diamond": 7,
    "master": 8,
    "grandmaster": 9,
    "challenger": 10
}

class PlayerCog(commands.Cog):
    def __init__(self, bot, db):
        self.bot = bot
        self.db = db

    # ---------------------------
    # /player_register <summoner_name>
    # ---------------------------
    @commands.hybrid_command(name="player_register", description="Register as a player in the system.")
    async def player_register(self, ctx, *, summoner_name: str):  # <-- notice the *
        discord_id = str(ctx.author.id)

        # Check if player exists
        player = self.db.fetch_one("SELECT discord_id FROM players WHERE discord_id=?", (discord_id,))
        if player:
            return await ctx.send("❌ You are already registered!", ephemeral=True)

        # Insert new player
        self.db.execute(
            "INSERT INTO players (discord_id, summoner_name) VALUES (?, ?)",
            (discord_id, summoner_name)
        )

        await ctx.send(f"✅ Registered **{summoner_name}** successfully!")

    # ---------------------------
    # /player_rank <rank>
    # ---------------------------
    @commands.hybrid_command(name="player_rank", description="Set your peak League rank.")
    async def player_rank(self, ctx, rank: str):
        rank_lower = rank.lower()

        if rank_lower not in RANK_WEIGHTS:
            return await ctx.send("❌ Invalid rank. Use Iron → Challenger.", ephemeral=True)

        discord_id = ctx.author.id

        # Check player exists
        player = self.db.fetch_one(
            "SELECT discord_id, current_team_id FROM players WHERE discord_id=?",
            (discord_id,)
        )
        if not player:
            return await ctx.send("❌ You must register first using /player_register", ephemeral=True)

        _, current_team_id = player

        # Get weight based on rank score
        weight = float(RANK_WEIGHTS[rank_lower])

        # Update player's rank + weight
        self.db.execute(
            "UPDATE players SET rank_tier=?, rank_score=?, weight=? WHERE discord_id=?",
            (rank.capitalize(), RANK_WEIGHTS[rank_lower], weight, discord_id)
        )

        # If player is on a team → recalc avg weight
        if current_team_id:
            self.db.execute("""
                UPDATE teams SET avg_weight = (
                    SELECT AVG(weight)
                    FROM players
                    WHERE current_team_id = ?
                )
                WHERE team_id = ?
            """, (current_team_id, current_team_id))

        await ctx.send(f"✅ Peak rank set to **{rank.capitalize()}** and weight updated!")

    # ---------------------------
    # /player_profile
    # ---------------------------
    @commands.hybrid_command(name="player_profile", description="View your profile stats.")
    async def player_profile(self, ctx):
        discord_id = ctx.author.id

        player = self.db.fetch_one("SELECT * FROM players WHERE discord_id=?", (discord_id,))
        if not player:
            return await ctx.send("❌ You must register first with /player_register", ephemeral=True)

        # Fetch team info
        team_name = "None"
        team_elo = team_wins = team_losses = 0
        team_wr = 0
        if player["current_team_id"]:
            team = self.db.fetch_one("SELECT * FROM teams WHERE team_id=?", (player["current_team_id"],))
            if team:
                team_name = team["team_name"]
                team_elo = team["elo"]
                team_wins = team["wins"]
                team_losses = team["losses"]
                team_wr = round(team_wins / (team_wins + team_losses) * 100, 2) if (team_wins + team_losses) > 0 else 0

        embed = discord.Embed(
            title=f"🎮 Player Profile — {ctx.author.name}",
            color=discord.Color.blue()
        )
        embed.add_field(name="Summoner Name", value=player["summoner_name"], inline=False)
        embed.add_field(name="Current Team", value=team_name, inline=True)
        embed.add_field(name="Team Elo", value=str(team_elo), inline=True)
        embed.add_field(name="Team Record", value=f"{team_wins}W / {team_losses}L\nWinrate: {team_wr}%", inline=False)
        embed.add_field(name="Peak Rank", value=player["rank_tier"] or "Unranked", inline=True)
        embed.add_field(name="All-Time Peak Elo", value=str(player["peak_team_elo"]), inline=True)
        embed.add_field(name="Team of Peak Elo", value=player["peak_team_name"] or "None", inline=True)

        await ctx.send(embed=embed)

    # ---------------------------
    # /player_retire
    # ---------------------------
    @commands.hybrid_command(name="player_retire", description="Retire your player profile.")
    async def player_retire(self, interaction: discord.Interaction):
            player = self.get_player(interaction.user.id)

            if not player:
                return await interaction.response.send_message(
                    "❌ You do not have a player profile registered.", ephemeral=True
                )

            team_id = player["team_id"]

            # If player is not on a team → delete immediately
            if team_id is None:
                self.bot.cursor.execute("DELETE FROM players WHERE discord_id = ?", (interaction.user.id,))
                self.bot.conn.commit()
                return await interaction.response.send_message(
                    "🗑️ Your player profile has been successfully **retired**.", ephemeral=True
                )

            # Player is on a team → check captain
            team = self.get_team(team_id)
            captain_id = team["captain_id"]

            if captain_id == interaction.user.id:
                # BLOCK retirement if player is captain
                return await interaction.response.send_message(
                    "**🚫 Retirement Blocked**\n\n"
                    "You are the **captain** of your team.\n"
                    "To retire, you must:\n"
                    "• Delete the team completely\n",
                    ephemeral=True,
                )

            # Player is NOT captain → remove from team then retire
            self.bot.cursor.execute(
                "UPDATE players SET team_id = NULL WHERE discord_id = ?", (interaction.user.id,)
            )
            self.bot.cursor.execute(
                "DELETE FROM players WHERE discord_id = ?", (interaction.user.id,)
            )
            self.bot.conn.commit()

            return await interaction.response.send_message(
                "✅ You have been removed from your team and your profile is now **retired**.",
                ephemeral=True
            )
    
    # Utility to fetch player row
    def get_player(self, discord_id):
        self.bot.cursor.execute("SELECT * FROM players WHERE discord_id = ?", (discord_id,))
        return self.bot.cursor.fetchone()

    # Utility to fetch team by id
    def get_team(self, team_id):
        self.bot.cursor.execute("SELECT * FROM teams WHERE team_id = ?", (team_id,))
        return self.bot.cursor.fetchone()
    
    
    @commands.hybrid_command(name="commands", description="Shows all player commands.")
    async def help(self, ctx: commands.Context):

        embed = discord.Embed(
            title="📘 LoL Customs — Command List",
            description="Format: `!command <required> [optional]`",
            color=discord.Color.blurple()
        )

        # -------------------------
        # PLAYER COMMANDS
        # -------------------------
        embed.add_field(
            name="👤 Player Commands",
            value=
                "**!player_register <summoner name>** — Register yourself as a player or captain.\n"
                "**!player_rank <rank>** — Set your peak League rank (Iron → Challenger).\n"
                "**!player_profile [@player]** — View your player profile and stats.\n"
                "**!player_retire** — Retire your player profile from the system.",
            inline=False
        )

        # -------------------------
        # TEAM MANAGEMENT COMMANDS
        # -------------------------
        embed.add_field(
            name="🛡 Team Management",
            value=
                "**!team_create <team name>** — Create a new team and become captain.\n"
                "**!team_invite <@player>** — Invite a player to join your team.\n"
                "**!team_view <team name>** — View details about a specific team.\n"
                "**!team_leave** — Leave your current team.\n"
                "**!team_kick <@player>** — (Captain only) Kick a player from your team.\n"
                "**!team_delete** — (Captain only) Delete your team.",
            inline=False
        )

        # -------------------------
        # MATCH COMMANDS
        # -------------------------
        embed.add_field(
            name="⚔ Match Commands",
            value=
                "**!match_invite <team name> [side]** — (Captain only) Invite another team to a match.\n"
                "**!match_update <match id> <screenshot>** — (Captain only) Submit match result for admin review.",
            inline=False
        )

        # -------------------------
        # OTHER COMMANDS
        # -------------------------
        embed.add_field(
            name="📦 Other Commands",
            value=
                "**!leaderboard** — Show the top 10 teams by Elo.\n"
                "**!tutorial** — Shows a simple tutorial.\n"
                "**!commands** — Show this command list.",
            inline=False
        )

        await ctx.send(embed=embed, ephemeral=True)


    @commands.hybrid_command(name="tutorial", description="Shows a simple tutorial to get started.")
    async def tutorial(self, ctx):
            embed = discord.Embed(
                title="📘 LoL Customs — How to Use the Bot",
                description="Follow these steps to get started!",
                color=discord.Color.blurple()
            )

            embed.add_field(
                name="1️⃣ Create your player profile",
                value="`!player_register <summoner name>` — Register yourself as a player in the system.",
                inline=False
            )
            embed.add_field(
                name="2️⃣ Set your peak League rank",
                value="`!player_rank <rank>` — Determines your weight when forming or joining teams.",
                inline=False
            )
            embed.add_field(
                name="3️⃣ Join or create a team",
                value="**Option A: Become a captain**\n`!team_create <team name>`\n"
                    "**Option B: Join an existing team**\nAsk a captain to invite you: `!team_invite @player`",
                inline=False
            )
            embed.add_field(
                name="4️⃣ Invite another team to a match (Captain only)",
                value="`!match_invite <team name> [side]` — Wait for acceptance.",
                inline=False
            )
            embed.add_field(
                name="5️⃣ Remember the match ID",
                value="The bot provides a Match ID after acceptance — keep it for later.",
                inline=False
            )
            embed.add_field(
                name="6️⃣ Submit match results (Captain only)",
                value="`!match_update <match id> <screenshot>` — Attach screenshot to ping admin for review.",
                inline=False
            )
            embed.add_field(
                name="7️⃣ View your profile or leaderboard",
                value="`!player_profile [@player]` — View stats\n"
                    "`!leaderboard` — View top teams",
                inline=False
            )

            await ctx.send(embed=embed, ephemeral=True)
            

async def setup(bot, db):
    await bot.add_cog(PlayerCog(bot, db))

