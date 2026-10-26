import os
import time
import asyncio
from collections import deque, defaultdict

import discord
from discord.ext import commands, tasks
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN", "").strip()
QUARANTINE_ROLE_NAME = os.getenv("QUARANTINE_ROLE_NAME", "Aislado")
LOG_CHANNEL_NAME = os.getenv("LOG_CHANNEL_NAME", "anti-raid-logs")
QUARANTINE_LOG_CHANNEL_NAME = os.getenv("QUARANTINE_LOG_CHANNEL_NAME", "aislamientos")
VOICE_CHANNEL_ID = int(os.getenv("VOICE_CHANNEL_ID", "1401644022144958595"))

JOIN_WINDOW_SECONDS = int(os.getenv("JOIN_WINDOW_SECONDS", "20"))
JOIN_THRESHOLD = int(os.getenv("JOIN_THRESHOLD", "6"))
EMERGENCY_SECONDS = int(os.getenv("EMERGENCY_SECONDS", "180"))
QUARANTINE_NEW_MEMBERS_DURING_RAID = os.getenv(
    "QUARANTINE_NEW_MEMBERS_DURING_RAID", "true"
).lower() == "true"

SPAM_WINDOW_SECONDS = int(os.getenv("SPAM_WINDOW_SECONDS", "8"))
SPAM_MESSAGE_THRESHOLD = int(os.getenv("SPAM_MESSAGE_THRESHOLD", "6"))
DUPLICATE_THRESHOLD = int(os.getenv("DUPLICATE_THRESHOLD", "4"))

# Cambia cada cierto tiempo el estado visible del bot.
PRESENCE_ROTATION_SECONDS = int(os.getenv("PRESENCE_ROTATION_SECONDS", "45"))

intents = discord.Intents.default()
intents.members = True
intents.message_content = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

join_times = defaultdict(deque)
user_messages = defaultdict(deque)
duplicate_messages = defaultdict(deque)
emergency_until = {}
emergency_tasks = {}
presence_index = 0


def is_owner_or_admin(member: discord.Member) -> bool:
    return member.id == member.guild.owner_id or member.guild_permissions.administrator


def quarantine_role(guild: discord.Guild):
    return discord.utils.get(guild.roles, name=QUARANTINE_ROLE_NAME)


def find_text_channel(guild: discord.Guild, channel_name: str):
    return discord.utils.get(guild.text_channels, name=channel_name)


async def send_to_channel(guild: discord.Guild, channel_name: str, message: str):
    channel = find_text_channel(guild, channel_name)
    if channel:
        try:
            await channel.send(
                message[:1900],
                allowed_mentions=discord.AllowedMentions.none()
            )
        except discord.HTTPException:
            pass


async def log(guild: discord.Guild, message: str):
    await send_to_channel(guild, LOG_CHANNEL_NAME, message)
    print(f"[{guild.name}] {message}")


async def log_quarantine(guild: discord.Guild, message: str):
    # Registro separado: cada aislamiento queda en el canal "aislamientos".
    await send_to_channel(guild, QUARANTINE_LOG_CHANNEL_NAME, message)
    print(f"[AISLAMIENTO - {guild.name}] {message}")


async def set_emergency(guild: discord.Guild, reason: str):
    emergency_until[guild.id] = max(
        emergency_until.get(guild.id, 0),
        time.time() + EMERGENCY_SECONDS
    )
    await log(
        guild,
        f"🚨 **MODO EMERGENCIA ACTIVADO**: {reason}. "
        f"Duración inicial: {EMERGENCY_SECONDS}s."
    )
    task = emergency_tasks.get(guild.id)
    if task and not task.done():
        task.cancel()
    emergency_tasks[guild.id] = asyncio.create_task(emergency_timer(guild))


async def emergency_timer(guild: discord.Guild):
    try:
        while True:
            remaining = emergency_until.get(guild.id, 0) - time.time()
            if remaining <= 0:
                emergency_until.pop(guild.id, None)
                await log(
                    guild,
                    "🟢 **Modo emergencia finalizado**. "
                    "Revisa los canales y los registros."
                )
                return
            await asyncio.sleep(min(remaining, 10))
    except asyncio.CancelledError:
        return


