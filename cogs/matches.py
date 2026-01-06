import discord
from discord.ext import commands
from discord.ui import View, Button
import random
from utils.elo import update_elo_weighted

class Matches(commands.Cog):
    def __init__(self, bot, db):
        self.bot = bot
        self.db = db  # Shared Database instance

   
    # ----------------------------
    # /match_invite
    # ----------------------------
    @commands.hybrid_command(name="match_invite", description="Invite another team to a match")
    async def match_invite(self,ctx,*,target_team_name: str,side: str = None):
        inviter_id = ctx.author.id

        # Fetch inviter's team
        team1 = self.db.fetch_one(
            "SELECT team_id, team_name, elo, captain_id, avg_weight FROM teams WHERE captain_id=?",
            (inviter_id, ))
        if not team1:
            return await ctx.send(
                "❌ You must be a captain to invite another team.",
                ephemeral=True)
        team1_id, team1_name, team1_elo, team1_captain, team1_weight = team1

        # Count players on inviter's team
        player_count1 = self.db.fetch_one(
            "SELECT COUNT(*) FROM players WHERE team_id=?", (team1_id, ))[0]

        if player_count1 < 5:
            return await ctx.send(
                f"❌ `{team1_name}` does not have 5 players.\n"
                f"Current players: **{player_count1}/5**",
                ephemeral=True)

        # Fetch target team
        team2 = self.db.fetch_one(
            "SELECT team_id, team_name, elo, captain_id, avg_weight FROM teams WHERE team_name=?",
            (target_team_name, ))
        if not team2:
            return await ctx.send(f"❌ Team `{target_team_name}` not found.",
                                  ephemeral=True)
        team2_id, team2_name, team2_elo, team2_captain, team2_weight = team2

        if team1_id == team2_id:
            return await ctx.send("❌ You cannot invite your own team.",
                                  ephemeral=True)

        team1_weight = float(team1_weight or 0)
        team2_weight = float(team2_weight or 0)

        # Determine sides
        sides = ["blue", "red"]
        team1_side = side.lower(
        ) if side and side.lower() in sides else random.choice(sides)
        team2_side = "red" if team1_side == "blue" else "blue"

        def elo_expected_score(r1, r2):
            return 1 / (1 + 10**((r2 - r1) / 400))

        def calculate_weight_modifier(diff):
            """
            Weight modifier using your scaling:
            - Ignore diff <= 0.65 (pure chess Elo)
            - Exponential scaling beyond that
            """
            diff = abs(diff)
            if diff <= 0.3:
                return 1 + (diff / 0.3) * 0.1

            # Convert weight diff (1–10 scale) into "league rank impact"
            # Based on empirical Riot MMR jumps:
            # 1 rank ≈ 200 MMR → 0.2 modifier scale
            scale = (diff - 0.3) * 0.75  # soft exponential

            return 1.15**(scale * 4)  # stronger exponential curve

        def weighted_elo_gain(team_elo,
                              opp_elo,
                              team_weight,
                              opp_weight,
                              base=20):
            # Pure chess expected win rate
            expected = elo_expected_score(team_elo, opp_elo)

            # Chess-based gain/loss
            chess_gain = base * (1 - expected)

            # Weight modifier
            weight_diff = team_weight - opp_weight
            weight_modifier = calculate_weight_modifier(weight_diff)

            # If stronger team (positive diff), they gain LESS
            if weight_diff > 0:
                final = chess_gain / weight_modifier
            else:
                final = chess_gain * weight_modifier

            return max(1, round(final))

        # Team 1 win / lose
        delta_win_team1 = weighted_elo_gain(team1_elo, team2_elo, team1_weight,
                                            team2_weight)
        delta_lose_team1 = weighted_elo_gain(team2_elo, team1_elo,
                                             team2_weight, team1_weight)

        # Team 2 win / lose
        delta_win_team2 = weighted_elo_gain(team2_elo, team1_elo, team2_weight,
                                            team1_weight)
        delta_lose_team2 = weighted_elo_gain(team1_elo, team2_elo,
                                             team1_weight, team2_weight)

        # Insert match into DB
        self.db.execute(
            "INSERT INTO matches (team1_id, team2_id, team1_side, team2_side) VALUES (?, ?, ?, ?)",
            (team1_id, team2_id, team1_side, team2_side))
        self.db.conn.commit()
        match_id = self.db.cursor.lastrowid

        # Build embed
        embed = discord.Embed(
            title=f"Match Invitation: {team1_name} vs {team2_name}",
            description=
            f"Team `{team1_name}` ({team1_side}) vs Team `{team2_name}` ({team2_side})",
            color=discord.Color.blue())
        embed.add_field(
            name=f"{team1_name} Elo",
            value=f"{team1_elo} | 🟢 +{delta_win_team1} / 🔴 -{delta_lose_team1}",
            inline=True)
        embed.add_field(
            name=f"{team2_name} Elo",
            value=f"{team2_elo} | 🟢 +{delta_win_team2} / 🔴 -{delta_lose_team2}",
            inline=True)
        embed.set_footer(text=f"Match ID: {match_id}")

        # Invite buttons
        class InviteView(View):

            def __init__(self, cog):
                super().__init__(timeout=60)
                self.cog = cog

            @discord.ui.button(label="Accept", style=discord.ButtonStyle.green)
            async def accept(self, interaction: discord.Interaction,
                             button: Button):
                if interaction.user.id != team2_captain:
                    return await interaction.response.send_message(
                        "❌ Only the invited team's captain can accept.",
                        ephemeral=True)
                await interaction.response.edit_message(
                    content=
                    f"✅ Match accepted by {team2_name}! Match ID: {match_id}",
                    view=None)

            @discord.ui.button(label="Decline", style=discord.ButtonStyle.red)
            async def decline(self, interaction: discord.Interaction,
                              button: Button):
                if interaction.user.id != team2_captain:
                    return await interaction.response.send_message(
                        "❌ Only the invited team's captain can decline.",
                        ephemeral=True)
                self.cog.db.execute("DELETE FROM matches WHERE match_id=?",
                                    (match_id, ))
                self.cog.db.conn.commit()
                await interaction.response.edit_message(
                    content=f"❌ Match declined by {team2_name}.", view=None)

        target_captain_user = ctx.guild.get_member(team2_captain)
        if not target_captain_user:
            return await ctx.send(
                f"❌ The captain of `{team2_name}` is not in this server.",
                ephemeral=True)

        await ctx.send(
            content=
            f"{ctx.author.mention} invites {target_captain_user.mention} to a match!",
            embed=embed,
            view=InviteView(self))
            
    # ----------------------------
    # /match_update
    # ----------------------------
    @commands.hybrid_command(name="match_update", description="Submit match result for admin verification")
    async def match_update(self, ctx, match_id: int):
        user_id = ctx.author.id

        # Fetch match
        match = self.db.fetch_one("SELECT * FROM matches WHERE match_id=?", (match_id,))
        if not match:
            return await ctx.send("❌ Match not found.", ephemeral=True)

        team1_id = match["team1_id"]
        team2_id = match["team2_id"]

        # Fetch teams
        team1 = self.db.fetch_one("SELECT team_name, captain_id FROM teams WHERE team_id=?", (team1_id,))
        team2 = self.db.fetch_one("SELECT team_name, captain_id FROM teams WHERE team_id=?", (team2_id,))

        # Check if author is captain of either team
        if user_id not in (team1["captain_id"], team2["captain_id"]):
            return await ctx.send("❌ Only a captain of either team can report the match.", ephemeral=True)

        # Ensure a screenshot is attached
        if not ctx.message.attachments:
            return await ctx.send("❌ Please attach a screenshot of the match result.", ephemeral=True)

        screenshot = ctx.message.attachments[0].url

        # Build embed for admin
        embed = discord.Embed(
            title=f"Match Result Submission: Match #{match_id}",
            description=f"Teams: **{team1['team_name']}** vs **{team2['team_name']}**",
            color=discord.Color.orange()
        )
        embed.set_image(url=screenshot)
        embed.set_footer(text=f"Submitted by: {ctx.author.display_name}")

        # Ping Admin role
        admin_role = discord.utils.get(ctx.guild.roles, name="Admin")
        if admin_role:
            await ctx.send(content=f"{admin_role.mention} New match result submitted!", embed=embed)
        else:
            await ctx.send(embed=embed)


# -----------------------------
# Setup
# -----------------------------
async def setup(bot, db):
    await bot.add_cog(Matches(bot, db))
