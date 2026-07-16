import os
import queue
import threading
import logging
import subprocess
import json
from datetime import datetime
import pysubs2

import database
import downloader
import gemini_service
import tts_service
import video_service
import drive_service
from config import DOWNLOAD_DIR, OUTPUT_DIR, FFMPEG_PATH

logger = logging.getLogger("queue_manager")
logging.basicConfig(level=logging.INFO)

def add_log(job_id: int, step: str, message: str):
    database.add_job_log(job_id, step, message)
    logger.info(f"[Job {job_id}][{step}] {message}")

def save_segments_to_subtitle(segments: list, output_path: str):
    """
    Chuyển đổi danh sách phân đoạn JSON sang file phụ đề (SRT hoặc ASS) sử dụng pysubs2.
    """
    subs = pysubs2.SSAFile()
    for seg in segments:
        start_ms = int(seg["start"] * 1000)
        end_ms = int(seg["end"] * 1000)
        text = seg["text"].replace("\n", " ").strip()
        event = pysubs2.SSAEvent(start=start_ms, end=end_ms, text=text)
        subs.append(event)
    subs.save(output_path)

def execute_pipeline(job_id: int):
    """
    Quy trình xử lý video Pipeline chính - Đầy đủ tất cả các bước.
    """
    job = database.get_job(job_id)
    if not job:
        logger.error(f"Job {job_id} không tồn tại trong database.")
        return
    
    database.update_job(
        job_id,
        status="running",
        progress=0,
        current_step="Init"
    )
    add_log(job_id, "Init", "Bắt đầu xử lý Job dịch video.")
    
    try:
        # Lấy API Key từ cấu hình Job hoặc biến môi trường
        gemini_key = job.get("gemini_key") or os.environ.get("GEMINI_API_KEY")
        if not gemini_key:
            raise ValueError(
                "Không tìm thấy Gemini API Key. Vui lòng truyền khóa API trong yêu cầu "
                "hoặc thiết lập biến môi trường GEMINI_API_KEY."
            )

        # --- BƯỚC 2: TẢI VIDEO & TRÍCH XUẤT ÂM THANH (PHASE 2) ---
        database.update_job(job_id, current_step="Download", progress=0)
        
        last_logged_pct = -5
        
        def update_download_progress(pct, stage):
            nonlocal last_logged_pct
            if stage == "downloading":
                overall_pct = int(pct * 0.15)  # 0% - 15% tổng tiến trình
                if pct - last_logged_pct >= 10:
                    add_log(job_id, "Download", f"Đang tải video: {pct}%")
                    last_logged_pct = pct
            elif stage == "extracting_audio":
                overall_pct = 17
                add_log(job_id, "Download", "Đang trích xuất âm thanh từ video...")
            else:  # audio_extracted
                overall_pct = 20
                add_log(job_id, "Download", "Đã trích xuất xong âm thanh thành công.")
                
            database.update_job(job_id, progress=overall_pct)

        # 1. Tải video gốc
        video_path = downloader.download_video(
            job["url"], 
            job_id, 
            update_progress_fn=update_download_progress
        )
        
        # 2. Trích xuất âm thanh WAV gốc
        audio_path = downloader.extract_audio(
            video_path, 
            job_id, 
            update_progress_fn=update_download_progress
        )
        
        database.update_job(job_id, video_path=video_path, audio_path=audio_path)
        
        # Lấy thời lượng video
        total_duration = tts_service.get_audio_duration(video_path)
        add_log(job_id, "Download", f"Thời lượng video gốc: {total_duration:.2f} giây.")

        # --- BƯỚC 3: NHẬN DIỆN GIỌNG NÓI (PHASE 3) ---
        database.update_job(job_id, current_step="Speech Recognition", progress=25)
        add_log(job_id, "Speech Recognition", "Đang gọi Gemini API để nhận dạng giọng nói...")
        
        original_segments = gemini_service.transcribe_audio(audio_path, gemini_key)
        
        # Lưu file transcript JSON gốc
        transcript_json_path = os.path.join(DOWNLOAD_DIR, f"job_{job_id}_transcript.json")
        with open(transcript_json_path, "w", encoding="utf-8") as f:
            json.dump(original_segments, f, ensure_ascii=False, indent=2)
            
        original_srt_path = os.path.join(DOWNLOAD_DIR, f"job_{job_id}_original.srt")
        save_segments_to_subtitle(original_segments, original_srt_path)
        
        database.update_job(job_id, srt_path=original_srt_path, progress=40)
        add_log(job_id, "Speech Recognition", f"Nhận dạng thành công {len(original_segments)} phân đoạn hội thoại.")

        # --- BƯỚC 4: DỊCH THUẬT AI (PHASE 4) ---
        database.update_job(job_id, current_step="Translate", progress=45)
        add_log(job_id, "Translate", f"Đang dịch phụ đề sang tiếng {job['target_lang']} bằng Gemini API...")
        
        translated_segments = gemini_service.translate_segments(
            original_segments, 
            job["target_lang"], 
            gemini_key
        )
        
        translated_srt_path = os.path.join(OUTPUT_DIR, f"job_{job_id}_translated.srt")
        translated_ass_path = os.path.join(OUTPUT_DIR, f"job_{job_id}_translated.ass")
        
        save_segments_to_subtitle(translated_segments, translated_srt_path)
        save_segments_to_subtitle(translated_segments, translated_ass_path)
        
        database.update_job(
            job_id, 
            srt_path=translated_srt_path, 
            ass_path=translated_ass_path, 
            progress=55
        )
        add_log(job_id, "Translate", "Dịch thuật phụ đề hoàn tất.")

        # --- BƯỚC 5: LỒNG TIẾNG AI (TTS) & AUDIO DUCKING (PHASE 5) ---
        database.update_job(job_id, current_step="Voice", progress=60)
        add_log(job_id, "Voice", "Đang sinh giọng nói lồng tiếng tự động (Edge TTS)...")
        
        # 1. Sinh file lồng tiếng của các phân đoạn và trộn thành file dubbed WAV dài bằng video gốc
        dubbed_audio_path = tts_service.generate_dubbed_track(
            translated_segments,
            job["voice"],
            total_duration,
            job_id
        )
        
        # 2. Áp dụng hiệu ứng Audio Ducking (giảm âm lượng nhạc nền gốc và trộn với giọng lồng tiếng mới)
        mixed_audio_path = os.path.join(DOWNLOAD_DIR, f"job_{job_id}_mixed.wav")
        add_log(job_id, "Voice", "Đang áp dụng hiệu ứng giảm âm lượng nhạc nền (Audio Ducking)...")
        
        tts_service.apply_audio_ducking(
            audio_path,
            dubbed_audio_path,
            translated_segments,
            job.get("bg_music_volume", 0.1),
            mixed_audio_path
        )
        
        database.update_job(job_id, dubbed_audio_path=mixed_audio_path, progress=75)
        add_log(job_id, "Voice", "Hoàn thành sinh giọng đọc lồng tiếng và trộn âm thanh.")

        # --- BƯỚC 6: RENDER VIDEO & REUP MODE (PHASE 6) ---
        database.update_job(job_id, current_step="Render", progress=80)
        add_log(job_id, "Render", "Đang tiến hành kết xuất video hoàn chỉnh (ghép phụ đề, audio lồng tiếng)...")
        
        output_video_path = os.path.join(OUTPUT_DIR, f"job_{job_id}_finished.mp4")
        
        # Chạy kết xuất video (bao gồm chèn phụ đề ASS, watermark, chỉnh sáng/tốc độ của Reup Mode)
        video_service.render_video(
            video_path,
            mixed_audio_path,
            translated_ass_path,
            output_video_path,
            job
        )
        
        database.update_job(job_id, output_video_path=output_video_path, progress=90)
        add_log(job_id, "Render", "Đã kết xuất thành công video cuối cùng.")

        # --- BƯỚC 7: SEO, THUMBNAIL & GOOGLE DRIVE UPLOAD (PHASE 7) ---
        database.update_job(job_id, current_step="SEO & Upload", progress=92)
        
        # 1. Tự động sinh hình thu nhỏ (Thumbnail) từ giây thứ 2.0 của video
        thumbnail_path = os.path.join(OUTPUT_DIR, f"job_{job_id}_thumbnail.jpg")
        thumb_cmd = [
            FFMPEG_PATH, "-y",
            "-ss", "2.0",
            "-i", video_path,
            "-vframes", "1",
            "-q:v", "2",
            thumbnail_path
        ]
        subprocess.run(
            thumb_cmd, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE, 
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        )
        database.update_job(job_id, thumbnail_path=thumbnail_path)
        add_log(job_id, "SEO & Upload", "Đã xuất hình thu nhỏ (Thumbnail) thành công.")
        
        # 2. Tạo nội dung SEO bằng Gemini API
        add_log(job_id, "SEO & Upload", "Đang tạo tiêu đề và mô tả video tối ưu SEO...")
        transcript_text = " ".join([seg["text"] for seg in translated_segments])
        seo_data = gemini_service.generate_seo(transcript_text, job["target_lang"], gemini_key)
        
        # Lưu nội dung SEO ra file txt
        seo_txt_path = os.path.join(OUTPUT_DIR, f"job_{job_id}_seo.txt")
        with open(seo_txt_path, "w", encoding="utf-8") as f:
            f.write(f"TIÊU ĐỀ SEO:\n{seo_data['title']}\n\n")
            f.write(f"MÔ TẢ VIDEO:\n{seo_data['description']}\n\n")
            f.write(f"HASHTAGS:\n{seo_data['tags']}\n")
            
        database.update_job(
            job_id,
            seo_title=seo_data["title"],
            seo_description=seo_data["description"],
            seo_tags=seo_data["tags"]
        )
        add_log(job_id, "SEO & Upload", "Đã lưu nội dung SEO thành công.")
        
        # 3. Tải lên Google Drive thủ công (Người dùng sẽ bấm nút chọn tải lên từ giao diện)
        database.update_job(job_id, drive_upload_status="none")
        add_log(job_id, "SEO & Upload", "Hoàn tất sinh Thumbnail và SEO. Video đã sẵn sàng để xem/tải về trên Dashboard.")

        # --- BƯỚC 8: HOÀN THÀNH ---
        finished_at = datetime.utcnow()
        created_at_dt = datetime.fromisoformat(job['created_at'])
        processing_time = (finished_at - created_at_dt).total_seconds()
        
        database.update_job(
            job_id,
            status="completed",
            progress=100,
            current_step="Done",
            finished_at=finished_at,
            processing_time=processing_time
        )
        add_log(job_id, "Done", "Hoàn thành toàn bộ quy trình dịch video thành công!")
        
    except Exception as e:
        database.update_job(
            job_id,
            status="failed",
            progress=0,
            error_message=str(e),
            finished_at=datetime.utcnow()
        )
        add_log(job_id, "Error", f"Lỗi xảy ra trong quá trình xử lý: {str(e)}")

class JobQueue:
    def __init__(self):
        self.queue = queue.Queue()
        self.worker_thread = None
        self.running = False

    def start(self):
        if not self.worker_thread or not self.worker_thread.is_alive():
            self.running = True
            self.worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
            self.worker_thread.start()
            logger.info("Hàng đợi xử lý ngầm (Background Job Queue) đã khởi động.")

    def stop(self):
        self.running = False
        self.queue.put(None)
        if self.worker_thread:
            self.worker_thread.join()
            logger.info("Hàng đợi xử lý ngầm đã dừng.")

    def add_job(self, job_id: int):
        self.queue.put(job_id)
        logger.info(f"Đã thêm Job ID {job_id} vào hàng đợi.")

    def _worker_loop(self):
        while self.running:
            try:
                job_id = self.queue.get()
                if job_id is None:
                    break
                
                # Execute pipeline processing
                execute_pipeline(job_id)
                self.queue.task_done()
            except Exception as e:
                logger.error(f"Lỗi trong vòng lặp Worker: {str(e)}", exc_info=True)

# Singleton Instance
job_queue = JobQueue()
