import time
import database
from queue_manager import job_queue

def test_flow():
    print("--- KHỞI TẠO TEST DB VÀ WORKER ---")
    database.init_db()
    job_queue.start()
    
    # Sử dụng một video ngắn để kiểm thử tải xuống và trích xuất âm thanh
    test_url = "https://www.youtube.com/shorts/tPEE9ZwTmy0"
    
    print(f"Tạo Job mới với URL: {test_url}...")
    job = database.create_job(
        url=test_url,
        target_lang="Vietnamese",
        voice="vi-VN-NamMinhNeural",
        mode="standard"
    )
    job_id = job["id"]
    print(f"Đã tạo Job ID: {job_id}")
    
    # Cho job vào queue
    job_queue.add_job(job_id)

    # Đợi worker xử lý (tải thực tế + trích xuất + giả lập các bước sau)
    print("\nĐang đợi luồng worker chạy thử nhiệm vụ...")
    # Tăng thời gian chờ lên vì cần tải thực tế (khoảng 30-40 giây tối đa cho shorts ngắn)
    for i in range(60):
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
            
    # Hiển thị đường dẫn file đã tải
    final_job = database.get_job(job_id)
    if final_job and final_job["status"] == "completed":
        print("\n--- KẾT QUẢ TẢI VÀ CHIẾT XUẤT FILE ---")
        print(f"Video path: {final_job.get('video_path')}")
        print(f"Audio path: {final_job.get('audio_path')}")
        
    job_queue.stop()
    print("\n--- KẾT THÚC KIỂM TRA ---")

if __name__ == "__main__":
    test_flow()
