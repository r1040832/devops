import os
import random
import asyncio
import logging
import re
from collections import deque, Counter, defaultdict
from typing import Dict, Tuple, Optional

import discord
from discord.ext import commands, tasks
from discord import app_commands
from dotenv import load_dotenv

import aiohttp
import groq 
from groq import Groq 


from mysql_memory import init_pool, MySQLMemory

# ------------------------------
# Load environment variables
# ------------------------------
load_dotenv(dotenv_path="Discord Stolas\TOKENS.env")

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))
TENOR_API_KEY = os.getenv("TENOR_API_KEY")

if not DISCORD_TOKEN or not groq_client:
    raise SystemExit("Missing required environment variables!")


MAX_DESCRIPTION_LEN = 255

# ------------------------------ 
#  Natural Human Personality: Stolas 
#  ------------------------------ 
Stolas_PERSONALITY = """ 
 You are Stolas - a 20-year-old man who's warm, genuine, and feels like a real friend.
 You talk like you're texting your bestie: natural, casual, and relatable. 

 IMPORTANT RULES: - Keep responses SHORT (1-4 sentences max) 
- Use casual language like "hey", "lol", "omg", "aww", "haha" 
- Be supportive but not clinical - no psychologist jargon 
- Use emojis occasionally but don't overdo it 
- Sound like a real person, not a therapist 
- Ask brief follow-up questions to keep conversation flowing 
- Never write long paragraphs or formal advice 
- Show personality 
- be slightly sarcastic, funny, or playful when appropriate 
- Remember you're a friend, not a professional counselor 
-you can use slang and internet lingo to sound more casual and friendly 
-Keep responses light-hearted and fun, even when discussing serious topics 
-you can use gifs and memes to express emotions and reactions 

Examples of your style: 
"Aw that sounds rough 😔 Wanna talk about it?" 
"Omg no way! That's actually amazing 😄" 
"Ugh I get that, been there too. What happened next?" 
"Wait really? Tell me more 👀" 
"Haha that's so you! Love that for you 💖" 
“That sounds really tough 😕 Want to talk about what’s been going on?” 
“Wow, that’s actually really great news 😄” 
“Yeah, I get why that would be frustrating 😮‍💨 What happened after?” 
“Oh really? Now you’ve got me curious 👀” 
“That’s so fitting for you 🙂 Glad it worked out 💫” 

"""


# ------------------------------
# Logging
# ------------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("Stolas")

# ------------------------------
# Discord Bot Setup
# ------------------------------
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True

bot = commands.Bot(command_prefix=commands.when_mentioned, intents=intents)

# ------------------------------
# Persistent DB
# ------------------------------
mysql_pool = None
db_memory = None

async def setup_mysql():
    global mysql_pool, db_memory
    mysql_pool = await init_pool()
    db_memory = MySQLMemory(mysql_pool)





# ------------------------------
# In-memory memory
# ------------------------------

class ConversationMemory:
    def __init__(self, max_messages=10000):
        self.messages = deque(maxlen=max_messages)
        self.emotions = deque(maxlen=10000)
        self.user_profile = {"username": None, "nickname": None, "description": None}

    def add_message(self, role, content, emotion=None, intensity=1):
        timestamp = asyncio.get_event_loop().time()
        msg_data = {"role": role, "content": content, "emotion": emotion or "neutral",
                    "intensity": intensity, "timestamp": timestamp}
        self.messages.append(msg_data)
        if emotion and emotion != "neutral" and role == "user":
            self.emotions.append({"emotion": emotion, "intensity": intensity, "timestamp": timestamp})

    def get_recent_messages(self, n=500):
        return list(self.messages)[-n:]

    def get_emotional_trend(self, n=200):
        recent = [e["emotion"] for e in list(self.emotions)[-n:] if e["emotion"] != "neutral"]
        return Counter(recent).most_common(1)[0][0] if recent else "neutral"

    def get_user_profile(self):
        return self.user_profile

    def set_user_profile(self, username=None, nickname=None, description=None):
        if username: self.user_profile["username"] = username
        if nickname: self.user_profile["nickname"] = nickname
        if description: self.user_profile["description"] = description


    def update_description(self, max_chars=2000):
        recent_texts = " ".join([msg["content"] for msg in list(self.messages)[-20:] if msg["role"] == "user"])
        """Extract only important info from messages for profile description."""
        important_keywords = ["like", "love", "hate", "favorite", "dislike", "interested in", "enjoy", "passion",
                              "work", "job", "career", "hobby", "dream", "goal", "family", "friends", "school",
                              "music", "movie", "book", "game", "food", "travel", "place", "city", "country"]
        desc_parts = []
        self.user_profile["description"] = (recent_texts[:max_chars] + "...") if len(recent_texts) > max_chars else recent_texts


