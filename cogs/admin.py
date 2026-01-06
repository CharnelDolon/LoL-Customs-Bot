import discord
from discord.ext import commands
from utils.elo import calculate_expected_elo, update_elo_weighted
from utils.embeds import error_embed, success_embed

ADMIN_ROLE_NAME = "Admin"

class Admin(commands.Cog):
    def __init__(self, bot, db):
        self.bot = bot
        self.db = db  # Shared Database instance

    # Utility: check if user is admin
    async def admin_check(self, interaction: discord.Interaction):
        if interaction.user.guild_permissions.administrator:
            return True
        role = discord.utils.get(interaction.user.roles, name=ADMIN_ROLE_NAME)
        return role is not None

    # ---------------------------
    # /admin_reset
    # ---------------------------
    @commands.hybrid_command(name="admin_reset", description="Reset ELO for all teams (Admin only)")
    async def admin_reset(self, ctx):
        if not ctx.author.guild_permissions.administrator:
            role = discord.utils.get(ctx.author.roles, name=ADMIN_ROLE_NAME)
            if not role:
                return await ctx.send(embed=error_embed("You do not have permission."), ephemeral=True)

        self.db.execute("UPDATE teams SET elo = 1000, wins = 0, losses = 0")
        self.db.conn.commit()
        await ctx.send(embed=success_embed("✅ All team ELO reset to 1000."))

    # ---------------------------
    # /admin_delete_team
    # ---------------------------
    @commands.hybrid_command(name="admin_delete_team", description="Forcefully delete a team (Admin only)")
    async def admin_delete_team(self, ctx, team_name: str):
        if not ctx.author.guild_permissions.administrator:
            role = discord.utils.get(ctx.author.roles, name=ADMIN_ROLE_NAME)
            if not role:
                return await ctx.send(embed=error_embed("You do not have permission."), ephemeral=True)

        team = self.db.fetch_one("SELECT team_id, team_name FROM teams WHERE team_name=?", (team_name,))
        if not team:
            return await ctx.send(embed=error_embed(f"Team `{team_name}` does not exist."), ephemeral=True)

        team_id = team["team_id"]

        # Remove players from team
        self.db.execute("UPDATE players SET current_team_id = NULL WHERE current_team_id=?", (team_id,))
        # Delete team and members
        self.db.execute("DELETE FROM teams WHERE team_id=?", (team_id,))
        self.db.execute("DELETE FROM team_members WHERE team_id=?", (team_id,))
        self.db.conn.commit()

        # After deleting from DB, delete the Discord channel
        # Assumes the channel name is same as team_name, lowercased and no spaces
        team_channel = discord.utils.get(ctx.guild.text_channels, name=team_name.lower().replace(" ", "-"))
        if team_channel:
            try:
                await team_channel.delete(reason="Admin deleted the team")
            except discord.Forbidden:
                await ctx.send(embed=error_embed(f"⚠️ Cannot delete channel `{team_channel.name}` due to permissions."))
            except discord.HTTPException as e:
                await ctx.send(embed=error_embed(f"⚠️ Failed to delete channel `{team_channel.name}`: {e}"))

        await ctx.send(embed=success_embed(f"✅ Team `{team_name}` has been deleted."))


    # ---------------------------
    # /admin_update
    # ---------------------------
    @commands.hybrid_command(name="admin_update", description="Admin verifies match and updates Elo")
    async def admin_update(self, ctx, match_id: int, winner_side: str):
        winner_side = winner_side.lower()
        if winner_side not in ["blue", "red"]:
            return await ctx.send("❌ Winner side must be `blue` or `red`.", ephemeral=True)

        # Fetch match
        match = self.db.fetch_one("SELECT * FROM matches WHERE match_id=?", (match_id,))
        if not match:
            return await ctx.send("❌ Match not found.", ephemeral=True)

        # Fetch both teams
        team1 = self.db.fetch_one(
            "SELECT team_id, team_name, elo, wins, losses, avg_weight FROM teams WHERE team_id=?",
            (match["team1_id"],)
        )
        team2 = self.db.fetch_one(
            "SELECT team_id, team_name, elo, wins, losses, avg_weight FROM teams WHERE team_id=?",
            (match["team2_id"],)
        )

        # Determine winner/loser based on side
        if winner_side == "blue":
            winner, loser = team1, team2
        else:
            winner, loser = team2, team1

        winner_weight = float(winner["avg_weight"] or 0)
        loser_weight = float(loser["avg_weight"] or 0)

        # --- Elo calculation functions ---
        def elo_expected_score(r1, r2):
            return 1 / (1 + 10 ** ((r2 - r1) / 400))

        def calculate_weight_modifier(diff):
            diff = abs(diff)
            if diff <= 0.3:
                return 1 + (diff / 0.3) * 0.1
            scale = (diff - 0.3) * 0.75
            return 1.15 ** (scale * 4)

        def weighted_elo_gain(team_elo, opp_elo, team_weight, opp_weight, base=20):
            expected = elo_expected_score(team_elo, opp_elo)
            chess_gain = base * (1 - expected)
            weight_diff = team_weight - opp_weight
            weight_modifier = calculate_weight_modifier(weight_diff)
            if weight_diff > 0:
                final = chess_gain / weight_modifier
            else:
                final = chess_gain * weight_modifier
            return max(1, round(final))

        # Calculate Elo deltas
        winner_delta = weighted_elo_gain(
            winner["elo"], loser["elo"], winner_weight, loser_weight
        )
        loser_delta = weighted_elo_gain(
            loser["elo"], winner["elo"], loser_weight, winner_weight
        )

        # Update winner/loser Elo and stats
        self.db.execute(
            "UPDATE teams SET elo=?, wins=? WHERE team_id=?",
            (winner["elo"] + winner_delta, winner["wins"] + 1, winner["team_id"])
        )
        self.db.execute(
            "UPDATE teams SET elo=?, losses=? WHERE team_id=?",
            (max(loser["elo"] - loser_delta, 0), loser["losses"] + 1, loser["team_id"])
        )

        # Update peak Elo for all players
        for team in [winner, loser]:
            players = self.db.fetch_all(
                "SELECT discord_id, peak_team_elo FROM players WHERE current_team_id=?",
                (team["team_id"],)
            )
            for p in players:
                if team["elo"] > (p["peak_team_elo"] or 0):
                    self.db.execute(
                        "UPDATE players SET peak_team_elo=? WHERE discord_id=?",
                        (team["elo"], p["discord_id"])
                    )

        # --- Delete match after updating Elo ---
        self.db.execute("DELETE FROM matches WHERE match_id=?", (match_id,))
        self.db.conn.commit()

        # Send result embed
        embed = discord.Embed(
            title=f"✅ Match #{match_id} Completed",
            description=f"Winner: **{winner['team_name']}**\nLoser: **{loser['team_name']}**",
            color=discord.Color.green()
        )
        embed.add_field(
            name="Elo Change",
            value=(f"{winner['team_name']}: 🟢 +{winner_delta}\n"
                f"{loser['team_name']}: 🔴 -{loser_delta}"),
            inline=False
        )
        embed.add_field(
            name="New Elo",
            value=(f"{winner['team_name']}: {winner['elo'] + winner_delta}\n"
                f"{loser['team_name']}: {max(loser['elo'] - loser_delta, 0)}"),
            inline=False
        )

        await ctx.send(embed=embed)

# ---------------------------
# Setup
# ---------------------------
async def setup(bot, db):
    await bot.add_cog(Admin(bot, db))