def emergency_active(guild: discord.Guild) -> bool:
    return emergency_until.get(guild.id, 0) > time.time()


async def quarantine(member: discord.Member, reason: str) -> bool:
    if member.bot or is_owner_or_admin(member):
        return False

    role = quarantine_role(member.guild)
    if role is None:
        await log(
            member.guild,
            f"⚠️ No encuentro el rol **{QUARANTINE_ROLE_NAME}**; "
            f"no pude aislar a {member} (`{member.id}`)."
        )
        return False

    me = member.guild.me
    if me is None or role >= me.top_role:
        await log(
            member.guild,
            f"⚠️ El rol **{QUARANTINE_ROLE_NAME}** debe estar por debajo "
            "del rol más alto del bot."
        )
        return False

    if member.top_role >= me.top_role:
        await log(
            member.guild,
            f"⚠️ No puedo moderar a {member} (`{member.id}`): su rol más alto "
            "está al mismo nivel o por encima del bot."
        )
        return False

    if role in member.roles:
        return False

    try:
        await member.add_roles(role, reason=f"Anti-raid: {reason}")
        embed = discord.Embed(
            title="🔒 Usuario aislado",
            color=discord.Color.orange(),
            timestamp=discord.utils.utcnow()
        )
        embed.add_field(name="Usuario", value=f"{member.mention}\n`{member}`", inline=True)
        embed.add_field(name="ID", value=f"`{member.id}`", inline=True)
        embed.add_field(name="Motivo", value=reason[:1000], inline=False)
        embed.set_footer(text=f"Servidor: {member.guild.name}")
        channel = find_text_channel(member.guild, QUARANTINE_LOG_CHANNEL_NAME)
        if channel:
            try:
                await channel.send(
                    embed=embed,
                    allowed_mentions=discord.AllowedMentions.none()
                )
            except discord.HTTPException:
                pass
        await log(member.guild, f"🔒 Aislado {member} (`{member.id}`). Motivo: {reason}")
        return True
    except discord.Forbidden:
        await log(
            member.guild,
            f"❌ Sin permisos para aislar a {member} (`{member.id}`). "
            "Revisa permisos y jerarquía de roles."
        )
    except discord.HTTPException as exc:
        await log(member.guild, f"❌ Error al aislar a `{member.id}`: {exc}")
    return False


async def quarantine_recent_joiners(guild: discord.Guild, reason: str):
    cutoff = time.time() - JOIN_WINDOW_SECONDS
    for member in list(guild.members):
        if member.bot or is_owner_or_admin(member):
            continue
        joined = member.joined_at.timestamp() if member.joined_at else 0
        if joined >= cutoff:
            await quarantine(member, reason)
            await asyncio.sleep(0.35)


@tasks.loop(seconds=PRESENCE_ROTATION_SECONDS)
async def rotate_presence():
    global presence_index
    if not bot.is_ready():
        return

    guilds = list(bot.guilds)
    isolated_count = 0
    for guild in guilds:
        role = quarantine_role(guild)
        if role:
            isolated_count += len(role.members)

    # Los estados online/ausente/no molestar se alternan. El texto de actividad
    # también cambia para mostrar qué está haciendo el bot.
    presences = [
        (discord.Status.online, discord.Activity(
            type=discord.ActivityType.playing,
            name="🛡️ Protegiendo servidores"
        )),
        (discord.Status.idle, discord.Activity(
            type=discord.ActivityType.watching,
            name=f"🔒 {isolated_count} usuarios aislados"
        )),
        (discord.Status.dnd, discord.Activity(
            type=discord.ActivityType.playing,
            name="🚨 Vigilando posibles raids"
        )),
        (discord.Status.online, discord.Activity(
            type=discord.ActivityType.listening,
            name="📡 Alertas de seguridad"
        )),
    ]
    status, activity = presences[presence_index % len(presences)]
    presence_index += 1
    try:
        await bot.change_presence(status=status, activity=activity)
    except discord.HTTPException as exc:
        print(f"No pude cambiar la presencia: {exc}")