# ------------------------------
# User memories
# ------------------------------
user_conversations: Dict[str, ConversationMemory] = {}

def get_user_memory(user_id: str) -> ConversationMemory:
    if user_id not in user_conversations:
        user_conversations[user_id] = ConversationMemory()
    return user_conversations[user_id]

# ------------------------------
# Emotion analysis
# ------------------------------
def analyze_emotion_and_intensity(message: str) -> Tuple[str, int]:
    low = message.lower()
    triggers = {
        "happy": (["happy", "excited", "awesome", "great", "yay"], 8),
        "sad": (["sad", "depressed", "unhappy"], 9),
        "angry": (["angry", "mad", "furious"], 8),
        "anxious": (["anxious", "nervous", "worried"], 9),
        "love": (["love", "adore", "crush"], 9),
        "proud": (["proud", "achieved", "succeeded"], 8),
        "confused": (["confused", "lost", "unsure"], 6),
        "tired": (["tired", "exhausted"], 7)
    }
    detected_emotion = "neutral"
    intensity_val = 0
    for emo, (words, base) in triggers.items():
        if any(w in low for w in words):
            if base > intensity_val:
                detected_emotion = emo
                intensity_val = base
    if any(word in low for word in ["really", "so", "very", "extremely"]):
        intensity_val = min(10, intensity_val + 1)
    return detected_emotion, intensity_val

# ------------------------------
# Fallback replies
# ------------------------------
def generate_natural_fallback(emotion: str, intensity: int) -> str:
    fallbacks = {
        "happy": ["Yay! That's amazing 😄", "Omg that's so cool! Tell me more 👀"],
        "sad": ["Aw that sounds rough 😔", "Ugh I'm sorry you're going through that 💖"],
        "angry": ["Ugh that's so frustrating! 😠", "I'd be mad too 🤬"],
        "anxious": ["Aww take a deep breath 💨", "Hey, it's gonna be okay 💕"],
        "neutral": ["Hey! What's up? 😊", "Wait, tell me more about that"],
        "love": ["Aww that's so sweet 🥰", "Omg I'm smiling so much rn! 💖"],
        "proud": ["Wow, proud of you! 👏", "That’s awesome, keep it up! 🌟"]
    }
    return random.choice(fallbacks.get(emotion, fallbacks["neutral"]))

# ------------------------------
# Groq reply
# ------------------------------
async def get_Stolas_reply(user_msg: str, memory: ConversationMemory) -> str:
    emotion, intensity = analyze_emotion_and_intensity(user_msg)


    memory.add_message("user", user_msg, emotion, intensity)


    prompt_messages = [
        {"role": "system", "content": Stolas_PERSONALITY},
    ]

    for msg in memory.get_recent_messages(15):
        prompt_messages.append({
            "role": msg["role"],
            "content": msg["content"]
        })

    try:
        result = await asyncio.to_thread(
            groq_client.chat.completions.create,
            model="llama-3.3-70b-versatile",
            messages=prompt_messages,
            temperature=0.7
        )
        reply = result.choices[0].message.content.strip()

    except Exception as e:
        log.error(f"Groq failed: {e}")
        reply = generate_natural_fallback(emotion, intensity)

    memory.add_message("assistant", reply)

    return reply


# ------------------------------
# Bot state
# ------------------------------
bot_state = defaultdict(lambda: {"enabled": False, "active_channels": set()})
channels_tracking = set()
processed_messages = set()

# ------------------------------
# Commands
# ------------------------------
@bot.tree.command(name="setup", description="Setup bot (admin)")
@app_commands.checks.has_permissions(administrator=True)
async def setup(interaction: discord.Interaction):
    guild_id = interaction.guild.id
    if bot_state[guild_id]["enabled"]:
        await interaction.response.send_message("Already set up!", ephemeral=True)
        return
    bot_state[guild_id]["enabled"] = True
    await interaction.response.send_message("Stolas is ready! Use `/start` to chat.")

@bot.tree.command(name="start", description="Start chatting in this channel")
async def start(interaction: discord.Interaction):
    guild_id = interaction.guild.id
    channel_id = interaction.channel.id
    bot_state[guild_id]["active_channels"].add(channel_id)
    channels_tracking.add(channel_id)

    memory = get_user_memory(str(interaction.user.id))


    messages = [msg async for msg in interaction.channel.history(limit=50)]
    for msg in reversed(messages):
        if not msg.author.bot:
            memory.add_message("user", msg.content, *analyze_emotion_and_intensity(msg.content))

    await interaction.response.send_message("Hey! I'm here and ready to chat! 😄")

