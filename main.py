import os
import asyncio
import yt_dlp
import aiofiles
import ffmpeg
from PIL import Image
from telethon import TelegramClient, events, Button
from telethon.tl.types import DocumentAttributeVideo
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Initialize Telegram Bot
bot = TelegramClient("bot_session", API_ID, API_HASH).start(bot_token=BOT_TOKEN)

# Constants
DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# yt-dlp Default Options
YDL_OPTIONS = {
    "quiet": True,
    "noprogress": True,
    "format": "bv+ba/best",
    "merge_output_format": "mp4",
    "postprocessors": [{"key": "FFmpegVideoConvertor"}],
    "writesubtitles": True,
    "subtitleslangs": ["en", "es", "fr"],
    "retries": 3,
    "fragment_retries": 5,
    "socket_timeout": 10,
}

# Extract Available Qualities
async def get_available_qualities(url):
    options = YDL_OPTIONS.copy()
    options["list_formats"] = True
    ydl = yt_dlp.YoutubeDL(options)
    info = await asyncio.to_thread(ydl.extract_info, url, download=False)

    formats = [
        {"id": fmt["format_id"], "res": fmt["resolution"], "ext": fmt["ext"]}
        for fmt in info.get("formats", [])
        if "resolution" in fmt
    ]
    
    return formats

# Download Video
async def download_video(url, format_id=None):
    options = YDL_OPTIONS.copy()
    options["outtmpl"] = f"{DOWNLOAD_DIR}/%(title)s.%(ext)s"
    if format_id:
        options["format"] = format_id

    ydl = yt_dlp.YoutubeDL(options)
    info = await asyncio.to_thread(ydl.extract_info, url, download=True)

    title = info.get("title", "video")
    caption = info.get("description", "")
    thumbnail_url = info.get("thumbnail", None)

    file_path = ydl.prepare_filename(info)
    thumb_path = f"{DOWNLOAD_DIR}/{title}.jpg" if thumbnail_url else None

    if thumbnail_url:
        await extract_thumbnail(thumbnail_url, thumb_path)

    return file_path, title, caption, thumb_path

# Extract Thumbnail
async def extract_thumbnail(thumbnail_url, save_path):
    try:
        async with yt_dlp.YoutubeDL({"quiet": True}) as ydl:
            await asyncio.to_thread(ydl.download, [thumbnail_url])
        img = Image.open(save_path)
        img.thumbnail((320, 320))
        img.save(save_path)
    except Exception:
        return None

# Upload Video
async def upload_video(file_path, title, caption, thumb_path, event):
    chat_id = event.chat_id
    msg = await event.reply(f"📤 **Uploading {title}...**")

    try:
        async with aiofiles.open(file_path, "rb") as f:
            video_data = await f.read()  # Read file in binary mode

        await bot.send_file(
            chat_id,
            file=video_data,
            caption=f"🎥 **{title}**\n\n{caption[:1024]}",
            attributes=[DocumentAttributeVideo(duration=0, w=1920, h=1080)],
            thumb=thumb_path,
        )

        os.remove(file_path)
        if thumb_path:
            os.remove(thumb_path)

    except Exception as e:
        await msg.edit(f"❌ **Upload Error:** {str(e)}")
    finally:
        await msg.delete()

# Handle Video URL (Quality Selection)
@bot.on(events.NewMessage)
async def process_url(event):
    url = event.text.strip()
    if not url.startswith(("http://", "https://")):
        return

    msg = await event.reply("🔍 **Fetching available video qualities...**")
    
    try:
        formats = await get_available_qualities(url)

        if len(formats) <= 1:
            await msg.edit("📥 **Downloading best available quality...**")
            file_path, title, caption, thumb_path = await download_video(url)
            await upload_video(file_path, title, caption, thumb_path, event)
            return
        
        buttons = []
        for i, fmt in enumerate(formats):
            if i % 3 == 0:
                buttons.append([])  # Start new row every 3 buttons
            buttons[-1].append(Button.inline(f"{fmt['res']} - {fmt['ext']}", data=f"{url}|{fmt['id']}"))
        
        buttons.append([Button.inline("⏩ Skip (Best Quality)", data=f"{url}|best")])

        await msg.edit("🎥 **Select video quality:**", buttons=buttons)
    
    except Exception as e:
        await msg.edit(f"❌ **Error:** {str(e)}")

# Handle Quality Selection
@bot.on(events.CallbackQuery)
async def quality_selected(event):
    url, format_id = event.data.decode().split("|")
    msg = await event.edit("📥 **Downloading selected quality...**")

    file_path, title, caption, thumb_path = await download_video(url, format_id=format_id)
    await upload_video(file_path, title, caption, thumb_path, event)

bot.run_until_disconnected()
