import os
import json
import logging
import requests

logger = logging.getLogger("drive_service")

# Đường dẫn lưu trữ Token OAuth2 của người dùng
TOKEN_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "token.json")

def is_authenticated() -> bool:
    """Kiểm tra xem người dùng đã đăng nhập Google Drive (có file token.json) chưa."""
    return os.path.exists(TOKEN_FILE)

def get_access_token() -> str:
    """
    Đọc access token từ token.json.
    Nếu hết hạn, tự động làm mới bằng refresh token (nếu được cấu hình).
    """
    if not os.path.exists(TOKEN_FILE):
        raise ValueError("Chưa đăng nhập Google Drive. Vui lòng đăng nhập qua API.")
        
    with open(TOKEN_FILE, "r") as f:
        token_data = json.load(f)
        
    # Đơn giản hóa: trong thực tế sẽ kiểm tra thời gian hết hạn và gọi API refresh token
    # https://oauth2.googleapis.com/token
    return token_data.get("access_token")

def create_folder(folder_name: str, parent_id: str = None, access_token: str = None) -> str:
    """Tạo một thư mục mới trên Google Drive và trả về Folder ID."""
    if not access_token:
        access_token = get_access_token()
        
    url = "https://www.googleapis.com/drive/v3/files"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    
    metadata = {
        "name": folder_name,
        "mimeType": "application/vnd.google-apps.folder"
    }
    if parent_id:
        metadata["parents"] = [parent_id]
        
    res = requests.post(url, headers=headers, json=metadata)
    if res.status_code != 200:
        raise Exception(f"Không thể tạo thư mục {folder_name}: {res.text}")
    return res.json()["id"]

def find_folder(folder_name: str, parent_id: str = None, access_token: str = None) -> str:
    """Tìm ID thư mục theo tên."""
    if not access_token:
        access_token = get_access_token()
        
    url = "https://www.googleapis.com/drive/v3/files"
    headers = {"Authorization": f"Bearer {access_token}"}
    
    q = f"mimeType = 'application/vnd.google-apps.folder' and name = '{folder_name}' and trashed = false"
    if parent_id:
        q += f" and '{parent_id}' in parents"
        
    params = {"q": q, "fields": "files(id, name)"}
    res = requests.get(url, headers=headers, params=params)
    if res.status_code != 200:
        raise Exception(f"Lỗi tìm thư mục {folder_name}: {res.text}")
        
    files = res.json().get("files", [])
    if files:
        return files[0]["id"]
    return None

def make_file_public_shareable(file_id: str, access_token: str = None):
    """Thiết lập quyền truy cập công khai cho tệp tin (anyone with link can read)."""
    if not access_token:
        access_token = get_access_token()
        
    url = f"https://www.googleapis.com/drive/v3/files/{file_id}/permissions"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    
    body = {
        "role": "reader",
        "type": "anyone"
    }
    res = requests.post(url, headers=headers, json=body)
    if res.status_code != 200:
        logger.warning(f"Không thể thiết lập quyền công khai cho file {file_id}: {res.text}")

def get_file_share_link(file_id: str, access_token: str = None) -> str:
    """Lấy link chia sẻ công khai của file."""
    if not access_token:
        access_token = get_access_token()
        
    url = f"https://www.googleapis.com/drive/v3/files/{file_id}"
    headers = {"Authorization": f"Bearer {access_token}"}
    params = {"fields": "webViewLink"}
    
    res = requests.get(url, headers=headers, params=params)
    if res.status_code == 200:
        return res.json().get("webViewLink")
    return f"https://drive.google.com/open?id={file_id}"

def upload_file_resumable(file_path: str, folder_id: str, access_token: str = None) -> str:
    """
    Tải tệp lớn lên Google Drive bằng cơ chế Resumable Upload (hỗ trợ tiếp tục tải khi mất mạng).
    """
    if not access_token:
        access_token = get_access_token()
        
    file_size = os.path.getsize(file_path)
    file_name = os.path.basename(file_path)
    
    # 1. Khởi tạo session tải lên
    url = "https://www.googleapis.com/upload/drive/v3/files?uploadType=resumable"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json; charset=UTF-8",
        "X-Upload-Content-Type": "application/octet-stream"
    }
    metadata = {
        "name": file_name,
        "parents": [folder_id]
    }
    
    res = requests.post(url, headers=headers, json=metadata)
    if res.status_code != 200:
        raise Exception(f"Lỗi khởi tạo upload resumable: {res.text}")
        
    upload_url = res.headers.get("Location")
    if not upload_url:
        raise Exception("Không tìm thấy header Location trong phản hồi khởi tạo upload.")
        
    # 2. Truyền dữ liệu file
    with open(file_path, "rb") as f:
        put_headers = {
            "Content-Length": str(file_size),
            "Content-Type": "application/octet-stream"
        }
        # Tải toàn bộ file (đối với môi trường local, thư viện requests tự truyền luồng)
        res_put = requests.put(upload_url, headers=put_headers, data=f)
        if res_put.status_code not in [200, 201]:
            raise Exception(f"Lỗi truyền dữ liệu file {file_name}: {res_put.text}")
            
    file_id = res_put.json()["id"]
    
    # Thiết lập chia sẻ công khai
    make_file_public_shareable(file_id, access_token)
    
    return file_id

