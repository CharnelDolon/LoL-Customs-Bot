import discord
from discord.ext import commands
from discord.ui import View, Button

class Teams(commands.Cog):
    def __init__(self, bot, db):
        self.bot = bot
        self.db = db  # Shared database instance

    # ---------------------------
    # /team_create <team_name>
    # ---------------------------
    @commands.hybrid_command(name="team_create", description="Create a new team and become its captain")
    async def team_create(self, ctx, *, team_name: str):
        user_id = ctx.author.id

        # Require complete profile
        profile = self.db.fetch_one(
            "SELECT summoner_name, rank_tier, weight FROM players WHERE discord_id=?",
            (user_id,)
        )
        if not profile or not profile["summoner_name"] or not profile["rank_tier"]:
            return await ctx.send("❌ You must complete your profile before creating a team.", ephemeral=True)

        # Check if user already owns a team
        existing_team = self.db.fetch_one(
            "SELECT team_id FROM teams WHERE captain_id=?", (user_id,)
        )
        if existing_team:
            return await ctx.send("❌ You already have a team!", ephemeral=True)

        # Check if name is taken
        existing_name = self.db.fetch_one(
            "SELECT team_id FROM teams WHERE team_name=?", (team_name,)
        )
        if existing_name:
            return await ctx.send("❌ A team with that name already exists.", ephemeral=True)

        # Create team
        self.db.execute(
            "INSERT INTO teams (team_name, captain_id, elo, wins, losses, avg_weight) VALUES (?, ?, 1000, 0, 0, ?)",
            (team_name, user_id, float(profile["weight"] or 0))
        )
        team_id = self.db.cursor.lastrowid

        # Update player's current_team_id
        self.db.execute(
            "UPDATE players SET current_team_id=? WHERE discord_id=?",
            (team_id, user_id)
        )

        # Recalculate avg_weight for team (in case more players join later)
        self.db.execute("""
            UPDATE teams SET avg_weight = (
                SELECT AVG(weight)
                FROM players
                WHERE current_team_id = ?
            )
            WHERE team_id = ?
        """, (team_id, team_id))

        # Create role
        guild = ctx.guild
        role = await guild.create_role(name=team_name, mentionable=True)
        await ctx.author.add_roles(role)

        # Create channel
        category = discord.utils.get(guild.categories, name="Team")
        if not category:
            category = await guild.create_category("Team")

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            role: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }
        await guild.create_text_channel(team_name, category=category, overwrites=overwrites)

        await ctx.send(f"✅ Team **{team_name}** created with captain {ctx.author.display_name}!")

    # ----------------------------
    # /team_delete
    # ----------------------------
    @commands.hybrid_command(name="team_delete", description="Delete your team (captain only)")
    async def team_delete(self, ctx):
        user_id = str(ctx.author.id)
        team = self.db.fetch_one("SELECT team_id, team_name FROM teams WHERE captain_id=?", (user_id,))
        if not team:
            return await ctx.send("❌ You are not a captain.", ephemeral=True)

        team_id, team_name = team

        # Remove current_team_id from all players
        self.db.execute("UPDATE players SET current_team_id=NULL WHERE current_team_id=?", (team_id,))
        # Delete team
        self.db.execute("DELETE FROM teams WHERE team_id=?", (team_id,))

        # Delete role
        role = discord.utils.get(ctx.guild.roles, name=team_name)
        if role:
            await role.delete()

        # Delete channel
        channel = discord.utils.get(ctx.guild.text_channels, name=team_name.lower())
        if channel:
            await channel.delete()

        await ctx.send(f"🗑 Team **{team_name}** deleted.")

    # ----------------------------
    # /team_leave
    # ----------------------------
    @commands.hybrid_command(name="team_leave", description="Leave your team")
    async def team_leave(self, ctx):
        user_id = str(ctx.author.id)
        player = self.db.fetch_one("SELECT current_team_id FROM players WHERE discord_id=?", (user_id,))
        if not player or not player["current_team_id"]:
            return await ctx.send("❌ You are not in a team.", ephemeral=True)

        team_id = player["current_team_id"]
        team = self.db.fetch_one("SELECT team_name, captain_id FROM teams WHERE team_id=?", (team_id,))

        if team["captain_id"] == int(user_id):
            return await ctx.send("❌ Captains must delete their team instead.", ephemeral=True)

        # Remove from team
        self.db.execute("UPDATE players SET current_team_id=NULL WHERE discord_id=?", (user_id,))

        # Recalculate avg_weight
        self.db.execute("""
            UPDATE teams SET avg_weight = (
                SELECT AVG(weight)
                FROM players
                WHERE current_team_id = ?
            )
            WHERE team_id = ?
        """, (team_id, team_id))
        self.db.conn.commit()

        # Remove role
        role = discord.utils.get(ctx.guild.roles, name=team["team_name"])
        if role:
            await ctx.author.remove_roles(role)

        await ctx.send("✅ You left your team.")

    # ----------------------------
    # /team_invite
    # ----------------------------
    @commands.hybrid_command(name="team_invite",
                             description="Invite a player to your team")
    async def player_invite(self, ctx, target: discord.Member):
        inviter_id = ctx.author.id
        target_id = target.id

        # Fetch inviter's team
        team = self.db.fetch_one(
            "SELECT team_id, team_name, captain_id FROM teams WHERE captain_id=?",
            (inviter_id, ))
        if not team:
            return await ctx.send("❌ You must be a captain to invite players.",
                                  ephemeral=True)

        # Check if target player already has a team
        target_player = self.db.fetch_one(
            "SELECT discord_id, current_team_id FROM players WHERE discord_id=?",
            (target_id, ))
        if target_player and target_player['current_team_id']:
            return await ctx.send(
                f"❌ {target.display_name} is already in a team.",
                ephemeral=True)

        # Check how many players are already in the team
        player_count = self.db.fetch_one(
            "SELECT COUNT(*) FROM players WHERE current_team_id=?",
            (team['team_id'], ))[0]

        if player_count >= 5:
            return await ctx.send(
                f"❌ `{team['team_name']}` already has **{player_count}/5** players.\n"
                f"No more players can be invited.",
                ephemeral=True)

        # ----------------------------
        # Invite buttons
        # ----------------------------
        class InviteView(View):

            def __init__(self, bot, db, team, target_id):
                super().__init__(timeout=None)
                self.bot = bot
                self.db = db
                self.team = team
                self.target_id = target_id

            @discord.ui.button(label="Accept ✅",
                               style=discord.ButtonStyle.green)
            async def accept(self, interaction: discord.Interaction,
                             button: Button):
                if interaction.user.id != self.target_id:
                    return await interaction.response.send_message(
                        "❌ Only the invited player can accept.",
                        ephemeral=True)
                # Update player's team
                self.db.execute(
                    "UPDATE players SET current_team_id=? WHERE discord_id=?",
                    (self.team['team_id'], self.target_id))

                # ----------------------------
                # Recalculate avg_weight for the team
                # ----------------------------
                self.db.execute(
                    """
                    UPDATE teams SET avg_weight = (
                        SELECT AVG(weight)
                        FROM players
                        WHERE current_team_id = ?
                    )
                    WHERE team_id = ?
                """, (self.team['team_id'], self.team['team_id']))

                self.db.conn.commit()
                await interaction.response.edit_message(
                    content=
                    f"✅ {interaction.user.mention} has joined {self.team['team_name']}!",
                    view=None)

            @discord.ui.button(label="Decline ❌",
                               style=discord.ButtonStyle.red)
            async def decline(self, interaction: discord.Interaction,
                              button: Button):
                if interaction.user.id != self.target_id:
                    return await interaction.response.send_message(
                        "❌ Only the invited player can decline.",
                        ephemeral=True)
                await interaction.response.edit_message(
                    content=
                    f"❌ {interaction.user.mention} declined the team invite.",
                    view=None)

        invite_view = InviteView(bot=self.bot,
                                 db=self.db,
                                 team=team,
                                 target_id=target_id)

        await ctx.send(
            content=
            f"{ctx.author.mention} has invited {target.mention} to join **{team['team_name']}**!",
            view=invite_view)

    # ----------------------------
    # /team_kick
    # ----------------------------
    @commands.hybrid_command(name="team_kick", description="Kick a teammate (captain only)")
    async def team_kick(self, ctx, member: discord.Member):
        captain_id = str(ctx.author.id)
        target_id = str(member.id)

        if captain_id == target_id:
            return await ctx.send("❌ You can't kick yourself. Use !team_delete command", ephemeral=True)

        team = self.db.fetch_one("SELECT team_id, team_name FROM teams WHERE captain_id=?", (captain_id,))
        if not team:
            return await ctx.send("❌ You are not a captain.", ephemeral=True)

        team_id = team["team_id"]
        target = self.db.fetch_one(
            "SELECT current_team_id FROM players WHERE discord_id=? AND current_team_id=?",
            (target_id, team_id)
        )
        if not target:
            return await ctx.send("❌ That player is not on your team.", ephemeral=True)

        # Remove from team
        self.db.execute("UPDATE players SET current_team_id=NULL WHERE discord_id=?", (target_id,))

        # Recalculate avg_weight
        self.db.execute("""
            UPDATE teams SET avg_weight = (
                SELECT AVG(weight)
                FROM players
                WHERE current_team_id = ?
            )
            WHERE team_id = ?
        """, (team_id, team_id))
        self.db.conn.commit()

        # Remove role
        role = discord.utils.get(ctx.guild.roles, name=team["team_name"])
        if role:
            await member.remove_roles(role)

        await ctx.send(f"🔨 {member.display_name} was kicked from the team.")

    # ----------------------------
    # /team_view
    # ----------------------------
    @commands.hybrid_command(name="team_view", description="View details about a specific team.")
    async def team_view(self, ctx, *, team_name: str):  # <-- * captures multi-word team names
        team = self.db.fetch_one("SELECT * FROM teams WHERE team_name=?", (team_name,))
        if not team:
            return await ctx.send(f"❌ Team `{team_name}` not found.", ephemeral=True)

        team_id = team["team_id"]
        players = self.db.fetch_all(
            "SELECT summoner_name, rank_tier, rank_score, discord_id FROM players WHERE current_team_id=?",
            (team_id,)
        )

        total_games = team["wins"] + team["losses"]
        winrate = f"{round(team['wins']/total_games*100,2)}%" if total_games else "0%"

        avg_weight = round(sum([p["rank_score"] for p in players]) / len(players), 2) if players else 0

        embed = discord.Embed(title=f"Team: {team_name}", color=discord.Color.blue())
        embed.add_field(name="Elo", value=str(team["elo"]))
        embed.add_field(name="Record", value=f"{team['wins']}/{team['losses']}")
        embed.add_field(name="Win Rate", value=winrate)
        embed.add_field(name="Avg Weight", value=str(avg_weight), inline=False)

        player_list = ""
        for p in players:
            name = p["summoner_name"] or "Unknown"
            rank = p["rank_tier"] or "N/A"
            score = p["rank_score"]
            captain_tag = " (Captain)" if p["discord_id"] == team["captain_id"] else ""
            player_list += f"• **{name}** – {rank} (Weight {score}){captain_tag}\n"

        embed.add_field(name=f"Players ({len(players)})", value=player_list or "None", inline=False)
        await ctx.send(embed=embed)

    # ----------------------------
    # /leaderboard
    # ----------------------------
    @commands.hybrid_command(name="leaderboard", description="Shows the top 10 teams by Elo")
    async def team_leaderboard(self, ctx):
        teams = self.db.fetch_all("""
            SELECT team_name, elo, wins, losses, avg_weight
            FROM teams
            ORDER BY elo DESC, team_name ASC
            LIMIT 10
        """)

        if not teams:
            await ctx.send("❌ No teams found.")
            return

        embed = discord.Embed(title="🏆 Top 10 Teams", color=discord.Color.gold())
        description = ""
        for rank, team in enumerate(teams, start=1):
            total_games = team["wins"] + team["losses"]
            win_rate = f"{round((team['wins']/total_games)*100,2)}%" if total_games else "0%"
            description += (
                f"**{rank}. {team['team_name']}** | Elo: {team['elo']} | Avg MMR: {team['avg_weight']} | "
                f"W/L: {team['wins']}/{team['losses']} | Win Rate: {win_rate}\n"
            )

        embed.description = description
        embed.set_footer(text="Top 10 teams by Elo.")
        await ctx.send(embed=embed)


async def setup(bot, db):
    await bot.add_cog(Teams(bot, db))
