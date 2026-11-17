import os
import asyncio
import discord
from discord.ext import commands
from discord import app_commands
import yt_dlp
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials

TOKEN = os.getenv("DISCORD_TOKEN")
SPOTIFY_ID = os.getenv("SPOTIFY_CLIENT_ID")
SPOTIFY_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
bot = commands.Bot(command_prefix="m!", intents=intents)

sp = None
if SPOTIFY_ID and SPOTIFY_SECRET:
    sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(client_id=SPOTIFY_ID, client_secret=SPOTIFY_SECRET))

queues = {}
currents = {}

YTDL_OPTS = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'quiet': True,
    'default_search': 'ytsearch',
    'extract_flat': False,
}
FFMPEG_OPTS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn'
}

def get_spotify_track(url):
    try:
        if sp and 'open.spotify.com/track/' in url:
            tid = url.split('/track/')[1].split('?')[0]
            t = sp.track(tid)
            return f"{t['artists'][0]['name']} - {t['name']}"
        if sp and 'open.spotify.com/playlist/' in url:
            pid = url.split('/playlist/')[1].split('?')[0]
            res = sp.playlist_tracks(pid, limit=20)
            out = []
            for item in res['items']:
                tr = item['track']
                if tr:
                    out.append(f"{tr['artists'][0]['name']} - {tr['name']}")
            return out
    except Exception as e:
        print("Spotify error:", e)
    return None

async def play_next(ctx, guild_id):
    if guild_id not in queues or not queues[guild_id]:
        currents.pop(guild_id, None)
        return
    query = queues[guild_id].pop(0)
    vc = ctx.guild.voice_client
    if not vc:
        return
    with yt_dlp.YoutubeDL(YTDL_OPTS) as ydl:
        info = ydl.extract_info(query, download=False)
        if 'entries' in info:
            info = info['entries'][0]
        url = info['url']
        title = info.get('title', query)
    currents[guild_id] = title
    vc.play(discord.FFmpegPCMAudio(url, **FFMPEG_OPTS), after=lambda e: asyncio.run_coroutine_threadsafe(play_next(ctx, guild_id), bot.loop))
    await ctx.channel.send(f"▶️ **Now Playing:** {title}")

@bot.event
async def on_ready():
    print(f"Login sebagai {bot.user}")
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} commands")
    except Exception as e:
        print(e)

@bot.tree.command(name="play", description="Putar lagu dari YouTube / Spotify")
@app_commands.describe(lagu="Judul lagu atau link YouTube/Spotify")
async def play(interaction: discord.Interaction, lagu: str):
    await interaction.response.defer()
    if not interaction.user.voice:
        await interaction.followup.send("❌ Kamu harus masuk Voice Channel dulu!")
        return
    vc = interaction.guild.voice_client
    if not vc:
        vc = await interaction.user.voice.channel.connect()
    elif vc.channel != interaction.user.voice.channel:
        await vc.move_to(interaction.user.voice.channel)

    guild_id = interaction.guild.id
    if guild_id not in queues:
        queues[guild_id] = []

    # Spotify playlist
    spot = get_spotify_track(lagu)
    if isinstance(spot, list):
        for s in spot:
            queues[guild_id].append(s)
        await interaction.followup.send(f"✅ Ditambahkan {len(spot)} lagu dari Spotify Playlist!")
    else:
        search = spot if isinstance(spot, str) else lagu
        queues[guild_id].append(search)
        await interaction.followup.send(f"✅ Ditambahkan ke antrian: **{search}**")

    if not vc.is_playing() and not vc.is_paused():
        # Buat fake ctx untuk play_next
        class FakeCtx:
            pass
        fake = FakeCtx()
        fake.guild = interaction.guild
        fake.channel = interaction.channel
        await play_next(fake, guild_id)

@bot.tree.command(name="skip", description="Skip lagu")
async def skip(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if vc and vc.is_playing():
        vc.stop()
        await interaction.response.send_message("⏭️ Di-skip!")
    else:
        await interaction.response.send_message("❌ Ga ada lagu yang diputar!")

@bot.tree.command(name="stop", description="Berhenti & keluar dari VC")
async def stop(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    gid = interaction.guild.id
    queues[gid] = []
    if vc:
        await vc.disconnect()
    await interaction.response.send_message("⏹️ Berhenti & keluar dari VC!")

@bot.tree.command(name="queue", description="Lihat antrian lagu")
async def queue_cmd(interaction: discord.Interaction):
    gid = interaction.guild.id
    q = queues.get(gid, [])
    cur = currents.get(gid, "Tidak ada")
    text = f"🎵 **Now Playing:** {cur}\n\n"
    if not q:
        text += "Antrian kosong!"
    else:
        for i, s in enumerate(q[:10], 1):
            text += f"{i}. {s}\n"
    await interaction.response.send_message(text)

@bot.tree.command(name="join", description="Bot join VC kamu")
async def join_cmd(interaction: discord.Interaction):
    if not interaction.user.voice:
        await interaction.response.send_message("❌ Masuk VC dulu!")
        return
    await interaction.user.voice.channel.connect()
    await interaction.response.send_message("✅ Udah join!")

bot.run(TOKEN)
