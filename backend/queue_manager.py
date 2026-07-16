import queue
import threading
import logging
import time
from datetime import datetime
import database
import downloader

logger = logging.getLogger("queue_manager")
logging.basicConfig(level=logging.INFO)

def add_log(job_id: int, step: str, message: str):
    database.add_job_log(job_id, step, message)
    logger.info(f"[Job {job_id}][{step}] {message}")

def execute_pipeline(job_id: int):
    """
    Quy trình xử lý video Pipeline chính.
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
        # --- BƯỚC 2: TẢI VIDEO & TRÍCH XUẤT ÂM THANH (PHASE 2) ---
        database.update_job(job_id, current_step="Download", progress=0)
        
        last_logged_pct = -5
        
        def update_download_progress(pct, stage):
            nonlocal last_logged_pct
            # Tính toán tiến trình tổng quan của Job cho bước Download (tổng cộng chiếm 20%)
            if stage == "downloading":
                # Tải xuống chiếm 85% của bước Download (tối đa 17% tổng tiến trình)
                overall_pct = int(pct * 0.85)
                # Chỉ log mỗi 10% để tránh nghẽn DB/Log
                if pct - last_logged_pct >= 10:
                    add_log(job_id, "Download", f"Đang tải video: {pct}%")
                    last_logged_pct = pct
            elif stage == "extracting_audio":
                overall_pct = 18
                add_log(job_id, "Download", "Đang trích xuất âm thanh từ video...")
            else:  # audio_extracted
                overall_pct = 20
                add_log(job_id, "Download", "Đã trích xuất xong âm thanh thành công.")
                
            database.update_job(job_id, progress=overall_pct)

        # Chạy tải video
        video_path = downloader.download_video(
            job["url"], 
            job_id, 
            update_progress_fn=update_download_progress
        )
        
        # Chạy trích xuất âm thanh
        audio_path = downloader.extract_audio(
            video_path, 
            job_id, 
            update_progress_fn=update_download_progress
        )
        
        # Cập nhật đường dẫn file vào DB
        database.update_job(
            job_id, 
            video_path=video_path, 
            audio_path=audio_path
        )
        
        # --- CÁC BƯỚC KHÁC (GIẢ LẬP - SẼ CẬP NHẬT Ở CÁC PHASE SAU) ---
        
        # 3. Speech Recognition
        database.update_job(job_id, current_step="Speech Recognition", progress=35)
        add_log(job_id, "Speech Recognition", "Đang nhận dạng giọng nói từ file âm thanh (sử dụng faster-whisper)...")
        time.sleep(2)
        
        # 4. Translate
        database.update_job(job_id, current_step="Translate", progress=55)
        add_log(job_id, "Translate", f"Đang dịch nội dung phụ đề sang ngôn ngữ {job['target_lang']} bằng Gemini API...")
        time.sleep(2)
        
        # 5. Voice Generation (TTS)
        database.update_job(job_id, current_step="Voice", progress=75)
        add_log(job_id, "Voice", f"Đang sinh giọng nói lồng tiếng với cấu hình giọng {job['voice']} (sử dụng Edge TTS)...")
        time.sleep(2)
        
        # 6. Render Video
        database.update_job(job_id, current_step="Render", progress=90)
        add_log(job_id, "Render", "Đang kết hợp phụ đề ASS, nhạc nền gốc và giọng lồng tiếng mới (sử dụng FFmpeg)...")
        time.sleep(2)
        
        # 7. Complete
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
        add_log(job_id, "Done", "Hoàn thành xử lý video thành công!")
        
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
