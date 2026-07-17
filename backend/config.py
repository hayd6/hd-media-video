import os
import shutil
import imageio_ffmpeg

# Thư mục gốc dự án
BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(BACKEND_DIR)

# Tự động nạp file .env ở thư mục gốc (nếu có)
ENV_FILE = os.path.join(BASE_DIR, ".env")
if os.path.exists(ENV_FILE):
    with open(ENV_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                os.environ[key.strip()] = val.strip()

# Thư mục chứa dữ liệu tạm và đầu ra
DATA_DIR = os.path.join(BASE_DIR, "data")
DOWNLOAD_DIR = os.path.join(DATA_DIR, "downloads")
OUTPUT_DIR = os.path.join(DATA_DIR, "outputs")

# Đảm bảo các thư mục tồn tại
os.makedirs(DOWNLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Thư mục bin chứa các file thực thi cần thiết
BIN_DIR = os.path.join(BACKEND_DIR, "bin")
os.makedirs(BIN_DIR, exist_ok=True)

# Đường dẫn ffmpeg tiêu chuẩn (sử dụng bản copy từ imageio-ffmpeg để yt-dlp nhận diện được)
FFMPEG_PATH = os.path.join(BIN_DIR, "ffmpeg.exe")

if not os.path.exists(FFMPEG_PATH):
    # Sao chép và đổi tên file từ imageio-ffmpeg sang ffmpeg.exe
    bundled_exe = imageio_ffmpeg.get_ffmpeg_exe()
    try:
        shutil.copy2(bundled_exe, FFMPEG_PATH)
        print(f"Đã sao chép thành công ffmpeg sang {FFMPEG_PATH}")
    except Exception as e:
        print(f"Lỗi khi sao chép ffmpeg: {e}")
        # Fallback về đường dẫn gốc của imageio
        FFMPEG_PATH = bundled_exe

# Cấu hình log
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

# Cấu hình AI Provider
AI_PROVIDER = os.environ.get("AI_PROVIDER", "ollama").lower()
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen3:7b")

# Tên model Gemini
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")

# Danh sách giọng nói lồng tiếng chuẩn (Không biến đổi pitch/Hz)
VOICES_CONFIG = {
    "vi-VN-HoaiMyNeural": {
        "name": "Hoài My (Nữ)",
        "voice": "vi-VN-HoaiMyNeural",
        "rate": "+0%",
        "pitch": "+0Hz"
    },
    "vi-VN-NamMinhNeural": {
        "name": "Nam Minh (Nam)",
        "voice": "vi-VN-NamMinhNeural",
        "rate": "+0%",
        "pitch": "+0Hz"
    },
    "en-US-AriaNeural": {
        "name": "Aria (Nữ)",
        "voice": "en-US-AriaNeural",
        "rate": "+0%",
        "pitch": "+0Hz"
    },
    "en-US-JennyNeural": {
        "name": "Jenny (Nữ)",
        "voice": "en-US-JennyNeural",
        "rate": "+0%",
        "pitch": "+0Hz"
    },
    "en-US-GuyNeural": {
        "name": "Guy (Nam)",
        "voice": "en-US-GuyNeural",
        "rate": "+0%",
        "pitch": "+0Hz"
    },
    "en-US-ChristopherNeural": {
        "name": "Christopher (Nam)",
        "voice": "en-US-ChristopherNeural",
        "rate": "+0%",
        "pitch": "+0Hz"
    }
}