@rotate_presence.before_loop
async def before_rotate_presence():
    await bot.wait_until_ready()


@tasks.loop(seconds=30)
async def keep_voice_connected():
    """Mantiene el bot conectado al canal de voz configurado."""
    if not bot.is_ready():
        return

    channel = bot.get_channel(VOICE_CHANNEL_ID)
    if channel is None:
        try:
            channel = await bot.fetch_channel(VOICE_CHANNEL_ID)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException) as exc:
            print(f"No pude encontrar/acceder al canal de voz {VOICE_CHANNEL_ID}: {exc}")
            return

    if not isinstance(channel, (discord.VoiceChannel, discord.StageChannel)):
        print(f"El ID {VOICE_CHANNEL_ID} no corresponde a un canal de voz o escenario.")
        return

    voice_client = discord.utils.get(bot.voice_clients, guild=channel.guild)
    try:
        if voice_client and voice_client.is_connected():
            if voice_client.channel and voice_client.channel.id != channel.id:
                await voice_client.move_to(channel)
            return

        if voice_client:
            try:
                await voice_client.disconnect(force=True)
            except (discord.HTTPException, asyncio.TimeoutError):
                pass

        await channel.connect(timeout=20, reconnect=True)
        print(f"Conectado al canal de voz: {channel.name} ({channel.id})")
    except (discord.Forbidden, discord.HTTPException, asyncio.TimeoutError, OSError) as exc:
        print(f"No pude conectar al canal de voz; volveré a intentar: {exc}")


@keep_voice_connected.before_loop
async def before_keep_voice_connected():
    await bot.wait_until_ready()


@bot.event
async def on_ready():
    print(f"Conectado como {bot.user} (ID: {bot.user.id})")
    print("Anti-raid activo.")
    for guild in bot.guilds:
        await log(guild, f"✅ Bot anti-raid conectado como **{bot.user}**.")
    if not rotate_presence.is_running():
        rotate_presence.start()
    if not keep_voice_connected.is_running():
        keep_voice_connected.start()


@bot.event
async def on_member_join(member: discord.Member):
    if member.bot:
        return

    now = time.time()
    q = join_times[member.guild.id]
    q.append(now)
    while q and now - q[0] > JOIN_WINDOW_SECONDS:
        q.popleft()

    if emergency_active(member.guild) and QUARANTINE_NEW_MEMBERS_DURING_RAID:
        await quarantine(member, "Entró mientras el modo emergencia estaba activo")
        return

    if len(q) >= JOIN_THRESHOLD:
        await set_emergency(
            member.guild,
            f"{len(q)} entradas en {JOIN_WINDOW_SECONDS} segundos"
        )
        if QUARANTINE_NEW_MEMBERS_DURING_RAID:
            await quarantine_recent_joiners(
                member.guild,
                f"Entrada durante oleada anti-raid ({len(q)} en {JOIN_WINDOW_SECONDS}s)"
            )


@bot.event
async def on_message(message: discord.Message):
    if message.author.bot or not message.guild:
        return

    if isinstance(message.author, discord.Member) and is_owner_or_admin(message.author):
        await bot.process_commands(message)
        return

    now = time.time()
    key = (message.guild.id, message.author.id)

    recent = user_messages[key]
    recent.append(now)
    while recent and now - recent[0] > SPAM_WINDOW_SECONDS:
        recent.popleft()

    content = message.content.strip().lower()
    if content:
        dup = duplicate_messages[key]
        dup.append((now, content[:500]))
        while dup and now - dup[0][0] > SPAM_WINDOW_SECONDS:
            dup.popleft()
        same_count = sum(1 for _, text in dup if text == content[:500])
    else:
        same_count = 0

    reason = None
    if len(recent) >= SPAM_MESSAGE_THRESHOLD:
        reason = f"Spam: {len(recent)} mensajes en {SPAM_WINDOW_SECONDS}s"
    elif same_count >= DUPLICATE_THRESHOLD:
        reason = f"Mensajes repetidos: {same_count} veces en {SPAM_WINDOW_SECONDS}s"

    if reason and isinstance(message.author, discord.Member):
        await quarantine(message.author, reason)
        await set_emergency(
            message.guild,
            f"spam detectado de usuario {message.author.id}"
        )
        try:
            await message.delete()
        except discord.HTTPException:
            pass
        return

    await bot.process_commands(message)


