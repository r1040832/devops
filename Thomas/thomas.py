import discord
from discord.ext import commands
from discord.ui import View, Button
import os
from dotenv import load_dotenv
import re
import aiomysql
import asyncio

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


    
# ----- On ready: start auto task -----
@bot.event
async def on_ready():
    await refresh_banned_words()
    print(f"Bot logged in as {bot.user}. Banned words loaded.")
    # Start the auto insult task
    bot.loop.create_task(auto_insult_channel())



# ----- Regex Patterns for tricky words -----

REGEX_PATTERNS = [
    re.compile(r"i[dD1]i[o0]t"),
    re.compile(r"loser"),
    re.compile(r"f[u*]ck(er|ing)?"),
    re.compile(r"sh[i1]t"),
    re.compile(r"b[i1]tch"),
]

# ------------------------------

BANNED_WORDS_CACHE = []

async def refresh_banned_words():
    global BANNED_WORDS_CACHE
    BANNED_WORDS_CACHE = await get_banned_words()

# Call once at startup
@bot.event
async def on_ready():
    await refresh_banned_words()
    print("Banned words loaded into cache.")


# ------------------------------
# MySQL Connection Pool Setup
# ------------------------------

mysql_pool = None # Global pool variable

async def init_pool():
    global mysql_pool
    if mysql_pool is None:
        mysql_pool = await aiomysql.create_pool(
            host=os.getenv("host"),
            user=os.getenv("user"),
            password=os.getenv("password"),
            db=os.getenv("db"),
            autocommit=True
        )

# ----- Fetch banned words from MySQL -----

async def get_banned_words():
    await init_pool()
    banned_words = []
    async with mysql_pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT word FROM banned_words")
            result = await cur.fetchall()
            banned_words = [row[0] for row in result]
    return banned_words

# ----- Helper: get/create category -----

async def get_or_create_category(guild):
    category = discord.utils.get(guild.categories, name=REPORT_CATEGORY_NAME)
    if not category:
        category = await guild.create_category(REPORT_CATEGORY_NAME)
    return category

# ----- Check messages -----

async def check_message_content(message, banned_words):
    # 1️⃣ Regex check
    for pattern in REGEX_PATTERNS:
        if pattern.search(message.content):
            return f"Matched regex: {pattern.pattern}"

    # 2️⃣ Check against MySQL list
    for word in banned_words:
        if word.lower() in message.content.lower():
            return f"Matched banned word from MySQL: {word}"

    return None

# ----- On message -----

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    banned_words = await get_banned_words()
    reason = await check_message_content(message, BANNED_WORDS_CACHE)


    if reason:
        # Extract words that match your regex
        words_in_message = re.findall(r'\w+', message.content)
        for word in words_in_message:
            for pattern in REGEX_PATTERNS:
                if pattern.search(word) and word.lower() not in [w.lower() for w in banned_words]:
                    await add_word_to_mysql(word)

        # Report message
        guild = message.guild
        report_category = await get_or_create_category(guild)
        report_channel = discord.utils.get(report_category.text_channels, name="msg-report")
        if not report_channel:
            report_channel = await guild.create_text_channel(
                "msg-report",
                category=report_category,
                overwrites={guild.default_role: discord.PermissionOverwrite(view_channel=True)}
            )

        await report_channel.send(
            f"⚠️ Deleted message from {message.author.mention}:\n"
            f"Content: \"{message.content}\"\n"
            f"Reason: {reason}"
        )

        await message.delete()
        return

    await bot.process_commands(message)
    
# ----- Add word to MySQL -----

async def add_word_to_mysql(word: str):
    """Add a new word to the banned_words table if it doesn't exist."""
    word = word.lower().strip()  # sanitize
    await init_pool()
    async with mysql_pool.acquire() as conn:
        async with conn.cursor() as cur:
            # Check if word exists
            await cur.execute("SELECT 1 FROM banned_words WHERE word=%s", (word,))
            exists = await cur.fetchone()
            if exists:
                return  # Already exists

            # Insert the new word
            await cur.execute("INSERT INTO banned_words (word) VALUES (%s)", (word,))
            print(f"Added new banned word to MySQL: {word}")

async def auto_insult_channel():
    await bot.wait_until_ready()  # Make sure bot is online
    channel_id = 123456789012345678  # Replace with your Discord channel ID
    channel = bot.get_channel(channel_id)
    if channel is None:
        print("Channel not found")
        return

    while not bot.is_closed():
        words = []
        await init_pool()
        async with mysql_pool.acquire() as conn:
            async with conn.cursor() as cur:
                for _ in range(4):
                    await cur.execute("SELECT word FROM banned_words ORDER BY RAND() LIMIT 1")
                    result = await cur.fetchone()
                    if result:
                        words.append(result[0])
        await channel.send(f"💬 Random insult: {' '.join(words)}")
        await asyncio.sleep(300)  # Wait 5 minutes


@bot.command()
async def refreshin(ctx):
    # Refresh the banned words cache from MySQL
    await refresh_banned_words()

# ----- Run Bot -----

bot.run(TOKEN)
