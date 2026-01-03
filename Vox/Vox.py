import discord
from discord import Color
import discord.guild
from discord.ext import commands
from discord.ui import Button, View, Modal, TextInput, Select
import os
from dotenv import load_dotenv
from typing import Optional


load_dotenv(dotenv_path="Vox/TOKEN.env")


TOKEN = os.getenv("TOKEN")
GUILD_ID = 1454498691225485435

intents = discord.Intents.default()
intents.members = True
intents.message_content = True


bot = commands.Bot(command_prefix="!", intents=intents)

# ----- UI Buttons -----

class PrivateChannelView(View):
    def __init__(self, guild: discord.Guild):  # <- add guild parameter
        super().__init__(timeout=None)

        
        share= discord.utils.get(guild.emojis, name="share")
        death= discord.utils.get(guild.emojis, name="death")
        add= discord.utils.get(guild.emojis, name="add")
        unadd= discord.utils.get(guild.emojis, name="unadd")
        lock= discord.utils.get(guild.emojis, name="lock")
        kick= discord.utils.get(guild.emojis, name="kick")
        
        self.add_item(Button(emoji=share, style=discord.ButtonStyle.secondary,  custom_id="create_private_channel"))
        self.add_item(Button(emoji=death, style=discord.ButtonStyle.secondary,  custom_id="delete_private_channel"))
        self.add_item(Button(emoji=add, style=discord.ButtonStyle.secondary,  custom_id="add_member_channel"))
        self.add_item(Button(emoji=unadd, style=discord.ButtonStyle.secondary,  custom_id="remove_member_channel"))

# ----- remove member -------

class RemoveMemberSelect(View):
    def __init__(self, channel: discord.TextChannel):
        super().__init__(timeout=None)
        self.channel = channel

        # List only members who currently have permission to view the channel
        members_in_channel = [
            member for member, perms in channel.overwrites.items()
            if isinstance(member, discord.Member) and perms.view_channel
        ]

        if not members_in_channel:
            # If no one to remove, we can skip creating a select
            return

        options = [
            discord.SelectOption(label=member.display_name, value=str(member.id))
            for member in members_in_channel
        ]

        self.select = Select(
            placeholder="Select members to remove",
            options=options,
            custom_id="select_remove_member",
            min_values=1,
            max_values=len(options)
        )

        self.select.callback = self.remove_members_callback
        self.add_item(self.select)

    async def remove_members_callback(self, interaction: discord.Interaction):
        removed_members = []

        for member_id_str in self.select.values:
            member_id = int(member_id_str)
            member = interaction.guild.get_member(member_id)
            if member:
                try:
                    # Remove permissions
                    await self.channel.set_permissions(member, view_channel=False, send_messages=False)
                    removed_members.append(member.mention)
                except Exception as e:
                    await interaction.response.send_message(
                        f"Error removing {member.display_name}: {e}",
                        ephemeral=True
                    )
                    return

        if removed_members:
            await interaction.response.send_message(
                f"Removed members from {self.channel.mention}: {', '.join(removed_members)}",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "No members were removed.",
                ephemeral=True
            )

# ----- Modal to add member -----

class AddMemberSelect(View):
    def __init__(self, channel: discord.TextChannel, guild_members: list[discord.Member]):
        super().__init__(timeout=None)
        self.channel = channel

        options = [
            discord.SelectOption(label=member.display_name, value=str(member.id))
            for member in guild_members
            if member != channel.guild.me
        ]

        self.select = Select(
            placeholder="Select members to add",
            options=options,
            custom_id="select_add_member",
            max_values=len(options),
            min_values=1
        )

        self.select.callback = self.add_members_callback  # <-- attach callback
        self.add_item(self.select)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        perms = self.channel.overwrites_for(interaction.user)
        return perms.view_channel

    async def add_members_callback(self, interaction: discord.Interaction):
        added_members = []

        for member_id_str in self.select.values:  # self.select.values holds selected member IDs
            member_id = int(member_id_str)
            member = interaction.guild.get_member(member_id)
            if member:
                try:
                    await self.channel.set_permissions(member, view_channel=True, send_messages=True)
                    added_members.append(member.mention)
                except Exception as e:
                    await interaction.response.send_message(
                        f"Error adding {member.display_name}: {e}",
                        ephemeral=True
                    )
                    return

        if added_members:
            await interaction.response.send_message(
                f"Added members to {self.channel.mention}: {', '.join(added_members)}",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "No members were added.",
                ephemeral=True
            )
            
        
                   
