# ============================================================
# ARK Tribe Status Tracker Bot — Multi-Tribe Edition
# Commands: /online /offline /note /addmember /removemember
#           /addtribe /removetribe /renametribe /listtribes
# Requires: pip install discord.py
# ============================================================

import discord
from discord import app_commands
from discord.ext import commands
import json, os
from datetime import datetime, timezone

# ---- CONFIGURE THESE ----
BOT_TOKEN         = os.environ.get("BOT_TOKEN")
STATUS_CHANNEL_ID = 1477197030588809336  # ID of your #tribe-status channel
ADMIN_ROLE_NAME   = "Tribe Admin"  # Role that can manage tribes/members
DATA_FILE         = "tribe_data.json"
# -------------------------

# ---------- DATA HELPERS ----------
def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE) as f:
            return json.load(f)
    return {"tribes": {}}

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

def time_ago(iso_str):
    if not iso_str: return "never"
    dt = datetime.fromisoformat(iso_str)
    diff = datetime.now(timezone.utc) - dt
    mins = int(diff.total_seconds() // 60)
    if mins < 1: return "just now"
    if mins < 60: return f"{mins}m ago"
    hrs = mins // 60
    if hrs < 24: return f"{hrs}h ago"
    return f"{hrs // 24}d ago"

def is_admin(interaction):
    return any(r.name == ADMIN_ROLE_NAME for r in interaction.user.roles)

# ---------- BUILD THE STATUS EMBED ----------
def build_embed(tribe_name, members):
    embed = discord.Embed(
        title=f"⚔️ {tribe_name.upper()} — TRIBE STATUS",
        color=0xC8902A
    )
    online  = [(n, m) for n, m in members.items() if m["online"]]
    offline = [(n, m) for n, m in members.items() if not m["online"]]

    online_text = "\n".join(
        f"🟢 **{n}** — since {m['last_seen'][:16].replace('T',' ')} UTC"
        for n, m in online
    ) or "No one online"

    offline_text = "\n".join(
        f"🔴 **{n}** — last seen {time_ago(m['last_seen'])}"
        for n, m in offline
    ) or "Everyone is online!"

    embed.add_field(name=f"ONLINE ({len(online)})",   value=online_text,  inline=False)
    embed.add_field(name=f"OFFLINE ({len(offline)})", value=offline_text, inline=False)
    embed.set_footer(text=f"Updated {datetime.now(timezone.utc).strftime('%H:%M UTC')}")
    return embed

# ---------- DROPDOWN VIEW ----------
class MemberSelect(discord.ui.Select):
    def __init__(self, members):
        options = [
            discord.SelectOption(
                label=name,
                description=f"{'🟢 Online' if m['online'] else '🔴 Offline'}",
                value=name
            )
            for name, m in list(members.items())[:25]
        ]
        super().__init__(placeholder="Select a tribe member...", options=options)
        self.members = members

    async def callback(self, interaction: discord.Interaction):
        name   = self.values[0]
        m      = self.members[name]
        status = "🟢 Online" if m["online"] else "🔴 Offline"
        notes  = m.get("notes", "No notes yet.")
        last   = time_ago(m["last_seen"]) if not m["online"] else "Currently in game"

        embed = discord.Embed(title=f"🦖 {name}", color=0x5865F2)
        embed.add_field(name="Status",    value=status, inline=True)
        embed.add_field(name="Last Seen", value=last,   inline=True)
        embed.add_field(name="Notes",     value=notes,  inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

class MemberView(discord.ui.View):
    def __init__(self, members):
        super().__init__(timeout=None)
        if members:
            self.add_item(MemberSelect(members))

# ---------- BOT SETUP ----------
intents = discord.Intents.default()
intents.message_content = True
bot  = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

async def refresh_status(guild):
    data = load_data()
    ch   = guild.get_channel(STATUS_CHANNEL_ID)
    if not ch: return
    for tribe_name, tribe in data["tribes"].items():
        embed  = build_embed(tribe_name, tribe["members"])
        view   = MemberView(tribe["members"])
        msg_id = tribe.get("status_message_id")
        if msg_id:
            try:
                msg = await ch.fetch_message(msg_id)
                await msg.edit(embed=embed, view=view)
                continue
            except:
                pass
        msg = await ch.send(embed=embed, view=view)
        data["tribes"][tribe_name]["status_message_id"] = msg.id
    save_data(data)

# ---------- TRIBE COMMANDS ----------

@tree.command(name="addtribe", description="Create a new tribe (Admins only)")
@app_commands.describe(name="Name for the tribe e.g. 'Main Tribe' or 'Alt Tribe'")
async def add_tribe(interaction: discord.Interaction, name: str):
    if not is_admin(interaction):
        await interaction.response.send_message("❌ Admins only.", ephemeral=True)
        return
    data = load_data()
    if name in data["tribes"]:
        await interaction.response.send_message(f"❌ A tribe called '{name}' already exists.", ephemeral=True)
        return
    data["tribes"][name] = {"members": {}, "status_message_id": None}
    save_data(data)
    await refresh_status(interaction.guild)
    await interaction.response.send_message(f"✅ Tribe **{name}** created!", ephemeral=True)

@tree.command(name="removetribe", description="Delete a tribe and all its members (Admins only)")
@app_commands.describe(name="Exact name of the tribe to remove")
async def remove_tribe(interaction: discord.Interaction, name: str):
    if not is_admin(interaction):
        await interaction.response.send_message("❌ Admins only.", ephemeral=True)
        return
    data = load_data()
    if name not in data["tribes"]:
        await interaction.response.send_message(f"❌ Tribe '{name}' not found.", ephemeral=True)
        return
    ch = interaction.guild.get_channel(STATUS_CHANNEL_ID)
    msg_id = data["tribes"][name].get("status_message_id")
    if ch and msg_id:
        try:
            msg = await ch.fetch_message(msg_id)
            await msg.delete()
        except:
            pass
    del data["tribes"][name]
    save_data(data)
    await interaction.response.send_message(f"✅ Tribe **{name}** removed.", ephemeral=True)

@tree.command(name="renametribe", description="Rename a tribe (Admins only)")
@app_commands.describe(old_name="Current tribe name", new_name="New tribe name")
async def rename_tribe(interaction: discord.Interaction, old_name: str, new_name: str):
    if not is_admin(interaction):
        await interaction.response.send_message("❌ Admins only.", ephemeral=True)
        return
    data = load_data()
    if old_name not in data["tribes"]:
        await interaction.response.send_message(f"❌ Tribe '{old_name}' not found.", ephemeral=True)
        return
    data["tribes"][new_name] = data["tribes"].pop(old_name)
    save_data(data)
    await refresh_status(interaction.guild)
    await interaction.response.send_message(f"✅ Renamed **{old_name}** to **{new_name}**.", ephemeral=True)

@tree.command(name="listtribes", description="Show all tribes")
async def list_tribes(interaction: discord.Interaction):
    data = load_data()
    if not data["tribes"]:
        await interaction.response.send_message("No tribes yet. Use /addtribe to create one.", ephemeral=True)
        return
    lines = [f"⚔️ **{name}** — {len(t['members'])} members" for name, t in data["tribes"].items()]
    await interaction.response.send_message("\n".join(lines), ephemeral=True)

# ---------- MEMBER COMMANDS ----------

@tree.command(name="addmember", description="Add a member to a tribe (Admins only)")
@app_commands.describe(tribe="Tribe name", name="Member's in-game name")
async def add_member(interaction: discord.Interaction, tribe: str, name: str):
    if not is_admin(interaction):
        await interaction.response.send_message("❌ Admins only.", ephemeral=True)
        return
    data = load_data()
    if tribe not in data["tribes"]:
        await interaction.response.send_message(f"❌ Tribe '{tribe}' not found. Use /listtribes to see your tribes.", ephemeral=True)
        return
    data["tribes"][tribe]["members"][name] = {"online": False, "last_seen": None, "notes": ""}
    save_data(data)
    await refresh_status(interaction.guild)
    await interaction.response.send_message(f"✅ Added **{name}** to **{tribe}**.", ephemeral=True)

@tree.command(name="removemember", description="Remove a member from a tribe (Admins only)")
@app_commands.describe(tribe="Tribe name", name="Member's name to remove")
async def remove_member(interaction: discord.Interaction, tribe: str, name: str):
    if not is_admin(interaction):
        await interaction.response.send_message("❌ Admins only.", ephemeral=True)
        return
    data = load_data()
    if tribe not in data["tribes"]:
        await interaction.response.send_message(f"❌ Tribe '{tribe}' not found.", ephemeral=True)
        return
    if name not in data["tribes"][tribe]["members"]:
        await interaction.response.send_message(f"❌ '{name}' not found in {tribe}. Check spelling is exact.", ephemeral=True)
        return
    del data["tribes"][tribe]["members"][name]
    save_data(data)
    await refresh_status(interaction.guild)
    await interaction.response.send_message(f"✅ Removed **{name}** from **{tribe}**.", ephemeral=True)

@tree.command(name="online", description="Set yourself as online in ARK")
@app_commands.describe(tribe="Which tribe are you playing on?")
async def set_online(interaction: discord.Interaction, tribe: str):
    data = load_data()
    if tribe not in data["tribes"]:
        await interaction.response.send_message(f"❌ Tribe '{tribe}' not found. Use /listtribes to see your tribes.", ephemeral=True)
        return
    name = interaction.user.display_name
    if name not in data["tribes"][tribe]["members"]:
        data["tribes"][tribe]["members"][name] = {"online": False, "last_seen": None, "notes": ""}
    data["tribes"][tribe]["members"][name]["online"]    = True
    data["tribes"][tribe]["members"][name]["last_seen"] = datetime.now(timezone.utc).isoformat()
    save_data(data)
    await refresh_status(interaction.guild)
    await interaction.response.send_message(f"✅ **{name}** is now online in **{tribe}**!", ephemeral=True)

@tree.command(name="offline", description="Set yourself as offline")
@app_commands.describe(tribe="Which tribe are you going offline from?")
async def set_offline(interaction: discord.Interaction, tribe: str):
    data = load_data()
    if tribe not in data["tribes"]:
        await interaction.response.send_message(f"❌ Tribe '{tribe}' not found.", ephemeral=True)
        return
    name = interaction.user.display_name
    if name not in data["tribes"][tribe]["members"]:
        data["tribes"][tribe]["members"][name] = {"online": False, "last_seen": None, "notes": ""}
    data["tribes"][tribe]["members"][name]["online"]    = False
    data["tribes"][tribe]["members"][name]["last_seen"] = datetime.now(timezone.utc).isoformat()
    save_data(data)
    await refresh_status(interaction.guild)
    await interaction.response.send_message(f"👋 **{name}** is now offline from **{tribe}**.", ephemeral=True)

@tree.command(name="note", description="Add a note to a tribe member (Admins only)")
@app_commands.describe(tribe="Tribe name", member="Member name", note="The note to set")
async def set_note(interaction: discord.Interaction, tribe: str, member: str, note: str):
    if not is_admin(interaction):
        await interaction.response.send_message("❌ Admins only.", ephemeral=True)
        return
    data = load_data()
    if tribe not in data["tribes"]:
        await interaction.response.send_message(f"❌ Tribe '{tribe}' not found.", ephemeral=True)
        return
    if member not in data["tribes"][tribe]["members"]:
        await interaction.response.send_message(f"❌ '{member}' not found in {tribe}.", ephemeral=True)
        return
    data["tribes"][tribe]["members"][member]["notes"] = note
    save_data(data)
    await interaction.response.send_message(f"✅ Note updated for **{member}** in **{tribe}**.", ephemeral=True)

@bot.event
async def on_ready():
    await tree.sync()
    print(f"✅ Bot online as {bot.user}")

bot.run(BOT_TOKEN)
