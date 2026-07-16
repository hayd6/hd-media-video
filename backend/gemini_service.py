import os
import time
import base64
import json
import logging
import subprocess
import requests
from config import FFMPEG_PATH, GEMINI_MODEL

logger = logging.getLogger("gemini_service")

def gemini_post_request(url: str, headers: dict, json_payload: dict, max_retries: int = 3, timeout: int = 120) -> requests.Response:
    """
    Thực hiện gửi yêu cầu POST đến Gemini API với cơ chế tự động thử lại (Retry) và Timeout lớn
    để phòng tránh các lỗi nghẽn mạng hoặc xử lý quá hạn từ phía máy chủ Google.
    """
    last_err = None
    for attempt in range(1, max_retries + 1):
        try:
            logger.info(f"Đang gọi Gemini API (Lần {attempt}/{max_retries}, timeout={timeout}s)...")
            response = requests.post(url, headers=headers, json=json_payload, timeout=timeout)
            
            # Tự động thử lại nếu gặp lỗi nghẽn/hạn chế (429) hoặc lỗi máy chủ tạm thời (5xx)
            if response.status_code in [429, 500, 502, 503, 504]:
                logger.warning(f"Gemini API trả về lỗi tạm thời {response.status_code}. Đang chờ để thử lại...")
                time.sleep(2 * attempt)
                continue
                
            return response
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
            logger.warning(f"Lỗi Timeout hoặc Kết nối khi gọi Gemini API (Lần {attempt}): {e}")
            last_err = e
            time.sleep(3 * attempt)
            
    if last_err:
        raise last_err
    raise Exception("Không thể kết nối tới Gemini API sau nhiều lần thử lại.")

def compress_audio_to_mp3(wav_path: str) -> str:
    """
    Nén file âm thanh WAV thành MP3 (64kbps, Mono) để giảm kích thước payload khi gửi tới Gemini API.
    Nếu thất bại, thử nén sang AAC. Nếu vẫn thất bại, trả về file WAV gốc.
    """
    mp3_path = wav_path.replace(".wav", ".mp3")
    command = [
        FFMPEG_PATH,
        "-y",
        "-i", wav_path,
        "-codec:a", "libmp3lame",
        "-b:a", "64k",
        "-ac", "1",
        mp3_path
    ]
    try:
        process = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        )
        if process.returncode == 0 and os.path.exists(mp3_path):
            logger.info(f"Đã nén âm thanh thành công sang MP3: {mp3_path}")
            return mp3_path
    except Exception as e:
        logger.warning(f"Lỗi khi nén sang MP3 (thử fallback sang AAC): {e}")

    # Fallback sang AAC (luôn có sẵn trong FFmpeg)
    aac_path = wav_path.replace(".wav", ".aac")
    command_aac = [
        FFMPEG_PATH,
        "-y",
        "-i", wav_path,
        "-codec:a", "aac",
        "-b:a", "64k",
        "-ac", "1",
        aac_path
    ]
    try:
        process = subprocess.run(
            command_aac,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        )
        if process.returncode == 0 and os.path.exists(aac_path):
            logger.info(f"Đã nén âm thanh thành công sang AAC: {aac_path}")
            return aac_path
    except Exception as e:
        logger.error(f"Lỗi khi nén sang AAC: {e}")

    return wav_path

def transcribe_audio(audio_path: str, api_key: str) -> list:
    """
    Sử dụng Gemini 2.5 Flash để nhận dạng giọng nói từ file âm thanh (Speech-to-Text).
    Trả về danh sách các phân đoạn hội thoại kèm thời gian start/end.
    """
    compressed_path = compress_audio_to_mp3(audio_path)
    
    if compressed_path.endswith(".mp3"):
        mime_type = "audio/mp3"
    elif compressed_path.endswith(".aac"):
        mime_type = "audio/aac"
    else:
        mime_type = "audio/wav"

    logger.info(f"Đang chuẩn bị gửi file âm thanh ({mime_type}) lên Gemini...")
    
    with open(compressed_path, "rb") as f:
        audio_data = base64.b64encode(f.read()).decode("utf-8")
        
    if compressed_path != audio_path and os.path.exists(compressed_path):
        try:
            os.remove(compressed_path)
        except Exception:
            pass

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={api_key}"
    
    prompt = (
        "Lắng nghe kỹ file âm thanh này và nhận diện giọng nói (Speech-to-Text). "
        "Hãy trích xuất chính xác nội dung hội thoại thành danh sách các phân đoạn (segments) "
        "kèm mốc thời gian bằng chính NGÔN NGỮ GỐC được nói trong âm thanh. "
        "Chia nhỏ các phân đoạn hợp lý (mỗi phân đoạn tối đa 2 đến 7 giây, khớp với nhịp điệu của người nói)."
    )
    
    payload = {
        "contents": [
            {
                "parts": [
                    {"text": prompt},
                    {
                        "inlineData": {
                            "mimeType": mime_type,
                            "data": audio_data
                        }
                    }
                ]
            }
        ],
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": {
                "type": "ARRAY",
                "items": {
                    "type": "OBJECT",
                    "properties": {
                        "start": {
                            "type": "NUMBER",
                            "description": "Thời gian bắt đầu phân đoạn (giây, ví dụ 1.5)"
                        },
                        "end": {
                            "type": "NUMBER",
                            "description": "Thời gian kết thúc phân đoạn (giây, ví dụ 4.2)"
                        },
                        "text": {
                            "type": "STRING",
                            "description": "Nội dung lời thoại gốc được nói trong phân đoạn này"
                        }
                    },
                    "required": ["start", "end", "text"]
                }
            }
        }
    }
    
    headers = {"Content-Type": "application/json"}
    
    response = gemini_post_request(url, headers=headers, json_payload=payload)
    if response.status_code != 200:
        raise Exception(f"Gemini API Error (status {response.status_code}): {response.text}")
        
    res_data = response.json()
    try:
        text_response = res_data["candidates"][0]["content"]["parts"][0]["text"]
        segments = json.loads(text_response)
        return segments
    except (KeyError, IndexError, json.JSONDecodeError) as e:
        raise Exception(f"Lỗi phân tích phản hồi từ Gemini: {e}. Raw: {response.text}")

