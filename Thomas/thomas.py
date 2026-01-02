import discord
from discord.ext import commands
from discord.ui import View, Button
import os
from dotenv import load_dotenv

load_dotenv("Thomas/TOKENS.env")
TOKEN = os.getenv("TOKEN")

REPORT_CATEGORY_NAME = "Reports"

# ----- Intents -----

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ----- Helper -----

async def get_or_create_category(guild):
    category = discord.utils.get(guild.categories, name=REPORT_CATEGORY_NAME)
    if not category:
        category = await guild.create_category(REPORT_CATEGORY_NAME)
    return category


def user_has_channel(category, member):
    for channel in category.text_channels:
        if member in channel.overwrites:
            return channel
    return None

# ----- UI View -----

class ReportView(View):
    def __init__(self):
        super().__init__(timeout=None)

    async def create_channel(self, interaction, prefix):
        guild = interaction.guild
        member = interaction.user
        category = await get_or_create_category(guild)


        mod_role = guild.get_role(1455519147948638249)
        if mod_role is None:
            await interaction.response.send_message(
                "❌ Mod role not found. Check the role ID.",
                ephemeral=True
            )
            return

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            member: discord.PermissionOverwrite(view_channel=True, send_messages=True),
            mod_role: discord.PermissionOverwrite(view_channel=True, send_messages=True)
        }

        channel = await guild.create_text_channel(
            f"{prefix}-{member.name}".lower(),
            overwrites=overwrites,
            category=category
        )

        await interaction.response.send_message(
            f"✅ Report created: {channel.mention}",
            ephemeral=True
        )

        await channel.send(
            f"{mod_role.mention} {member.mention}"
        )

    @discord.ui.button(label="Player Report", style=discord.ButtonStyle.green, custom_id="Player Report")
    async def player_report(self, interaction: discord.Interaction, button: Button):
        await self.create_channel(interaction, "player-report")

    @discord.ui.button(label="Bug Report", style=discord.ButtonStyle.red,custom_id="Bug Report")
    async def bug_report(self, interaction: discord.Interaction, button: Button):
        await self.create_channel(interaction, "bug-report")

    @discord.ui.button(label="Other", style=discord.ButtonStyle.blurple, custom_id="Other")
    async def other(self, interaction: discord.Interaction, button: Button):
        await self.create_channel(interaction, "other")

# ----- Command -----

@bot.command()
async def report_ui(ctx):
    await ctx.send(
        "Use the buttons below to create a report channel:",
        view=ReportView()
    )


bot.run(TOKEN)