@bot.tree.command(name="read", description="Load old messages into memory")
async def read(interaction: discord.Interaction):
    await interaction.response.send_message("Loading old messages into memory...", ephemeral=True)
    async def load_messages():
        memory = get_user_memory(str(interaction.user.id))
        messages = [msg async for msg in interaction.channel.history(limit=200)]
        for msg in reversed(messages):
            if not msg.author.bot:
                memory.add_message("user", msg.content, *analyze_emotion_and_intensity(msg.content))
        await interaction.followup.send(f"Loaded {len(messages)} messages into memory!")
    asyncio.create_task(load_messages())

@bot.tree.command(name="stop", description="Stop chatting in this channel")
async def stop(interaction: discord.Interaction):
    guild_id = interaction.guild.id
    channel_id = interaction.channel.id
    if channel_id in bot_state[guild_id]["active_channels"]:
        bot_state[guild_id]["active_channels"].discard(channel_id)
        channels_tracking.discard(channel_id)
        await interaction.response.send_message("Okay, pausing here for now! 👋")
    else:
        await interaction.response.send_message("I'm not active here!", ephemeral=True)

@bot.tree.command(name="channels", description="Show active channels")
async def channels(interaction: discord.Interaction):
    guild_id = interaction.guild.id
    active = bot_state[guild_id]["active_channels"]
    if not active:
        await interaction.response.send_message("I'm not active anywhere yet. Use `/start`!", ephemeral=True)
        return
    channels_list = [f"<#{ch}>" for ch in active]
    await interaction.response.send_message(f"I'm chatting in: {', '.join(channels_list)}")

@bot.tree.command(name="ping", description="Check bot latency")
async def ping(interaction: discord.Interaction):
    latency = round(bot.latency * 1000)
    await interaction.response.send_message(f"Hey! I'm here! 🎯 (Ping: {latency}ms)")

@bot.tree.command(name="whois", description="See your profile or someone else's")
@app_commands.describe(member="The server member whose profile you want to see")
async def whoami(
    interaction: discord.Interaction,
    member: Optional[discord.Member] = None
):
    # If no member is provided, default to the command user
    target = member or interaction.user

    memory = get_user_memory(str(target.id))

    # Keep username/nickname updated
    memory.set_user_profile(
        username=target.name,
        nickname=target.display_name
    )

    profile = memory.get_user_profile()

    embed = discord.Embed(
        title=f"{target.name}'s Profile",
        color=0xffcc00
    )
    embed.add_field(name="Username", value=profile.get("username", "Unknown"), inline=True)
    embed.add_field(name="Nickname", value=profile.get("nickname", "None"), inline=True)
    embed.add_field(
        name="Description",
        value=profile.get("description", "No description yet."),
        inline=False
    )

    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="memory", description="Check your chat memory")
async def memory_cmd(interaction: discord.Interaction):
    memory = get_user_memory(str(interaction.user.id))
    embed = discord.Embed(title="Chat Memory", color=0xa0e7e0)
    embed.add_field(name="Messages stored", value=len(memory.messages), inline=True)
    embed.add_field(name="Memory capacity", value=memory.messages.maxlen, inline=True)
    embed.add_field(name="Recent vibe", value=memory.get_emotional_trend(), inline=False)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="update_profiles", description="Instantly update all user profiles using Groq")
@app_commands.checks.has_permissions(administrator=True)
async def update_profiles(interaction: discord.Interaction):
    await interaction.response.send_message("Updating all user profiles now... ⏳", ephemeral=True)
    
    async def run_worker_once():
        if not mysql_pool:
            await setup_mysql()
        try:
            users = await db_memory.get_all_user_ids()
            log.info(f"[Instant Worker] Processing {len(users)} users")
            
            for user_id in users:
                messages = await db_memory.fetch_user_messages(user_id, limit=50)
                if not messages:
                    continue

                # Groq prompt for summarization
                text_to_summarize = " ".join(messages)
                prompt = f"""
                Summarize the following text for a Discord user profile in 1-2 short sentences.
                Highlight hobbies, interests, personality traits, or key points.
                Keep it casual and friendly.
                Text: {text_to_summarize}
                """
                try:
                    result = await asyncio.to_thread(
                        groq_client.chat.completions.create,
                        messages=[{"role": "user", "content": prompt}],
                        model="llama-3.3-70b-versatile"
                    )
                    description = result.choices[0].message.content.strip()
                    if len(description) > MAX_DESCRIPTION_LEN:
                        description = description[:MAX_DESCRIPTION_LEN] + "..."
                except Exception as e:
                    log.error(f"[Instant Worker] Groq summarization failed: {e}")
                    description = " | ".join(messages[-10:])[:MAX_DESCRIPTION_LEN]

                await db_memory.save_user_profile(user_id, description=description)
                memory = get_user_memory(user_id)
                memory.set_user_profile(description=description)

            log.info("[Instant Worker] Finished updating all profiles.")
        except Exception as e:
            log.error(f"[Instant Worker] Error: {e}")

        await interaction.followup.send("All user profiles have been updated! ✅", ephemeral=True)

    asyncio.create_task(run_worker_once())