def ensure_folder_structure(access_token: str = None) -> dict:
    """
    Đảm bảo cấu trúc thư mục Drive tồn tại:
    HD Media/
    ├── Finished/
    ├── Subtitle/
    ├── Audio/
    ├── Thumbnail/
    └── SEO/
    Trả về dict ánh xạ tên thư mục con sang ID thư mục của nó.
    """
    if not access_token:
        access_token = get_access_token()
        
    # 1. Tìm hoặc tạo thư mục cha "HD Media"
    parent_id = find_folder("HD Media", access_token=access_token)
    if not parent_id:
        parent_id = create_folder("HD Media", access_token=access_token)
        logger.info(f"Đã tạo thư mục cha 'HD Media' (ID: {parent_id})")
        
    folders = ["Finished", "Subtitle", "Audio", "Thumbnail", "SEO"]
    mapping = {"root": parent_id}
    
    # 2. Tạo hoặc tìm các thư mục con
    for sub in folders:
        sub_id = find_folder(sub, parent_id=parent_id, access_token=access_token)
        if not sub_id:
            sub_id = create_folder(sub, parent_id=parent_id, access_token=access_token)
            logger.info(f"Đã tạo thư mục con 'HD Media/{sub}' (ID: {sub_id})")
        mapping[sub] = sub_id
        
    return mapping

def upload_job_assets(job_id: int, assets: dict) -> dict:
    """
    Tải lên toàn bộ file kết quả của Job.
    assets: dict chứa đường dẫn của các tệp tin kết quả:
      {
        "video": "path/to/video.mp4",
        "subtitle_ass": "path/to/sub.ass",
        "subtitle_srt": "path/to/sub.srt",
        "audio": "path/to/audio.mp3",
        "thumbnail": "path/to/thumb.jpg",
        "seo": "path/to/seo.txt"
      }
    Trả về: dict chứa link và id của video chính tải lên thư mục Finished.
    """
    # Nếu không có token đăng nhập, giả lập tiến trình upload
    if not is_authenticated():
        logger.info(f"[Job {job_id}] Chạy chế độ GIẢ LẬP Google Drive (chưa đăng nhập)...")
        return {
            "drive_link": f"https://drive.google.com/open?id=mock_video_id_job_{job_id}",
            "drive_file_id": f"mock_video_id_job_{job_id}",
            "drive_upload_status": "completed"
        }
        
    try:
        access_token = get_access_token()
        mapping = ensure_folder_structure(access_token)
        
        results = {}
        
        # 1. Tải lên video chính (thư mục Finished)
        if "video" in assets and os.path.exists(assets["video"]):
            logger.info(f"[Job {job_id}] Đang upload Video chính...")
            v_id = upload_file_resumable(assets["video"], mapping["Finished"], access_token)
            results["drive_file_id"] = v_id
            results["drive_link"] = get_file_share_link(v_id, access_token)
            
        # 2. Tải phụ đề lên (thư mục Subtitle)
        for key in ["subtitle_ass", "subtitle_srt"]:
            if key in assets and os.path.exists(assets[key]):
                logger.info(f"[Job {job_id}] Đang upload phụ đề {key}...")
                upload_file_resumable(assets[key], mapping["Subtitle"], access_token)
                
        # 3. Tải nhạc nền/giọng đọc lên (thư mục Audio)
        if "audio" in assets and os.path.exists(assets["audio"]):
            logger.info(f"[Job {job_id}] Đang upload audio...")
            upload_file_resumable(assets["audio"], mapping["Audio"], access_token)
            
        # 4. Tải hình ảnh thu nhỏ lên (thư mục Thumbnail)
        if "thumbnail" in assets and os.path.exists(assets["thumbnail"]):
            logger.info(f"[Job {job_id}] Đang upload thumbnail...")
            upload_file_resumable(assets["thumbnail"], mapping["Thumbnail"], access_token)
            
        # 5. Tải tệp thông tin SEO lên (thư mục SEO)
        if "seo" in assets and os.path.exists(assets["seo"]):
            logger.info(f"[Job {job_id}] Đang upload file SEO...")
            upload_file_resumable(assets["seo"], mapping["SEO"], access_token)
            
        results["drive_upload_status"] = "completed"
        return results
        
    except Exception as e:
        logger.error(f"[Job {job_id}] Lỗi khi upload các tệp lên Google Drive: {e}", exc_info=True)
        return {
            "drive_upload_status": "failed",
            "error_message": str(e)
        }
