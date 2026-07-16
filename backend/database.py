import sqlite3
import os
from datetime import datetime
from typing import Optional, List, Dict, Any

# SQLite database file path
DB_FILE = os.path.join(os.path.dirname(__file__), "hd_media.db")

def get_db_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Tạo bảng jobs
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS jobs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        status TEXT DEFAULT 'pending',
        progress INTEGER DEFAULT 0,
        current_step TEXT DEFAULT 'Init',
        url TEXT NOT NULL,
        
        target_lang TEXT DEFAULT 'Vietnamese',
        voice TEXT DEFAULT 'vi-VN-HoaiMyNeural',
        mode TEXT DEFAULT 'standard',
        
        video_path TEXT,
        audio_path TEXT,
        srt_path TEXT,
        ass_path TEXT,
        dubbed_audio_path TEXT,
        bg_music_path TEXT,
        output_video_path TEXT,
        thumbnail_path TEXT,
        
        speed REAL DEFAULT 1.0,
        brightness REAL DEFAULT 0.0,
        contrast REAL DEFAULT 0.0,
        saturation REAL DEFAULT 0.0,
        sharpen INTEGER DEFAULT 0,
        denoise INTEGER DEFAULT 0,
        mirror TEXT DEFAULT 'none',
        crop TEXT DEFAULT 'none',
        resize TEXT DEFAULT 'none',
        watermark_path TEXT,
        watermark_opacity REAL DEFAULT 0.5,
        watermark_size REAL DEFAULT 0.15,
        watermark_position TEXT DEFAULT 'bottom_right',
        intro_path TEXT,
        outro_path TEXT,
        bg_music_volume REAL DEFAULT 0.1,
        
        drive_link TEXT,
        drive_file_id TEXT,
        drive_upload_status TEXT DEFAULT 'none',
        
        seo_title TEXT,
        seo_description TEXT,
        seo_tags TEXT,
        
        error_message TEXT,
        created_at TEXT NOT NULL,
        finished_at TEXT,
        processing_time REAL
    )
    """)
    
    # Tạo bảng job_logs
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS job_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        job_id INTEGER NOT NULL,
        timestamp TEXT NOT NULL,
        step TEXT NOT NULL,
        message TEXT NOT NULL,
        FOREIGN KEY (job_id) REFERENCES jobs (id) ON DELETE CASCADE
    )
    """)
    conn.commit()
    conn.close()

def row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    """Chuyển đổi một dòng dữ liệu từ sqlite3 sang dictionary, xử lý kiểu boolean và datetime."""
    if row is None:
        return {}
    d = dict(row)
    # Chuyển các trường ngày tháng sang datetime object nếu cần
    for time_key in ["created_at", "finished_at"]:
        if d.get(time_key):
            try:
                # Trả về string isoformat phù hợp để API serialize dễ dàng
                pass
            except Exception:
                pass
    # Chuyển đổi boolean
    for bool_key in ["sharpen", "denoise"]:
        if bool_key in d:
            d[bool_key] = bool(d[bool_key])
    return d

def create_job(url: str, target_lang: str, voice: str, mode: str, **kwargs) -> Dict[str, Any]:
    conn = get_db_connection()
    cursor = conn.cursor()
    
    created_at = datetime.utcnow().isoformat()
    
    fields = ["url", "target_lang", "voice", "mode", "created_at", "status"]
    values = [url, target_lang, voice, mode, created_at, "pending"]
    
    for k, v in kwargs.items():
        # Chỉ nhận các trường hợp lệ trong database
        if k in [
            "speed", "brightness", "contrast", "saturation", "sharpen", "denoise",
            "mirror", "crop", "resize", "watermark_opacity", "watermark_size",
            "watermark_position", "bg_music_volume", "watermark_path", "intro_path", "outro_path"
        ]:
            fields.append(k)
            # Chuyển đổi boolean thành integer cho SQLite
            if isinstance(v, bool):
                values.append(1 if v else 0)
            else:
                values.append(v)
                
    placeholders = ", ".join(["?"] * len(fields))
    columns = ", ".join(fields)
    
    query = f"INSERT INTO jobs ({columns}) VALUES ({placeholders})"
    cursor.execute(query, values)
    conn.commit()
    
    job_id = cursor.lastrowid
    cursor.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
    row = cursor.fetchone()
    conn.close()
    
    return row_to_dict(row)

def get_job(job_id: int) -> Optional[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return row_to_dict(row)
    return None

def get_all_jobs() -> List[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM jobs ORDER BY created_at DESC")
    rows = cursor.fetchall()
    conn.close()
    return [row_to_dict(row) for row in rows]

def update_job(job_id: int, **updates) -> Optional[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    
    set_clauses = []
    values = []
    
    for k, v in updates.items():
        set_clauses.append(f"{k} = ?")
        if isinstance(v, bool):
            values.append(1 if v else 0)
        elif isinstance(v, datetime):
            values.append(v.isoformat())
        else:
            values.append(v)
            
    if not set_clauses:
        conn.close()
        return get_job(job_id)
        
    values.append(job_id)
    query = f"UPDATE jobs SET {', '.join(set_clauses)} WHERE id = ?"
    cursor.execute(query, values)
    conn.commit()
    conn.close()
    return get_job(job_id)

def delete_job(job_id: int) -> bool:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
    conn.commit()
    affected = cursor.rowcount
    conn.close()
    return affected > 0

def add_job_log(job_id: int, step: str, message: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    timestamp = datetime.utcnow().isoformat()
    cursor.execute(
        "INSERT INTO job_logs (job_id, timestamp, step, message) VALUES (?, ?, ?, ?)",
        (job_id, timestamp, step, message)
    )
    conn.commit()
    conn.close()

def get_job_logs(job_id: int) -> List[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM job_logs WHERE job_id = ? ORDER BY timestamp ASC", (job_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]
