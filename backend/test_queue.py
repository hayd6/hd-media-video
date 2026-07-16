import os
import time
import database
from queue_manager import job_queue

# Import config để kích hoạt tính năng đọc .env tự động
import config

def test_flow():
    print("--- KHỞI TẠO TEST DB VÀ WORKER ---")
    
    # Kiểm tra khóa API Gemini
    gemini_key = os.environ.get("GEMINI_API_KEY")
    if not gemini_key:
        print("\n==================================================")
        print("[CẢNH BÁO] Không tìm thấy biến môi trường GEMINI_API_KEY hoặc file .env.")
        print("Vui lòng tạo một file tên '.env' tại thư mục gốc dự án (D:\\HuyD\\AI\\.env) với nội dung:")
        print("GEMINI_API_KEY=khóa_api_gemini_của_bạn")
        print("Sau đó chạy lại script test này.")
        print("==================================================\n")
        return
        
    database.init_db()
    job_queue.start()
    
    # Sử dụng một video ngắn để kiểm thử tải xuống, trích xuất âm thanh, nhận diện và dịch thuật
    test_url = "https://www.youtube.com/shorts/tPEE9ZwTmy0"
    
    print(f"Tạo Job mới với URL: {test_url}...")
    job = database.create_job(
        url=test_url,
        target_lang="Vietnamese",
        voice="vi-VN-NamMinhNeural",
        mode="standard",
        gemini_key=gemini_key
    )
    job_id = job["id"]
    print(f"Đã tạo Job ID: {job_id}")
    
    # Cho job vào queue
    job_queue.add_job(job_id)

    # Đợi worker xử lý (tải thực tế + trích xuất + gọi API Gemini thực tế + giả lập các bước sau)
    print("\nĐang đợi luồng worker chạy thử nhiệm vụ...")
    # Tăng thời gian chờ lên tối đa 90 giây vì có gọi thêm API Gemini nhận diện và dịch thuật
    for i in range(90):
        time.sleep(1)
        current_job = database.get_job(job_id)
        if current_job:
            print(f"Giây {i+1}: Trạng thái={current_job['status']}, Tiến độ={current_job['progress']}%, Bước={current_job['current_step']}")
            if current_job["status"] in ["completed", "failed"]:
                break
        else:
            print(f"Giây {i+1}: Không tìm thấy Job!")
    
    # In ra toàn bộ logs của Job
    print("\n--- NHẬT KÝ CHI TIẾT (LOGS) TRONG DATABASE ---")
    logs = database.get_job_logs(job_id)
    for log in logs:
        print(f"[{log['timestamp']}] [{log['step']}] {log['message']}")
            
    # Hiển thị kết quả của các file đầu ra
    final_job = database.get_job(job_id)
    if final_job and final_job["status"] == "completed":
        print("\n--- KẾT QUẢ CÁC PHÂN ĐOẠN ĐÃ XỬ LÝ ---")
        print(f"Video gốc: {final_job.get('video_path')}")
        print(f"Âm thanh gốc: {final_job.get('audio_path')}")
        print(f"Phụ đề dịch (SRT): {final_job.get('srt_path')}")
        print(f"Phụ đề dịch (ASS): {final_job.get('ass_path')}")
    elif final_job and final_job["status"] == "failed":
        print("\n--- LỖI XẢY RA KHI CHẠY JOB ---")
        print(f"Chi tiết lỗi: {final_job.get('error_message')}")
        
    job_queue.stop()
    print("\n--- KẾT THÚC KIỂM TRA ---")

if __name__ == "__main__":
    test_flow()