# ----- Command to send buttons -----

embed=discord.Embed(
    title="Private Channel Menu",
    description="Use the buttons below to manage your private text channel.",
    color=discord.Color.blurple()
    )

embed.set_image(url="https://cdn.discordapp.com/attachments/1456702024627388439/1456710898772345055/image.png?ex=69595b3e&is=695809be&hm=618175ed9a010e7c878211bc6f916dc07e8e25f4794689c07b082891accf8323&")


@bot.command()
async def private_ui(ctx):
    view = PrivateChannelView(ctx.guild)
    await ctx.send(embed=embed,view=view)
        

# ----- Helper: find member's private channel -----

def get_member_channel(category, member):
    for ch in category.text_channels:
        perms = ch.overwrites_for(member)
        if perms.view_channel:
            return ch
    return None

# ----- Interaction handler -----

@bot.event
async def on_interaction(interaction: discord.Interaction):
    if interaction.type != discord.InteractionType.component:
        return

    custom_id = interaction.data["custom_id"]
    guild = interaction.guild
    member = interaction.user

    # Get or create "Vox" category
    
    category_name = "Vox"
    category = discord.utils.get(guild.categories, name=category_name)
    if not category:
        category = await guild.create_category(category_name)

    # Handle button clicks
    
    if custom_id == "create_private_channel":
        existing_channel = get_member_channel(category, member)
        if existing_channel:
            await interaction.response.send_message(f"Your private channel already exists: {existing_channel.mention}", ephemeral=True)
            return

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            member: discord.PermissionOverwrite(view_channel=True, send_messages=True)
        }
        channel = await guild.create_text_channel(f"private-{member.name}", overwrites=overwrites, category=category)
        await interaction.response.send_message(f"Private channel created: {channel.mention}", ephemeral=True)

    elif custom_id == "delete_private_channel":
        channel = get_member_channel(category, member)
        if channel:
            await channel.delete()
            await interaction.response.send_message("Your private channel has been deleted.", ephemeral=True)
        else:
            await interaction.response.send_message("You don't have a private channel to delete.", ephemeral=True)
        
    elif custom_id == "add_member_channel":
        # Get the member's private channel (can be None)
        channel: discord.TextChannel = get_member_channel(category, member)

        if channel is not None:
            view = AddMemberSelect(channel, guild.members)
            await interaction.response.send_message(
                "Select members to add to your private channel:",
                view=view,
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "You don't have a private channel to add members to.",
                ephemeral=True
            )
    elif custom_id == "remove_member_channel":
        channel: Optional[discord.TextChannel] = get_member_channel(category, member)

        if channel is not None:
            view = RemoveMemberSelect(channel)
            if not view.select.options:
                await interaction.response.send_message(
                    "There are no members to remove from your private channel.",
                    ephemeral=True
                )
                return

            await interaction.response.send_message(
                "Select members to remove from your private channel:",
                view=view,
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "You don't have a private channel to remove members from.",
                ephemeral=True
            )    

CATEGORY_NAME = "Vox"

# =====================
# HELPERS
# =====================

def get_member_voice_channel(category: discord.CategoryChannel, member: discord.Member):
    for ch in category.voice_channels:
        perms = ch.overwrites_for(member)
        if perms.view_channel:
            return ch
    return None


async def get_or_create_category(guild: discord.Guild):
    category = discord.utils.get(guild.categories, name=CATEGORY_NAME)
    if not category:
        category = await guild.create_category(CATEGORY_NAME)
    return category


