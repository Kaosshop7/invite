import discord
from discord.ext import commands, tasks
from discord import app_commands
import json
import os
import psutil 
import asyncio
from flask import Flask
from threading import Thread
from dotenv import load_dotenv

load_dotenv()

app = Flask("")
@app.route("/")
def home(): return "Bot is online and running!"
def run(): app.run(host="0.0.0.0", port=8080)
def keep_alive():
    t = Thread(target=run)
    t.start()

DATA_FILE = "bot_data.json"

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            data.setdefault("invite_history", {}) 
            data.setdefault("fake_invite_counts", {})
            data.setdefault("multipliers", {})
            return data
    return {
        "rewards_config": {},  
        "log_channels": {},    
        "welcome_channels": {},
        "top_messages": {},    
        "invited_by": {},      
        "real_invites": {},
        "invite_history": {},
        "fake_invite_counts": {},
        "multipliers": {}
    }

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

intents = discord.Intents.default()
intents.members = True
intents.invites = True
intents.message_content = True

MIN_ACCOUNT_AGE_DAYS = 3
MILESTONES = [50, 100, 150, 200, 300, 500, 1000]

class EventView(discord.ui.View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(label="เช็คสถิติ", style=discord.ButtonStyle.primary, custom_id="btn_check_stats", emoji="📊")
    async def check_stats(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild_id = str(interaction.guild.id)
        user_id = str(interaction.user.id)
        invites = self.bot.db["real_invites"].get(guild_id, {}).get(user_id, 0)
        embed = discord.Embed(
            title="📊 สถิติการเชิญของคุณ",
            description=f"ตอนนี้คุณมีแต้มสะสมทั้งหมด **{invites}** แต้ม 🚀",
            color=0x3498DB
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="ขอลิงก์เชิญ", style=discord.ButtonStyle.success, custom_id="btn_get_link", emoji="🔗")
    async def get_link(self, interaction: discord.Interaction, button: discord.ui.Button):
        invite = await interaction.channel.create_invite(max_age=0, max_uses=0, reason="ขอลิงก์กิจกรรมจากบอท")
        await interaction.response.send_message(f"นี่ลิงก์ส่วนตัวของคุณ ก๊อปไปชวนเพื่อนได้เลย\n👉 {invite.url}", ephemeral=True)

class InviteBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)
        self.invites_cache = {}
        self.db = load_data()

    async def setup_hook(self):
        self.add_view(EventView(self))
        await self.tree.sync()
        print("✅ ซิงค์คำสั่ง Slash Commands เรียบร้อยแล้ว!")
        self.update_status.start()

    @tasks.loop(seconds=15)
    async def update_status(self):
        ram = psutil.virtual_memory()
        guild = self.guilds[0] if self.guilds else None
        mult = self.db.get("multipliers", {}).get(str(guild.id), 1) if guild else 1
        
        if mult > 1: status_msg = f"RAM: {ram.percent}%"
        else: status_msg = f"RAM: {ram.percent}%"
            
        activity = discord.Activity(type=discord.ActivityType.watching, name=status_msg)
        await self.change_presence(activity=activity)

    @update_status.before_loop
    async def before_update_status(self):
        await self.wait_until_ready()

bot = InviteBot()

@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    embed = discord.Embed(title="❌ เกิดข้อผิดพลาด!", description=f"```{error}```", color=0xE74C3C)
    if interaction.response.is_done():
        await interaction.followup.send(embed=embed, ephemeral=True)
    else:
        await interaction.response.send_message(embed=embed, ephemeral=True)

async def update_leaderboard(guild):
    guild_id = str(guild.id)
    if guild_id not in bot.db["top_messages"]: return
        
    top_info = bot.db["top_messages"][guild_id]
    channel = guild.get_channel(top_info["channel"])
    if not channel: return

    invites_data = bot.db["real_invites"].get(guild_id, {})
    sorted_invites = sorted(invites_data.items(), key=lambda x: x[1], reverse=True)[:10]

    desc = "🏆 **รายชื่อคนชวนเพื่อน 10 อันดับแรก**\n\n"
    if not sorted_invites:
        desc += "ยังไม่มีใครชวนเพื่อนมาเลย แย่งอันดับ 1 กันเร็ว! 🚀"
    else:
        medals = ["🥇", "🥈", "🥉"]
        for i, (user_id, count) in enumerate(sorted_invites):
            if count <= 0: continue
            medal = medals[i] if i < 3 else "🏅"
            desc += f"{medal} **อันดับ {i+1}:** <@{user_id}> ➔ `{count}` แต้ม\n"

    embed = discord.Embed(title="📊 Leaderboard: อันดับนักเชิญเพื่อน", description=desc, color=0xFFD700)

    try:
        msg = await channel.fetch_message(top_info["message"])
        await msg.edit(embed=embed)
    except:
        new_msg = await channel.send(embed=embed)
        bot.db["top_messages"][guild_id]["message"] = new_msg.id
        save_data(bot.db)

@bot.event
async def on_ready():
    print(f'✅ ล็อกอินสำเร็จ! ใช้งานบอทในชื่อ {bot.user}')
    for guild in bot.guilds:
        try: bot.invites_cache[guild.id] = await guild.invites()
        except discord.Forbidden: pass
        await update_leaderboard(guild)

@bot.event
async def on_invite_create(invite): bot.invites_cache[invite.guild.id] = await invite.guild.invites()

@bot.event
async def on_invite_delete(invite): bot.invites_cache[invite.guild.id] = await invite.guild.invites()

@bot.event
async def on_member_join(member):
    guild = member.guild
    guild_id = str(guild.id)
    member_id = str(member.id)
    
    if guild.id not in bot.invites_cache: return
    old_invites = bot.invites_cache[guild.id]
    try:
        new_invites = await guild.invites()
        bot.invites_cache[guild.id] = new_invites
    except discord.Forbidden: return

    inviter = None
    for invite in old_invites:
        for new_invite in new_invites:
            if invite.code == new_invite.code and invite.uses < new_invite.uses:
                inviter = new_invite.inviter
                break
        if inviter: break

    if inviter:
        inviter_id = str(inviter.id)
        log_ch_id = bot.db["log_channels"].get(guild_id)
        log_ch = guild.get_channel(log_ch_id) if log_ch_id else None
        
        account_age = (discord.utils.utcnow() - member.created_at).days
        is_fake = account_age < MIN_ACCOUNT_AGE_DAYS
        
        if is_fake:
            if guild_id not in bot.db["fake_invite_counts"]: bot.db["fake_invite_counts"][guild_id] = {}
            fake_count = bot.db["fake_invite_counts"][guild_id].get(inviter_id, 0) + 1
            bot.db["fake_invite_counts"][guild_id][inviter_id] = fake_count
            save_data(bot.db)
            
            kicked = False
            try:
                await member.kick(reason=f"Auto-Mod: บัญชีอายุไม่ถึง {MIN_ACCOUNT_AGE_DAYS} วัน (สงสัยว่าเป็นไอดีไก่)")
                kicked = True
            except discord.Forbidden: pass

            if log_ch:
                warn_embed = discord.Embed(
                    title="🚨 Auto-Mod: ตรวจพบคนพยายามปั๊มยอด!",
                    description=f"{inviter.mention} ชวนไอดีไก่ {member.mention} เข้ามา\n⚠️ นี่คือครั้งที่ **{fake_count}** แล้วนะที่คนนี้เอาไอดีไก่เข้ามา\n**สถานะ:** {'👢 เตะไอดีไก่นี้ทิ้งเรียบร้อยแล้ว!' if kicked else '⚠️ บอทยศต่ำกว่า เลยเตะไม่ได้'}",
                    color=0xE74C3C
                )
                await log_ch.send(embed=warn_embed)
            return
          
        base_multiplier = bot.db.get("multipliers", {}).get(guild_id, 1)
        points_to_add = 1 * base_multiplier
        inviter_member = guild.get_member(inviter.id)
        if inviter_member and inviter_member.premium_since is not None: 
            points_to_add += 1

        if guild_id not in bot.db["invited_by"]: bot.db["invited_by"][guild_id] = {}
        if guild_id not in bot.db["real_invites"]: bot.db["real_invites"][guild_id] = {}
        if guild_id not in bot.db["invite_history"]: bot.db["invite_history"][guild_id] = {}
        if inviter_id not in bot.db["invite_history"][guild_id]: bot.db["invite_history"][guild_id][inviter_id] = []
        
        bot.db["invite_history"][guild_id][inviter_id].append(member_id)
        bot.db["invited_by"][guild_id][member_id] = {"inviter": inviter_id, "points": points_to_add}
        
        current_invites = bot.db["real_invites"][guild_id].get(inviter_id, 0) + points_to_add
        bot.db["real_invites"][guild_id][inviter_id] = current_invites
        save_data(bot.db)

        welcome_ch_id = bot.db["welcome_channels"].get(guild_id)
        if welcome_ch_id:
            welcome_ch = guild.get_channel(welcome_ch_id)
            if welcome_ch:
                wel_embed = discord.Embed(
                    title="👋 ยินดีต้อนรับสมาชิกใหม่",
                    description=f"คุณ {member.mention} เข้าร่วมเซิร์ฟเวอร์เราแล้ว!\n🎯 คนที่ชวนมาคือ: {inviter.mention}\n📈 ตอนนี้คนชวนมีแต้มสะสม **{current_invites}** แต้มแล้ว" + (f"\n*(ได้แต้มโบนัส x{points_to_add})*" if points_to_add > 1 else ""),
                    color=0x3498DB
                )
                if member.avatar: wel_embed.set_thumbnail(url=member.avatar.url)
                await welcome_ch.send(embed=wel_embed)

        if guild_id in bot.db["rewards_config"]:
            config = bot.db["rewards_config"][guild_id]
            for req_invites_str, role_id in config.items():
                req_points = int(req_invites_str)
                if current_invites >= req_points and (current_invites - points_to_add) < req_points: 
                    role = guild.get_role(role_id)
                    member_to_reward = guild.get_member(inviter.id)
                    if role and member_to_reward:
                        await member_to_reward.add_roles(role)
                        if log_ch:
                            log_embed = discord.Embed(title="🎉 ปลดล็อคยศใหม่!", description=f"ยินดีด้วย {member_to_reward.mention}! คุณสะสมแต้มครบ **{req_points}** แต้มแล้ว รับยศ {role.mention} ไปประดับโปรไฟล์เลย!", color=0x2ECC71)
                            await log_ch.send(embed=log_embed)

        for ms in MILESTONES:
            if current_invites >= ms and (current_invites - points_to_add) < ms and log_ch:
                await log_ch.send(embed=discord.Embed(title="🔥 ทำลายสถิติใหม่!", description=f"ทุกคนปรบมือให้ {inviter.mention} หน่อย!\nตอนนี้ชวนเพื่อนทะลุ **{ms}** แต้ม 👑✨", color=0xFF00FF))

        await update_leaderboard(guild)

@bot.event
async def on_member_remove(member):
    guild = member.guild
    guild_id = str(guild.id)
    member_id = str(member.id)
    
    if guild_id in bot.db["invited_by"] and member_id in bot.db["invited_by"][guild_id]:
        data = bot.db["invited_by"][guild_id][member_id]
        if isinstance(data, str): inviter_id, points = data, 1
        else: inviter_id, points = data["inviter"], data["points"]
        
        if guild_id in bot.db["real_invites"] and inviter_id in bot.db["real_invites"][guild_id]:
            bot.db["real_invites"][guild_id][inviter_id] = max(0, bot.db["real_invites"][guild_id][inviter_id] - points)
                
        if inviter_id in bot.db.get("invite_history", {}).get(guild_id, {}):
            if member_id in bot.db["invite_history"][guild_id][inviter_id]:
                bot.db["invite_history"][guild_id][inviter_id].remove(member_id)
                
        del bot.db["invited_by"][guild_id][member_id]
        save_data(bot.db)
        await update_leaderboard(guild)



@bot.tree.command(name="backup", description="ดึงไฟล์ข้อมูลบอทสำรอง")
@app_commands.default_permissions(administrator=True)
async def backup_data(interaction: discord.Interaction):
    if not os.path.exists(DATA_FILE):
        await interaction.response.send_message("❌ ยังไม่มีไฟล์ข้อมูลเลยครับ", ephemeral=True)
        return
    
    await interaction.response.defer(ephemeral=True)
    try:
        user = interaction.user
        await user.send("📁 **นี่คือไฟล์ Backup ข้อมูลเซิร์ฟเวอร์ครับ**\n**", file=discord.File(DATA_FILE))
        await interaction.followup.send("✅ ส่งไฟล์ Backup เข้าแชทส่วนตัว (DM) ให้เรียบร้อยแล้วครับ!", ephemeral=True)
    except discord.Forbidden:
        await interaction.followup.send("❌ ส่งให้ไม่ได้ครับ แอดมินต้องเปิดรับข้อความ DM ก่อนนะ", ephemeral=True)

@bot.tree.command(name="check_user", description="เช็คประวัติ")
@app_commands.default_permissions(administrator=True)
async def check_user(interaction: discord.Interaction, member: discord.Member):
    guild_id, inviter_id = str(interaction.guild.id), str(member.id)
    real = bot.db.get("real_invites", {}).get(guild_id, {}).get(inviter_id, 0)
    fake = bot.db.get("fake_invite_counts", {}).get(guild_id, {}).get(inviter_id, 0)
    history = bot.db.get("invite_history", {}).get(guild_id, {}).get(inviter_id, [])
    
    mentions = [f"<@{uid}>" for uid in history[:20]]
    hist_text = ", ".join(mentions) if mentions else "ไม่เคยชวนใครเข้าเลย (หรือคนที่ชวนมากดออกหมดแล้ว)"
    if len(history) > 20: hist_text += f" ...และอีก {len(history)-20} คน"

    embed = discord.Embed(title=f"🔍 ส่องประวัติ: {member.display_name}", color=0x3498DB)
    embed.add_field(name="✅ แต้มรวมตอนนี้", value=f"`{real}` แต้ม", inline=True)
    embed.add_field(name="🚨 พยายามโกงไอดีไก่", value=f"`{fake}` ครั้ง", inline=True)
    embed.add_field(name="👥 รายชื่อคนที่ชวนมา (ที่ยังอยู่ในเซิร์ฟ)", value=hist_text, inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="set_multiplier", description="เปิดกิจกรรมคูณแต้ม")
@app_commands.default_permissions(administrator=True)
async def set_multiplier(interaction: discord.Interaction, multiplier: int):
    multiplier = max(1, multiplier)
    bot.db.setdefault("multipliers", {})[str(interaction.guild.id)] = multiplier
    save_data(bot.db)
    await interaction.response.send_message(f"✅ ตอนนี้เปิดโหมดกิจกรรมแล้ว! ใครชวนเพื่อนเข้ามาจะได้แต้ม **x{multiplier}** ครับ!")

@bot.tree.command(name="permission", description="ตั้งค่ายศ")
@app_commands.default_permissions(administrator=True)
async def permission(interaction: discord.Interaction, role1: discord.Role, invites1: int, role2: discord.Role = None, invites2: int = 0, role3: discord.Role = None, invites3: int = 0):
    guild_id = str(interaction.guild.id)
    bot.db["rewards_config"][guild_id] = {str(invites1): role1.id}
    desc = f"🔹 ระดับ 1: ใช้ `{invites1}` แต้ม ➔ ได้ยศ {role1.mention}\n"
    if role2 and invites2 > 0:
        bot.db["rewards_config"][guild_id][str(invites2)] = role2.id
        desc += f"🔹 ระดับ 2: ใช้ `{invites2}` แต้ม ➔ ได้ยศ {role2.mention}\n"
    if role3 and invites3 > 0:
        bot.db["rewards_config"][guild_id][str(invites3)] = role3.id
        desc += f"🔹 ระดับ 3: ใช้ `{invites3}` แต้ม ➔ ได้ยศ {role3.mention}\n"
    save_data(bot.db)
    await interaction.response.send_message(embed=discord.Embed(title="⚙️ ตั้งค่ายศรางวัลเสร็จแล้ว!", description=desc, color=0x3498DB))

@bot.tree.command(name="set_log", description="เลือกห้องที่จะให้บอทแจ้งเตือน")
@app_commands.default_permissions(administrator=True)
async def set_log(interaction: discord.Interaction, channel: discord.TextChannel):
    bot.db["log_channels"][str(interaction.guild.id)] = channel.id
    save_data(bot.db)
    await interaction.response.send_message(f"✅ บอทจะไปแจ้งเตือนรับยศและเตือนคนโกงที่ห้อง {channel.mention} ครับ!")

@bot.tree.command(name="set_welcome", description="เลือกห้องต้อนรับคนเข้าเซิร์ฟ")
@app_commands.default_permissions(administrator=True)
async def set_welcome(interaction: discord.Interaction, channel: discord.TextChannel):
    bot.db["welcome_channels"][str(interaction.guild.id)] = channel.id
    save_data(bot.db)
    await interaction.response.send_message(f"✅ บอทจะไปกล่าวต้อนรับสมาชิกใหม่ที่ห้อง {channel.mention} ครับ!")

@bot.tree.command(name="setup_top", description="สร้างกระดานจัดอันดับ")
@app_commands.default_permissions(administrator=True)
async def setup_top(interaction: discord.Interaction, channel: discord.TextChannel):
    await interaction.response.send_message(f"กำลังจัดกระดาน Leaderboard ไปที่ห้อง {channel.mention} รอแป๊บนึงนะ...", ephemeral=True)
    msg = await channel.send(embed=discord.Embed(title="📊 Leaderboard...", description="กำลังโหลดข้อมูล... ⏳"))
    bot.db["top_messages"][str(interaction.guild.id)] = {"channel": channel.id, "message": msg.id}
    save_data(bot.db)
    await update_leaderboard(interaction.guild)

@bot.tree.command(name="ประกาศ", description="ส่งประกาศกิจกรรม")
@app_commands.default_permissions(administrator=True)
async def announce_event(interaction: discord.Interaction):
    guild_id = str(interaction.guild.id)
    if not bot.db["rewards_config"].get(guild_id):
        await interaction.response.send_message("⚠️ แอดมินต้องใช้คำสั่ง `/permission` ตั้งค่ายศก่อน ถึงจะประกาศได้นะครับ", ephemeral=True)
        return
        
    sorted_rewards = sorted([(int(k), v) for k, v in bot.db["rewards_config"][guild_id].items()])
    mult = bot.db.get("multipliers", {}).get(guild_id, 1)
    
    desc = (
        "🎉 **ประกาศๆ! กิจกรรมชวนเพื่อนเข้าเซิร์ฟ แจกยศฟรีมาแล้วจ้า!** 🚀\n"
        "ใครอยากได้ยศเท่ๆ เอาไว้ประดับโปรไฟล์ ฟังทางนี้! กติกาง่ายมาก แค่ชวนเพื่อนเข้ามาจอยเซิร์ฟเวอร์ของเรา ยิ่งชวนเยอะ บอทก็ยิ่งบวกแต้มให้ และแจกยศระดับสูงให้เลยแบบอัตโนมัติไม่ต้องง้อแอดมิน!\n\n"
        "👇 **วิธีร่วมสนุก ง่ายๆ แค่ 3 สเต็ป**\n"
        "1️⃣ กดปุ่ม 🔗 **'ขอลิงก์เชิญ'** ข้างล่างนี้ได้เลย (บอทจะเด้งลิงก์ส่วนตัวให้) หรือใครถนัดกดสร้างลิงก์เองก็จัดไป (อย่าลืมตั้งค่าเป็นแบบไม่จำกัดเวลาด้วยนะ)\n"
        "2️⃣ ก๊อปลิงก์ไปแปะชวนเพื่อน ชวนแก๊ง ชวนใครก็ได้ให้กดเข้ามา\n"
        "3️⃣ พอเพื่อนกดเข้าเซิร์ฟปุ๊บ ระบบจะบวกแต้มให้ทันที! เช็คแต้มตัวเองเมื่อไหร่ก็ได้ แค่กดปุ่ม 📊 **'เช็คสถิติของฉัน'** ด้านล่าง\n\n"
        "🛑 **กฎเหล็ก (อ่านก่อนนะ เดี๋ยวยอดไม่ขึ้นจะหาว่าไม่เตือน)**\n"
        "🔸 **ห้ามปั๊มไอดีไก่:** ระบบเซิร์ฟเรามีบอทสแกนนะจ๊ะ ถ้าเอาไอดีที่เพิ่งสร้างใหม่ (อายุไม่ถึง 3 วัน) เข้ามา บอทจะ **เตะทิ้งทันที** และไม่บวกแต้มให้เด้อ\n"
        "🔸 **ห้ามเพื่อนหนี:** ถ้าคนที่ชวนมา เค้ากดออกจากเซิร์ฟเวอร์ปุ๊บ ระบบจะ **'หักแต้ม'** คืนอัตโนมัติ แฟร์ๆ ครับ!\n\n"
        "💎 **Booster Bonus:**\n"
        "ใครที่ใจดีบูสต์เซิร์ฟเวอร์ให้เรา (Server Booster) รับอภิสิทธิ์ไปเลย! ชวนเพื่อน 1 คน ได้โบนัสบวกเพิ่มไปอีก **+1 แต้ม** ฟรีๆ!\n"
    )
    
    if mult > 1: 
        desc += f"\n🔥 **ตอนนี้แอดมินเปิดโหมด x{mult}! ชวนเพื่อน 1 คน รับไปเลย {mult} แต้ม**\n"
        
    desc += "\n🎁 **ของรางวัลตามระดับ**\n"
    
    level_emojis = ["🥉", "🥈", "🥇", "💎", "👑"]
    for i, (req, role_id) in enumerate(sorted_rewards):
        role = interaction.guild.get_role(role_id)
        emoji = level_emojis[i] if i < len(level_emojis) else "🎖️"
        desc += f"{emoji} ระดับ {i+1}: สะสมครบ `{req}` แต้ม ➔ **ได้รับยศ {role.mention if role else '`ไม่พบยศ`'}**\n"

    desc += "\n*รออะไรอยู่ล่ะฮะ รีบกดขอลิงก์แล้วไปชวนแก๊งเพื่อนมาลุยกันเลย!*"

    embed = discord.Embed(title="🌟 กิจกรรม: Invite ปลดล็อคยศฟรี! 🌟", description=desc, color=0x9B59B6)
    if interaction.guild.icon: embed.set_thumbnail(url=interaction.guild.icon.url)
    
    await interaction.response.send_message(embed=embed, view=EventView(bot))


@bot.tree.command(name="ping", description="เช็คความเร็วของบอท")
async def ping(interaction: discord.Interaction):
    latency = round(bot.latency * 1000)
    embed = discord.Embed(
        title="🏓 Pong!",
        description=f"ความเร็วในการตอบสนอง: `{latency}ms` ⚡",
        color=0x2ECC71
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="help", description="ดูคู่มือคำสั่งทั้งหมดของบอท")
async def help_cmd(interaction: discord.Interaction):
    embed = discord.Embed(
        title="📚 คู่มือคำสั่งบอท",
        description="รายการคำสั่งทั้งหมดที่คุณสามารถใช้งานได้:",
        color=0x3498DB
    )
    
    embed.add_field(name="🔹 คำสั่งทั่วไป", value="`/ping` - เช็คความเร็วของบอท\n`/help` - ดูคู่มือการใช้งานนี้", inline=False)
    
    if interaction.user.guild_permissions.administrator:
        admin_cmds = (
            "`/permission` - ตั้งค่ายศและคะแนน\n"
            "`/ประกาศ` - ส่งกติกาพร้อมปุ่มกด\n"
            "`/setup_top` - ตั้งจุดโชว์ Leaderboard\n"
            "`/set_log` - เลือกห้องส่งแจ้งเตือนต่างๆ\n"
            "`/set_welcome` - เลือกห้องต้อนรับคนเข้า\n"
            "`/check_user` - ส่องประวัติคนชวนแบบละเอียด\n"
            "`/set_multiplier` - เปิดกิจกรรมคูณแต้ม\n"
            "`/backup` - ดึงไฟล์ข้อมูลสำรองมาเก็บไว้"
        )
        embed.add_field(name="⚙️ คำสั่งสำหรับผู้ดูแล (Admin)", value=admin_cmds, inline=False)
    else:
        embed.add_field(name="⚙️ คำสั่งอื่นๆ", value="คำสั่งตั้งค่าระบบถูกจำกัดไว้ให้เฉพาะ Admin ใช้งานครับ", inline=False)

    await interaction.response.send_message(embed=embed, ephemeral=True)

if __name__ == "__main__":
    keep_alive()
    token = os.getenv("TOKEN") 
    if not token:
        print("❌ ไม่พบ Token! อย่าลืมไปใส่ 'TOKEN' ใน Environment Variables ของ Render นะ")
    else:
        bot.run(token)
