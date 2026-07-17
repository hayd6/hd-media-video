import json
import logging
import requests
from config import OLLAMA_HOST

logger = logging.getLogger("ollama_service")

def get_api_url():
    return f"{OLLAMA_HOST.rstrip('/')}/api/generate"

def get_tags_url():
    return f"{OLLAMA_HOST.rstrip('/')}/api/tags"

def get_models() -> list:
    """
    Lấy danh sách các model đang có trong Ollama local.
    """
    try:
        response = requests.get(get_tags_url(), timeout=5)
        response.raise_for_status()
        data = response.json()
        models = [m.get("name") for m in data.get("models", [])]
        return models
    except Exception as e:
        logger.error(f"Lỗi khi lấy danh sách model từ Ollama: {e}")
        return []

def translate_segments(segments: list, target_lang: str, model_name: str) -> list:
    """
    Dịch danh sách các phân đoạn hội thoại sang ngôn ngữ đích sử dụng Ollama Local.
    Giữ nguyên các mốc thời gian start/end.
    """
    if not segments:
        return []

    prompt = (
        f"Hãy đóng vai trò là một biên dịch viên phụ đề chuyên nghiệp.\n"
        f"Dịch nội dung văn bản (trường 'text') trong danh sách JSON các phân đoạn hội thoại sau sang ngôn ngữ: {target_lang}.\n"
        f"Yêu cầu:\n"
        f"1. Dịch trôi chảy, tự nhiên, văn phong phù hợp với ngữ cảnh.\n"
        f"2. Giữ nguyên chính xác mốc thời gian 'start' và 'end' của từng phân đoạn.\n"
        f"3. Chỉ trả về một mảng JSON (Array) hợp lệ chứa các object có 'start', 'end', 'text', không kèm theo bất kỳ văn bản giải thích nào khác.\n\n"
        f"Dữ liệu JSON:\n{json.dumps(segments, ensure_ascii=False)}"
    )

    payload = {
        "model": model_name,
        "prompt": prompt,
        "format": "json",
        "stream": False,
        "options": {
            "temperature": 0.3
        }
    }

    headers = {"Content-Type": "application/json"}

    logger.info(f"Đang gọi Ollama ({model_name}) để dịch thuật...")
    
    try:
        response = requests.post(get_api_url(), headers=headers, json=payload, timeout=300)
        response.raise_for_status()
    except Exception as e:
        logger.error(f"Lỗi khi kết nối với Ollama: {e}")
        raise Exception(f"Không thể kết nối với Ollama tại {get_api_url()}. Hãy chắc chắn Ollama đang chạy và đã tải model {model_name}. Chi tiết lỗi: {str(e)}")

    res_data = response.json()
    try:
        text_response = res_data.get("response", "").strip()
        translated_segments = json.loads(text_response)
        
        if isinstance(translated_segments, dict):
            for key, value in translated_segments.items():
                if isinstance(value, list):
                    translated_segments = value
                    break
                    
        if not isinstance(translated_segments, list):
            raise Exception("Phản hồi không phải là danh sách (Array).")
            
        return translated_segments
        
    except json.JSONDecodeError as e:
        logger.error(f"Lỗi phân tích phản hồi JSON từ Ollama. Raw: {text_response}")
        raise Exception(f"Lỗi định dạng JSON từ Ollama Local: {e}")

def generate_seo(transcript_text: str, target_lang: str, model_name: str) -> dict:
    """
    Sinh nội dung SEO sử dụng Ollama.
    """
    prompt = (
        f"Dựa vào nội dung cuộc hội thoại trong video sau đây, hãy viết tiêu đề SEO cuốn hút, "
        f"mô tả tóm tắt nội dung hấp dẫn kèm các từ khóa hashtags (tags) phù hợp để đăng YouTube/TikTok. "
        f"Ngôn ngữ viết: {target_lang}.\n\n"
        f"Nội dung hội thoại:\n\"{transcript_text}\"\n\n"
        f"Yêu cầu: CHỈ TRẢ VỀ JSON HỢP LỆ với cấu trúc: {{\"title\": \"...\", \"description\": \"...\", \"tags\": \"...\"}} "
        f"Không giải thích gì thêm."
    )

    payload = {
        "model": model_name,
        "prompt": prompt,
        "format": "json",
        "stream": False,
        "options": {
            "temperature": 0.7
        }
    }

    headers = {"Content-Type": "application/json"}

    logger.info(f"Đang gọi Ollama ({model_name}) để sinh SEO...")
    
    try:
        response = requests.post(get_api_url(), headers=headers, json=payload, timeout=120)
        response.raise_for_status()
    except Exception as e:
        logger.error(f"Lỗi khi gọi Ollama sinh SEO: {e}")
        raise Exception(f"Lỗi khi gọi Ollama: {str(e)}")

    res_data = response.json()
    try:
        text_response = res_data.get("response", "").strip()
        seo_data = json.loads(text_response)
        return seo_data
    except Exception as e:
        logger.error(f"Lỗi phân tích phản hồi SEO từ Ollama: {e}. Raw: {res_data.get('response')}")
        raise Exception(f"Lỗi JSON từ Ollama: {e}")