# =====================
# MAIN UI VIEW
# =====================




class PrivateVoiceView(View):
    def __init__(self, guild: discord.Guild):
        super().__init__(timeout=None)

        def e(name, fallback):
            return discord.utils.get(guild.emojis, name=name) or fallback



        self.add_item(Button(emoji=e("share", "🎙️"), style=discord.ButtonStyle.secondary, custom_id="create_voice"))
        self.add_item(Button(emoji=e("death", "🗑️"), style=discord.ButtonStyle.secondary, custom_id="delete_voice"))
        self.add_item(Button(emoji=e("add", "➕"), style=discord.ButtonStyle.secondary, custom_id="add_member"))
        self.add_item(Button(emoji=e("unadd", "➖"), style=discord.ButtonStyle.secondary, custom_id="remove_member"))
        self.add_item(Button(emoji=e("lock", "🔒"), style=discord.ButtonStyle.secondary, custom_id="toggle_lock"))
        self.add_item(Button(emoji=e("kick", "👢"), style=discord.ButtonStyle.secondary, custom_id="kick_member"))

# =====================
# KICK MEMBER VIEW 
# =====================

class KickMemberView(View):
    def __init__(self, channel: discord.VoiceChannel):
        super().__init__(timeout=60)
        self.channel = channel

        members = channel.members

        if not members:
            return

        options = [
            discord.SelectOption(
                label=m.display_name,
                value=str(m.id)
            )
            for m in members
        ]

        self.select = Select(
            placeholder="Select members to KICK from VC",
            options=options,
            min_values=1,
            max_values=len(options)
        )

        self.select.callback = self.callback
        self.add_item(self.select)

    async def callback(self, interaction: discord.Interaction):
        kicked = []

        for mid in self.select.values:
            member = interaction.guild.get_member(int(mid))
            if member and member.voice and member.voice.channel == self.channel:
                await member.move_to(None)
                kicked.append(member.mention)

        await interaction.response.send_message(
            f"👢 Kicked from VC: {', '.join(kicked)}",
            ephemeral=True
        )

# =====================
# ADD MEMBER VIEW
# =====================

class AddMemberView(View):
    def __init__(self, channel: discord.VoiceChannel):
        super().__init__(timeout=60)
        self.channel = channel

        options = [
            discord.SelectOption(label=m.display_name, value=str(m.id))
            for m in channel.guild.members
            if not channel.overwrites_for(m).view_channel and not m.bot
        ]

        self.select = Select(
            placeholder="Select members to ADD",
            options=options[:25],
            min_values=1,
            max_values=len(options[:25])
        )

        self.select.callback = self.callback
        self.add_item(self.select)

    async def callback(self, interaction: discord.Interaction):
        added = []

        for mid in self.select.values:
            member = interaction.guild.get_member(int(mid))
            if member:
                await self.channel.set_permissions(
                    member,
                    view_channel=True,
                    connect=True,
                    speak=True
                )
                added.append(member.mention)

        await interaction.response.send_message(
            f"Added: {', '.join(added)}",
            ephemeral=True
        )


# =====================
# REMOVE MEMBER VIEW
# =====================

class RemoveMemberView(View):
    def __init__(self, channel: discord.VoiceChannel):
        super().__init__(timeout=60)
        self.channel = channel

        members = [
            m for m, p in channel.overwrites.items()
            if isinstance(m, discord.Member) and p.view_channel
        ]

        options = [
            discord.SelectOption(label=m.display_name, value=str(m.id))
            for m in members
        ]

        self.select = Select(
            placeholder="Select members to REMOVE",
            options=options,
            min_values=1,
            max_values=len(options)
        )

        self.select.callback = self.callback
        self.add_item(self.select)

    async def callback(self, interaction: discord.Interaction):
        removed = []

        for mid in self.select.values:
            member = interaction.guild.get_member(int(mid))
            if member:
                await self.channel.set_permissions(member, overwrite=None)
                removed.append(member.mention)

        await interaction.response.send_message(
            f"Removed: {', '.join(removed)}",
            ephemeral=True
        )