@bot.command(name="estado")
@commands.has_permissions(administrator=True)
async def estado(ctx):
    if emergency_active(ctx.guild):
        remaining = max(0, int(emergency_until[ctx.guild.id] - time.time()))
        await ctx.reply(f"🚨 Modo emergencia activo. Tiempo restante: aprox. {remaining}s.")
    else:
        await ctx.reply("🟢 Modo emergencia inactivo. Anti-raid activo.")


@bot.command(name="emergencia")
@commands.has_permissions(administrator=True)
async def emergencia(ctx):
    await set_emergency(ctx.guild, f"activado manualmente por {ctx.author}")
    await ctx.reply("🚨 Modo emergencia activado.")


@bot.command(name="finemergencia")
@commands.has_permissions(administrator=True)
async def finemergencia(ctx):
    emergency_until.pop(ctx.guild.id, None)
    task = emergency_tasks.get(ctx.guild.id)
    if task and not task.done():
        task.cancel()
    await log(ctx.guild, f"🟢 Modo emergencia desactivado manualmente por {ctx.author}.")
    await ctx.reply("Modo emergencia desactivado.")


@bot.command(name="aislar")
@commands.has_permissions(administrator=True)
async def aislar(ctx, member: discord.Member, *, motivo: str = "Aislamiento manual"):
    ok = await quarantine(member, motivo)
    await ctx.reply("Usuario aislado." if ok else "No se pudo aislar; revisa los registros.")


@bot.command(name="desaislar")
@commands.has_permissions(administrator=True)
async def desaislar(ctx, member: discord.Member):
    role = quarantine_role(ctx.guild)
    if not role or role not in member.roles:
        await ctx.reply("Ese usuario no tiene el rol Aislado.")
        return
    try:
        await member.remove_roles(role, reason=f"Desaislamiento manual por {ctx.author}")
        await log_quarantine(
            ctx.guild,
            f"🔓 **Usuario desaislado**: {member} (`{member.id}`). Por: {ctx.author}."
        )
        await ctx.reply("Usuario desaislado.")
    except discord.Forbidden:
        await ctx.reply("No tengo permisos para quitar el rol Aislado.")


@bot.command(name="ayuda")
async def ayuda(ctx):
    await ctx.reply(
        "**Comandos anti-raid**\n"
        "`!estado` — estado de emergencia (admin).\n"
        "`!emergencia` — activa emergencia (admin).\n"
        "`!finemergencia` — desactiva emergencia (admin).\n"
        "`!aislar @usuario motivo` — aislamiento manual (admin).\n"
        "`!desaislar @usuario` — quita el aislamiento (admin).\n"
        "`!ayuda` — muestra esta ayuda."
    )


@estado.error
@emergencia.error
@finemergencia.error
@aislar.error
@desaislar.error
async def admin_command_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.reply("Necesitas permiso de administrador para usar ese comando.")
    elif isinstance(error, commands.MemberNotFound):
        await ctx.reply("No encuentro ese miembro. Menciónalo o usa su ID.")
    else:
        await ctx.reply("No pude ejecutar el comando. Revisa la configuración y los permisos.")


if not TOKEN:
    raise SystemExit(
        "Falta DISCORD_TOKEN. Configura esa variable de entorno en tu hosting "
        "o copia .env.example a .env y pega el token."
    )

bot.run(TOKEN)
