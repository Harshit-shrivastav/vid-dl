import os
import asyncio
import yt_dlp
import aiofiles
import ffmpeg
from telethon import TelegramClient, events, Button
from telethon.tl.types import DocumentAttributeVideo

# Telegram API Credentials
API_ID = "your_api_id"
API_HASH = "your_api_hash"
BOT_TOKEN = "your_bot_token"

# Initialize Telethon Client
bot = TelegramClient("bot_session", API_ID, API_HASH).start(bot_token=BOT_TOKEN)

# Download Directory
DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# Progress Bar
async def progress_callback(current, total, message, status="Downloading"):
    percent = (current / total) * 100
    progress_bar = f"[{'█' * int(percent // 5)}{'-' * (20 - int(percent // 5))}]"
    await message.edit(f"**{status}:** {percent:.1f}%\n{progress_bar}")

# Fetch available quality options
async def get_quality_options(url):
    options = {
        "quiet": True,
        "list_formats": True,
    }
    async with yt_dlp.YoutubeDL(options) as ydl:
        info = await asyncio.to_thread(ydl.extract_info, url, download=False)
        formats = info.get("formats", [])
        return [(f"{fmt['format_id']} - {fmt['resolution']} - {fmt['ext']}", fmt["format_id"]) for fmt in formats if "resolution" in fmt]

# Download Video
async def download_video(url, format_id=None, is_audio=False, message=None):
    output_template = f"{DOWNLOAD_DIR}/%(title)s.{'mp3' if is_audio else 'mp4'}"
    options = {
        "outtmpl": output_template,
        "format": format_id or ("bestaudio" if is_audio else "best"),
        "merge_output_format": "mp4",
        "quiet": True,
        "progress_hooks": [lambda d: asyncio.create_task(progress_callback(
            d.get("downloaded_bytes", 0),
            d.get("total_bytes", 1),
            message,
            "Downloading"
        ))],
        "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3"}] if is_audio else []
    }

    async with yt_dlp.YoutubeDL(options) as ydl:
        info = await asyncio.to_thread(ydl.extract_info, url, download=True)
        return ydl.prepare_filename(info), info.get("title", "video")

# Upload to Telegram
async def upload_video(file_path, title, event):
    chat_id = event.chat_id
    async with aiofiles.open(file_path, "rb") as f:
        file_size = os.path.getsize(file_path)
        msg = await event.reply(f"**Uploading {title}...**")

        async def upload_progress(sent_bytes, total_bytes):
            await progress_callback(sent_bytes, total_bytes, msg, "Uploading")

        await bot.send_file(
            chat_id,
            file=f,
            caption=f"🎥 **{title}**",
            progress_callback=upload_progress,
            attributes=[DocumentAttributeVideo(duration=0, w=1920, h=1080)]
        )

    await msg.delete()
    os.remove(file_path)  # Clean up

# Handle /start Command
@bot.on(events.NewMessage(pattern="/start"))
async def start(event):
    await event.reply(
        "👋 **Welcome!**\nSend me a video URL to download.\n\n"
        "✅ Supports YouTube, TikTok, Instagram, Facebook, Twitter, etc.\n"
        "🎵 Use `/audio <URL>` to download as MP3."
    )

# Handle Audio Downloads
@bot.on(events.NewMessage(pattern=r"/audio (.+)"))
async def audio_download(event):
    url = event.pattern_match.group(1)
    msg = await event.reply("🎶 **Downloading audio...**")
    
    try:
        file_path, title = await download_video(url, is_audio=True, message=msg)
        await upload_video(file_path, title, event)
    except Exception as e:
        await event.reply(f"❌ **Error:** {str(e)}")
    
    finally:
        await msg.delete()

# Handle Video Download Requests with Quality Selection
@bot.on(events.NewMessage(pattern=r"/video (.+)"))
async def choose_quality(event):
    url = event.pattern_match.group(1)
    msg = await event.reply("🔍 **Fetching available qualities...**")

    try:
        formats = await get_quality_options(url)
        buttons = [Button.inline(text, data=f"{url}|{fid}") for text, fid in formats[:10]]
        await msg.edit("🎥 **Select video quality:**", buttons=buttons)
    except Exception as e:
        await msg.edit(f"❌ **Error fetching formats:** {str(e)}")

# Handle Video Download with Selected Quality
@bot.on(events.CallbackQuery)
async def quality_selected(event):
    data = event.data.decode()
    url, format_id = data.split("|")
    
    msg = await event.edit("📥 **Downloading selected quality...**")
    try:
        file_path, title = await download_video(url, format_id=format_id, message=msg)
        await upload_video(file_path, title, event)
    except Exception as e:
        await event.edit(f"❌ **Error:** {str(e)}")
    finally:
        await msg.delete()

# Handle Playlist Downloads
@bot.on(events.NewMessage(pattern=r"/playlist (.+)"))
async def playlist_download(event):
    url = event.pattern_match.group(1)
    msg = await event.reply("📂 **Downloading playlist...**")

    try:
        options = {
            "outtmpl": f"{DOWNLOAD_DIR}/%(title)s.%(ext)s",
            "format": "best",
            "merge_output_format": "mp4",
            "quiet": True,
        }
        async with yt_dlp.YoutubeDL(options) as ydl:
            info = await asyncio.to_thread(ydl.extract_info, url, download=True)
        
        for entry in info["entries"]:
            file_path = f"{DOWNLOAD_DIR}/{entry['title']}.mp4"
            await upload_video(file_path, entry["title"], event)

    except Exception as e:
        await event.reply(f"❌ **Error:** {str(e)}")

    finally:
        await msg.delete()

# Start the bot
print("🚀 Bot is running...")
bot.run_until_disconnected()
