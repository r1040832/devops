import discord
import feedparser
import asyncio
from dotenv import load_dotenv
import os

# ── Load environment variables ─────────────────────────────
load_dotenv("Evangeline\TOKENS.env")

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
CHANNEL_ID = 1456662674015391937

# ── RSS feeds (add as many as you want) ─────────────────────
RSS_FEEDS = {
    "BBC": "http://feeds.bbci.co.uk/news/world/rss.xml",
    "CNN": "http://rss.cnn.com/rss/edition_world.rss",
    "GitLab": "https://about.gitlab.com/atom.xml",
    "": "",
    "": "",
}

# ── Discord client setup ───────────────────────────────────
intents = discord.Intents.default()
client = discord.Client(intents=intents)

posted_links = set()

# ── Fetch and post news ────────────────────────────────────
async def fetch_news():
    channel = client.get_channel(CHANNEL_ID)

    if channel is None:
        print("❌ Channel not found.")
        return

    for source, url in RSS_FEEDS.items():
        feed = feedparser.parse(url)

        for entry in feed.entries[:2]:
            if entry.link not in posted_links:
                await channel.create_thread(
                    name=entry.title[:100],
                    content=f"*Source:* {source}\n{entry.link}"
                )
                posted_links.add(entry.link)
                await asyncio.sleep(2)

# ── Bot events ─────────────────────────────────────────────
@client.event
async def on_ready():
    print(f"✅ Logged in as {client.user}")
    await fetch_news()  # run once at startup

    while True:
        await asyncio.sleep(1800)  # 30 minutes
        await fetch_news()

# ── Run bot ────────────────────────────────────────────────
client.run(DISCORD_TOKEN)
