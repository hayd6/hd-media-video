import os
import subprocess
import logging
import yt_dlp
import database
from config import DOWNLOAD_DIR, FFMPEG_PATH

logger = logging.getLogger("downloader")

def download_progress_hook(d, job_id, update_db_progress_fn):
    """
    Hook cập nhật tiến độ tải xuống từ yt-dlp vào cơ sở dữ liệu.
    """
    if d['status'] == 'downloading':
        # Tính toán phần trăm hoàn thành
        downloaded = d.get('downloaded_bytes', 0)
        total = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
        
        if total > 0:
            percentage = int((downloaded / total) * 100)
        else:
            # Nếu không lấy được dung lượng, lấy chuỗi hiển thị phần trăm từ yt-dlp
            percent_str = d.get('_percent_str', '0%').replace('%', '').strip()
            try:
                percentage = int(float(percent_str))
            except ValueError:
                percentage = 0
                
        if update_db_progress_fn:
            update_db_progress_fn(percentage, "downloading")

def download_video(url: str, job_id: int, update_progress_fn=None) -> str:
    """
    Tải video từ link URL sử dụng yt-dlp.
    Trả về đường dẫn tuyệt đối của video đã tải.
    """
    output_template = os.path.join(DOWNLOAD_DIR, f"job_{job_id}_video.%(ext)s")
    
    # Cấu hình yt-dlp, truyền thêm đường dẫn chứa thư mục ffmpeg
    ydl_opts = {
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'outtmpl': output_template,
        'noplaylist': True,
        'progress_hooks': [lambda d: download_progress_hook(d, job_id, update_progress_fn)],
        'logger': logger,
        'ffmpeg_location': os.path.dirname(FFMPEG_PATH),  # Chỉ định thư mục chứa ffmpeg cho yt-dlp
    }
    
    logger.info(f"[Job {job_id}] Bắt đầu tải video từ {url}...")
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)
        
        if not os.path.exists(filename):
            base_name = os.path.join(DOWNLOAD_DIR, f"job_{job_id}_video")
            for f in os.listdir(DOWNLOAD_DIR):
                if f.startswith(f"job_{job_id}_video"):
                    filename = os.path.join(DOWNLOAD_DIR, f)
                    break
                    
        logger.info(f"[Job {job_id}] Đã tải xong video: {filename}")
        return filename

def extract_audio(video_path: str, job_id: int, update_progress_fn=None) -> str:
    """
    Trích xuất âm thanh từ video đã tải sử dụng FFmpeg.
    Định dạng đầu ra: WAV (16kHz, Mono - Phù hợp nhất cho Whisper).
    """
    audio_path = os.path.join(DOWNLOAD_DIR, f"job_{job_id}_audio.wav")
    
    if update_progress_fn:
        update_progress_fn(90, "extracting_audio")
        
    logger.info(f"[Job {job_id}] Bắt đầu trích xuất âm thanh: {video_path} -> {audio_path}")
    
    # Lệnh chạy FFmpeg
    command = [
        FFMPEG_PATH,
        "-y",
        "-i", video_path,
        "-vn",
        "-acodec", "pcm_s16le",
        "-ar", "16000",
        "-ac", "1",
        audio_path
    ]
    
    process = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    )
    
    if process.returncode != 0:
        error_msg = process.stderr.decode('utf-8', errors='ignore')
        logger.error(f"[Job {job_id}] Lỗi khi chạy FFmpeg trích xuất âm thanh: {error_msg}")
        raise Exception(f"Không thể trích xuất âm thanh từ video: {error_msg}")
        
    if update_progress_fn:
        update_progress_fn(100, "audio_extracted")
        
    logger.info(f"[Job {job_id}] Đã trích xuất âm thanh thành công: {audio_path}")
    return audio_path
