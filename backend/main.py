import os
from typing import List, Optional
from datetime import datetime
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, status, BackgroundTasks
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import database
import drive_service
from queue_manager import job_queue
from config import OUTPUT_DIR

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Khởi chạy: Khởi tạo database SQLite và chạy background queue thread
    database.init_db()
    job_queue.start()
    yield
    # Dừng: Tắt background queue thread
    job_queue.stop()

app = FastAPI(
    title="HD Media - AI Video Translator API",
    description="Backend API bằng SQLite + Python cho HD Media",
    version="1.1",
    lifespan=lifespan
)

# Cấu hình CORS để cho phép Frontend kết nối
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Phục vụ thư mục chứa file đầu ra để Frontend phát video và download trực tiếp
app.mount("/outputs", StaticFiles(directory=OUTPUT_DIR), name="outputs")

@app.get("/", response_class=HTMLResponse)
def read_root():
    html_path = os.path.join(os.path.dirname(__file__), "templates", "index.html")
    if os.path.exists(html_path):
        with open(html_path, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>HD Media API is running. Template not found.</h1>"

# API schemas sử dụng Pydantic
class JobCreate(BaseModel):
    url: str
    target_lang: Optional[str] = "Vietnamese"
    voice: Optional[str] = "vi-VN-HoaiMyNeural"
    mode: Optional[str] = "standard"
    
    # Tùy chọn Reup Mode
    speed: Optional[float] = 1.0
    brightness: Optional[float] = 0.0
    contrast: Optional[float] = 0.0
    saturation: Optional[float] = 0.0
    sharpen: Optional[bool] = False
    denoise: Optional[bool] = False
    mirror: Optional[str] = "none"
    crop: Optional[str] = "none"
    resize: Optional[str] = "none"
    watermark_opacity: Optional[float] = 0.5
    watermark_size: Optional[float] = 0.15
    watermark_position: Optional[str] = "bottom_right"
    bg_music_volume: Optional[float] = 0.1

class JobResponse(BaseModel):
    id: int
    status: str
    progress: int
    current_step: str
    url: str
    target_lang: str
    voice: str
    mode: str
    created_at: str
    finished_at: Optional[str] = None
    processing_time: Optional[float] = None
    drive_link: Optional[str] = None
    error_message: Optional[str] = None

    class Config:
        from_attributes = True

# --- API Endpoints: Jobs & History ---

@app.post("/api/jobs", response_model=JobResponse, status_code=status.HTTP_201_CREATED)
def create_job(payload: JobCreate):
    try:
        # Chuyển payload thành dict để tạo job trong DB
        job_data = payload.model_dump()
        job = database.create_job(**job_data)
        
        # Đưa Job vào hàng đợi ngầm
        job_queue.add_job(job["id"])
        return job
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi khi tạo Job: {str(e)}")

@app.get("/api/jobs", response_model=List[JobResponse])
def get_jobs():
    return database.get_all_jobs()

@app.get("/api/jobs/{job_id}", response_model=JobResponse)
def get_job(job_id: int):
    job = database.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Không tìm thấy Job.")
    return job

@app.delete("/api/jobs/{job_id}", status_code=status.HTTP_200_OK)
def delete_job(job_id: int):
    success = database.delete_job(job_id)
    if not success:
        raise HTTPException(status_code=404, detail="Không tìm thấy Job hoặc không thể xóa.")
    return {"message": f"Đã xóa Job ID {job_id} thành công."}

@app.post("/api/jobs/{job_id}/retry", response_model=JobResponse)
def retry_job(job_id: int):
    job = database.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Không tìm thấy Job.")
    
    # Cập nhật trạng thái về pending và cho lại vào queue
    updated_job = database.update_job(
        job_id,
        status="pending",
        progress=0,
        current_step="Init",
        error_message=None,
        finished_at=None,
        processing_time=None
    )
    
    job_queue.add_job(job_id)
    return updated_job

@app.get("/api/jobs/{job_id}/logs")
def get_job_logs(job_id: int):
    job = database.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Không tìm thấy Job.")
    
    return database.get_job_logs(job_id)


# --- API Endpoints: Google Drive (Phục vụ các Phase sau) ---

@app.post("/api/google/login")
def google_login():
    return {"message": "Bắt đầu đăng nhập Google OAuth2 (Giả lập)..."}

@app.get("/api/google/status")
def google_status():
    return {"authenticated": drive_service.is_authenticated()}

def background_upload_task(job_id: int):
    # Cập nhật trạng thái bắt đầu upload
    database.update_job(job_id, drive_upload_status="uploading")
    database.add_job_log(job_id, "Drive", "Bắt đầu tải các tệp tin kết quả lên Google Drive...")
    
    job = database.get_job(job_id)
    if not job:
        return
        
    output_video_path = job.get("output_video_path")
    if not output_video_path or not os.path.exists(output_video_path):
        database.update_job(job_id, drive_upload_status="failed")
        database.add_job_log(job_id, "Drive", "Lỗi: Không tìm thấy file video đã kết xuất.")
        return
        
    output_dir = os.path.dirname(output_video_path)
    
    # Thu thập tất cả các tài nguyên của job để tải lên thư mục tương ứng trên Drive
    assets = {
        "video": output_video_path,
        "subtitle_ass": job.get("ass_path"),
        "subtitle_srt": job.get("srt_path"),
        "audio": job.get("dubbed_audio_path"),
        "thumbnail": job.get("thumbnail_path"),
        "seo": os.path.join(output_dir, f"job_{job_id}_seo.txt")
    }
    
    try:
        drive_res = drive_service.upload_job_assets(job_id, assets)
        database.update_job(
            job_id,
            drive_link=drive_res.get("drive_link"),
            drive_file_id=drive_res.get("drive_file_id"),
            drive_upload_status=drive_res.get("drive_upload_status")
        )
        if drive_res.get("drive_upload_status") == "completed":
            database.add_job_log(job_id, "Drive", f"Tải lên Google Drive thành công! Link: {drive_res.get('drive_link')}")
        else:
            database.add_job_log(job_id, "Drive", f"Tải lên Google Drive thất bại: {drive_res.get('error_message')}")
    except Exception as e:
        database.update_job(job_id, drive_upload_status="failed")
        database.add_job_log(job_id, "Drive", f"Lỗi xảy ra khi upload: {str(e)}")

@app.post("/api/google/upload/{job_id}")
def google_upload(job_id: int, background_tasks: BackgroundTasks):
    job = database.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Không tìm thấy Job.")
    if job["status"] != "completed":
        raise HTTPException(status_code=400, detail="Video chưa được render hoàn chỉnh. Không thể tải lên.")
        
    # Thêm background task để upload không làm nghẽn API chính
    background_tasks.add_task(background_upload_task, job_id)
    return {"message": f"Đã bắt đầu tải video của Job {job_id} lên Google Drive trong nền."}

@app.get("/api/google/files/{job_id}")
def get_drive_files(job_id: int):
    return {
        "job_id": job_id,
        "files": [
            {"name": "video.mp4", "id": "mock_id_video"},
            {"name": "subtitle.ass", "id": "mock_id_ass"},
            {"name": "thumbnail.jpg", "id": "mock_id_thumb"}
        ]
    }

@app.delete("/api/google/file/{file_id}")
def delete_drive_file(file_id: str):
    return {"message": f"Đã xóa file ID {file_id} trên Google Drive."}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