def translate_segments(segments: list, target_lang: str, api_key: str) -> list:
    """
    Dịch danh sách các phân đoạn hội thoại sang ngôn ngữ đích sử dụng Gemini 2.5 Flash.
    Giữ nguyên các mốc thời gian start/end.
    """
    if not segments:
        return []
        
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={api_key}"
    
    prompt = (
        f"Hãy đóng vai trò là một biên dịch viên phụ đề chuyên nghiệp. "
        f"Dịch nội dung văn bản (trường 'text') trong danh sách các phân đoạn hội thoại sau sang ngôn ngữ: {target_lang}. "
        f"Yêu cầu: Dịch trôi chảy, tự nhiên, văn phong phù hợp với ngữ cảnh video, tránh dịch từng từ máy móc. "
        f"Giữ nguyên chính xác mốc thời gian 'start' và 'end' của từng phân đoạn."
    )
    
    payload = {
        "contents": [
            {
                "parts": [
                    {"text": prompt},
                    {"text": json.dumps(segments, ensure_ascii=False)}
                ]
            }
        ],
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": {
                "type": "ARRAY",
                "items": {
                    "type": "OBJECT",
                    "properties": {
                        "start": {
                            "type": "NUMBER"
                        },
                        "end": {
                            "type": "NUMBER"
                        },
                        "text": {
                            "type": "STRING",
                            "description": "Nội dung lời thoại đã được dịch sang ngôn ngữ đích"
                        }
                    },
                    "required": ["start", "end", "text"]
                }
            }
        }
    }
    
    headers = {"Content-Type": "application/json"}
    
    response = gemini_post_request(url, headers=headers, json_payload=payload)
    if response.status_code != 200:
        raise Exception(f"Gemini Translation API Error (status {response.status_code}): {response.text}")
        
    res_data = response.json()
    try:
        text_response = res_data["candidates"][0]["content"]["parts"][0]["text"]
        translated_segments = json.loads(text_response)
        return translated_segments
    except (KeyError, IndexError, json.JSONDecodeError) as e:
        raise Exception(f"Lỗi phân tích phản hồi dịch từ Gemini: {e}. Raw: {response.text}")

def generate_seo(transcript_text: str, target_lang: str, api_key: str) -> dict:
    """
    Sinh nội dung SEO (Tiêu đề, mô tả tóm tắt, thẻ hashtags) dựa vào nội dung hội thoại của video.
    """
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={api_key}"
    
    prompt = (
        f"Dựa vào nội dung cuộc hội thoại trong video sau đây, hãy viết tiêu đề SEO cuốn hút, "
        f"mô tả tóm tắt nội dung hấp dẫn kèm các từ khóa hashtags (tags) phù hợp để đăng YouTube/TikTok. "
        f"Ngôn ngữ viết: {target_lang}.\n\n"
        f"Nội dung hội thoại:\n\"{transcript_text}\""
    )
    
    payload = {
        "contents": [
            {
                "parts": [{"text": prompt}]
            }
        ],
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": {
                "type": "OBJECT",
                "properties": {
                    "title": {
                        "type": "STRING",
                        "description": "Tiêu đề video cuốn hút chuẩn SEO"
                    },
                    "description": {
                        "type": "STRING",
                        "description": "Mô tả tóm tắt video chi tiết hấp dẫn"
                    },
                    "tags": {
                        "type": "STRING",
                        "description": "Danh sách các hashtags từ khóa cách nhau bằng dấu phẩy"
                    }
                },
                "required": ["title", "description", "tags"]
            }
        }
    }
    
    headers = {"Content-Type": "application/json"}
    
    logger.info("Đang gọi Gemini API để sinh tiêu đề & SEO cho video...")
    response = gemini_post_request(url, headers=headers, json_payload=payload)
    
    if response.status_code != 200:
        raise Exception(f"Gemini SEO API Error (status {response.status_code}): {response.text}")
        
    res_data = response.json()
    try:
        text_response = res_data["candidates"][0]["content"]["parts"][0]["text"]
        seo_data = json.loads(text_response)
        logger.info("Đã sinh SEO thành công.")
        return seo_data
    except (KeyError, IndexError, json.JSONDecodeError) as e:
        raise Exception(f"Lỗi phân tích phản hồi SEO từ Gemini: {e}. Raw: {response.text}")
