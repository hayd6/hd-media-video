import json
import logging
import requests

logger = logging.getLogger("qwen_service")

# URL API của Ollama mặc định
OLLAMA_API_URL = "http://127.0.0.1:11434/api/generate"

def translate_segments(segments: list, target_lang: str) -> list:
    """
    Dịch danh sách các phân đoạn hội thoại sang ngôn ngữ đích sử dụng Qwen Local (Ollama).
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
        "model": "qwen2.5",
        "prompt": prompt,
        "format": "json",
        "stream": False,
        "options": {
            "temperature": 0.3
        }
    }

    headers = {"Content-Type": "application/json"}

    logger.info("Đang gọi Ollama Qwen Local để dịch thuật...")
    
    try:
        response = requests.post(OLLAMA_API_URL, headers=headers, json=payload, timeout=300)
        response.raise_for_status()
    except Exception as e:
        logger.error(f"Lỗi khi kết nối với Ollama Qwen: {e}")
        raise Exception(f"Không thể kết nối với Ollama tại {OLLAMA_API_URL}. Hãy chắc chắn Ollama đang chạy và đã tải model qwen2.5 bằng lệnh 'ollama run qwen2.5'. Chi tiết lỗi: {str(e)}")

    res_data = response.json()
    try:
        text_response = res_data.get("response", "").strip()
        # Đảm bảo phân tích đúng JSON
        translated_segments = json.loads(text_response)
        
        # Xử lý trường hợp Ollama bọc mảng trong một object JSON thay vì mảng trực tiếp
        if isinstance(translated_segments, dict):
            for key, value in translated_segments.items():
                if isinstance(value, list):
                    translated_segments = value
                    break
                    
        if not isinstance(translated_segments, list):
            raise Exception("Phản hồi không phải là danh sách (Array).")
            
        return translated_segments
        
    except json.JSONDecodeError as e:
        logger.error(f"Lỗi phân tích phản hồi JSON từ Qwen. Raw: {text_response}")
        raise Exception(f"Lỗi định dạng JSON từ Qwen Local: {e}")