# =====================
# COMMAND
# =====================

@bot.command()
async def private_v_ui(ctx):
    embed = discord.Embed(
        title="🎧 Private Voice Channels",
        description="Manage your private voice room using the buttons below.",
        color=discord.Color.blurple()
    )

    embed.set_image(
        url="https://cdn.discordapp.com/attachments/1456777077306163291/1456781564913389618/image.png?ex=69599d0e&is=69584b8e&hm=3f23a9ce41b8c0987c4499eed72c68a32572c4123d8a7a36ffe9feb402ddbc86&"
    )

    view = PrivateVoiceView(ctx.guild)
    await ctx.send(embed=embed, view=view)


# =====================
# INTERACTIONS
# =====================

@bot.event
async def on_interaction(interaction: discord.Interaction):
    if interaction.type != discord.InteractionType.component:
        return

    guild = interaction.guild
    member = interaction.user
    cid = interaction.data["custom_id"]

    category = await get_or_create_category(guild)

    # CREATE
    if cid == "create_voice":
        if get_member_voice_channel(category, member):
            return await interaction.response.send_message(
                "You already have a voice room.",
                ephemeral=True
            )

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            member: discord.PermissionOverwrite(
                view_channel=True,
                connect=True,
                speak=True
            )
        }

        channel = await guild.create_voice_channel(
            f"🎙️ {member.name}'s room",
            category=category,
            overwrites=overwrites
        )

        if member.voice:
            await member.move_to(channel)

        await interaction.response.send_message(
            f"Created {channel.mention}",
            ephemeral=True
        )

    # DELETE
    elif cid == "delete_voice":
        channel = get_member_voice_channel(category, member)
        if not channel:
            return await interaction.response.send_message(
                "You don't have a voice room.",
                ephemeral=True
            )

        await channel.delete()
        await interaction.response.send_message(
            "Voice room deleted.",
            ephemeral=True
        )

    # ADD
    elif cid == "add_member":
        channel = get_member_voice_channel(category, member)
        if not channel:
            return await interaction.response.send_message(
                "You don't have a voice room.",
                ephemeral=True
            )

        await interaction.response.send_message(
            "Add members:",
            view=AddMemberView(channel),
            ephemeral=True
        )

    # REMOVE
    elif cid == "remove_member":
        channel = get_member_voice_channel(category, member)
        if not channel:
            return await interaction.response.send_message(
                "You don't have a voice room.",
                ephemeral=True
            )

        await interaction.response.send_message(
            "Remove members:",
            view=RemoveMemberView(channel),
            ephemeral=True
        )
    # TOGGLE LOCK
    elif cid == "toggle_lock":
        channel = get_member_voice_channel(category, member)

        if not channel:
            return await interaction.response.send_message(
                "You don't have a voice room.",
                ephemeral=True
            )

        everyone = guild.default_role
        current = channel.overwrites_for(everyone)

        # If currently open → lock it
        if current.connect is not False:
            await channel.set_permissions(everyone, connect=False)
            await interaction.response.send_message(
                "🔒 Voice channel locked.",
                ephemeral=True
            )
        else:
            # If locked → unlock it
            await channel.set_permissions(everyone, connect=True)
            await interaction.response.send_message(
                "🔓 Voice channel unlocked.",
                ephemeral=True
            )
    # KICK FROM VC
    elif cid == "kick_member":
        channel = get_member_voice_channel(category, member)

        if not channel:
            return await interaction.response.send_message(
                "You don't have a voice room.",
                ephemeral=True
            )

        if not channel.members:
            return await interaction.response.send_message(
                "There is no one in your voice channel to kick.",
                ephemeral=True
            )

        await interaction.response.send_message(
            "Select members to kick from the voice channel:",
            view=KickMemberView(channel),
            ephemeral=True
        )



bot.run(TOKEN)