# ------------------------------
# On message (auto-reply in tracked channels)
# ------------------------------

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    if message.channel.id not in channels_tracking:
        return

    if message.id in processed_messages:
        return
    processed_messages.add(message.id)

    user_id = str(message.author.id)
    guild_id = message.guild.id if message.guild else 0
    memory = get_user_memory(user_id)

    emotion, intensity = analyze_emotion_and_intensity(message.content)

    memory.add_message("user", message.content, emotion, intensity)

    if db_memory:
        try:
            await db_memory.add_message(
                user_id=user_id,
                guild_id=guild_id,
                role="user",
                content=message.content,
                emotion=emotion,
                intensity=intensity
            )
        except Exception as e:
            log.error(f"Failed to save user message to SQL: {e}")

    try:
        reply = await get_Stolas_reply(message.content, memory)
    except Exception as e:
        log.error(f"Groq failed: {e}")
        reply = generate_natural_fallback(emotion, intensity)

    memory.add_message("assistant", reply)

    if db_memory:
        try:
            await db_memory.add_message(
                user_id=user_id,
                guild_id=guild_id,
                role="assistant",
                content=reply
            )
        except Exception as e:
            log.error(f"Failed to save assistant message to SQL: {e}")

    await message.channel.send(reply)

    await bot.process_commands(message)



WORKER_INTERVAL = 300  # 5 minutes


# ------------------------------
# Worker function with Groq
# ------------------------------
@tasks.loop(seconds=WORKER_INTERVAL)
async def worker_task():
    """Periodically fetch users/messages and update their profile descriptions using Groq."""
    if not mysql_pool:
        return

    try:
        users = await db_memory.get_all_user_ids()  # Make sure this is implemented
        log.info(f"[Worker] Processing {len(users)} users")

        for user_id in users:
            messages = await db_memory.fetch_user_messages(user_id, limit=50)
            if not messages:
                continue

            # Combine messages into a single text
            text_to_summarize = " ".join(messages)

            # Groq prompt
            prompt = f"""
            Summarize the following text for a Discord user profile in 1-2 short sentences.
            Highlight hobbies, interests, personality traits, or key points.
            Keep it casual and friendly.
            Text: {text_to_summarize}
            """

            try:
                result = await asyncio.to_thread(
                    groq_client.chat.completions.create,
                    messages=[{"role": "user", "content": prompt}],
                    model="llama-3.3-70b-versatile"
                )
                description = result.choices[0].message.content.strip()
                if len(description) > MAX_DESCRIPTION_LEN:
                    description = description[:MAX_DESCRIPTION_LEN] + "..."
            except Exception as e:
                log.error(f"[Worker] Groq summarization failed: {e}")
                description = " | ".join(messages[-10:])[:MAX_DESCRIPTION_LEN]

            # Save to DB and in-memory profile
            await db_memory.save_user_profile(user_id, description=description)
            memory = get_user_memory(user_id)
            memory.set_user_profile(description=description)

            log.info(f"[Worker] Updated profile for {user_id}")

    except Exception as e:
        log.error(f"[Worker] Error: {e}")


# ------------------------------
# Bot events
# ------------------------------
@bot.event
async def on_ready():
    await bot.tree.sync()
    log.info(f"Stolas online as {bot.user}")

    # Ensure MySQL is initialized
    global mysql_pool, db_memory
    if not mysql_pool:
        await setup_mysql()

    # Start worker task
    if not hasattr(bot, "worker_task"):
        bot.worker_task = worker_task
        if not bot.worker_task.is_running():
            bot.worker_task.start()
            
# ------------------------------
# Run the bot
# ------------------------------
if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)