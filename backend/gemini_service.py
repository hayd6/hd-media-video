import os
import re
import time
import base64
import json
import logging
import subprocess
import requests
from config import FFMPEG_PATH, GEMINI_MODEL

logger = logging.getLogger("gemini_service")


def _get_api_keys() -> list:
    """
    Đọc danh sách Gemini API Key từ biến môi trường.
    Hỗ trợ nhiều key theo thứ tự: GEMINI_API_KEY_1, GEMINI_API_KEY_2, ...
    Sau đó fallback về GEMINI_API_KEY (key duy nhất) nếu không có key số.
    """
    keys = []
    for i in range(1, 10):
        key = os.environ.get(f"GEMINI_API_KEY_{i}")
        if key:
            keys.append(key.strip())
    if not keys:
        single = os.environ.get("GEMINI_API_KEY")
        if single:
            keys.append(single.strip())
    return keys


def _parse_retry_delay(response_text: str) -> float:
    """
    Phân tích `retryDelay` từ phản hồi lỗi 429 của Google để biết chính xác
    cần chờ bao nhiêu giây trước khi thử lại.
    """
    try:
        data = json.loads(response_text)
        details = data.get("error", {}).get("details", [])
        for detail in details:
            if detail.get("@type") == "type.googleapis.com/google.rpc.RetryInfo":
                delay_str = detail.get("retryDelay", "0s")
                # Định dạng có thể là "35s" hoặc "35.5s"
                match = re.search(r"([\d.]+)s", delay_str)
                if match:
                    return float(match.group(1)) + 2  # Cộng thêm 2s buffer
    except Exception:
        pass
    return 10.0  # Mặc định chờ 10 giây


def _is_quota_exhausted(response_text: str) -> bool:
    """
    Kiểm tra xem lỗi 429 có phải do quota NGÀY đã hết hoàn toàn không.
    
    Phân biệt 2 loại giới hạn:
    - Giới hạn phút (RPM): retryDelay thường < 60 giây → CHỜ và thử lại cùng key
    - Hết quota ngày (RPD): retryDelay rất dài (> 60 giây) → CHUYỂN sang key khác
    """
    if 'GenerateRequestsPerDayPerProjectPerModel' not in response_text and '"quotaValue": "0"' not in response_text:
        return False
    # Chỉ coi là hết quota ngày nếu thời gian chờ đề nghị >= 60 giây
    delay = _parse_retry_delay(response_text)
    return delay >= 62  # 60s + 2s buffer chúng ta đã cộng thêm = 62


def _extract_gemini_error(response_text: str) -> tuple:
    """Lay ma loi va thong diep loi tu response JSON cua Gemini."""
    try:
        error = json.loads(response_text).get("error", {})
        return error.get("status", ""), error.get("message", "")
    except Exception:
        return "", response_text


def _is_api_key_error(response_text: str) -> bool:
    """Nhan dien cac loi thuoc ve API key de co the thu key tiep theo."""
    status, message = _extract_gemini_error(response_text)
    text = f"{status} {message}".lower()
    markers = [
        "api_key_invalid",
        "api key not valid",
        "invalid api key",
        "permission_denied",
        "consumer suspended",
        "api has not been used",
        "api has not been enabled",
        "the caller does not have permission",
    ]
    return any(marker in text for marker in markers)


def _is_model_error(response_text: str) -> bool:
    """Nhan dien loi model khong ton tai/khong kha dung."""
    status, message = _extract_gemini_error(response_text)
    text = f"{status} {message}".lower()
    return (
        "not_found" in text
        or "is no longer available" in text
        or ("model" in text and "not found" in text)
    )


def gemini_post_request_with_key_rotation(build_url_fn, headers: dict, json_payload: dict, max_retries: int = 5, timeout: int = 60) -> requests.Response:
    """
    Gọi Gemini API với cơ chế xoay vòng API Key (Key Rotation).
    - Khi một key bị hết quota ngày (retryDelay >= 60s): CHUYỂN sang key tiếp theo ngay
    - Khi một key bị giới hạn phút (retryDelay < 60s): CHỜ rồi thử lại
    - Khi một key bị lỗi kết nối (ConnectionError): CHUYỂN sang key tiếp theo
    `build_url_fn` là một hàm nhận vào api_key và trả về URL hoàn chỉnh.
    """
    keys = _get_api_keys()
    if not keys:
        raise Exception("Không tìm thấy GEMINI_API_KEY trong môi trường. Vui lòng kiểm tra tệp .env.")

    last_response = None
    last_err = None

    for key_index, api_key in enumerate(keys):
        logger.info(f"Đang sử dụng Gemini API Key #{key_index + 1}/{len(keys)}...")
        url = build_url_fn(api_key)
        key_should_switch = False

        for attempt in range(1, max_retries + 1):
            try:
                logger.info(f"  Lần gọi {attempt}/{max_retries} (timeout={timeout}s)...")
                response = requests.post(url, headers=headers, json=json_payload, timeout=timeout)
                last_response = response

                if response.status_code == 429:
                    if _is_quota_exhausted(response.text):
                        # Hết quota ngày → chuyển key ngay
                        logger.warning(f"  Key #{key_index + 1} đã hết quota ngày. Chuyển sang key tiếp theo...")
                        key_should_switch = True
                        break
                    else:
                        # Giới hạn phút → chờ đúng thời gian Google đề nghị rồi thử lại
                        wait_sec = _parse_retry_delay(response.text)
                        logger.warning(f"  Lỗi 429 (giới hạn phút). Chờ {wait_sec:.0f}s rồi thử lại với key #{key_index + 1}...")
                        time.sleep(wait_sec)
                        continue

                if response.status_code in [400, 401, 403] and _is_api_key_error(response.text):
                    logger.warning(f"  Key #{key_index + 1} khong hop le/khong co quyen. Chuyen sang key tiep theo...")
                    key_should_switch = True
                    break

                if response.status_code == 404 and _is_model_error(response.text):
                    _, message = _extract_gemini_error(response.text)
                    raise Exception(
                        f"Gemini model '{GEMINI_MODEL}' khong kha dung: {message}\n"
                        "Hay doi GEMINI_MODEL trong .env sang model con ho tro, vi du: gemini-2.0-flash"
                    )

                if response.status_code in [500, 502, 503, 504]:
                    logger.warning(f"  Lỗi máy chủ tạm thời {response.status_code}. Chờ rồi thử lại...")
                    time.sleep(5 * attempt)
                    continue

                return response  # Thành công!

            except requests.exceptions.Timeout as e:
                # Timeout → thử lại với cùng key
                logger.warning(f"  Timeout (Lần {attempt}/{max_retries}). Thử lại...")
                last_err = e
                time.sleep(3)

            except requests.exceptions.ConnectionError as e:
                # Lỗi kết nối (connection reset, refused) → chuyển sang key tiếp theo
                logger.warning(f"  Lỗi kết nối với key #{key_index + 1}: {e}. Chuyển sang key tiếp theo...")
                last_err = e
                key_should_switch = True
                break

        if key_should_switch:
            continue  # Thử key tiếp theo

        # Tất cả lần thử với key này đều thất bại (không phải quota ngày)
        if last_err:
            raise last_err
        if last_response:
            raise Exception(f"Gemini API Error (status {last_response.status_code}): {last_response.text}")


    # Tất cả key đều hết quota
    key_count = len(keys)
    status_info = f" (Mã HTTP {last_response.status_code}: {last_response.text})" if last_response else ""
    if last_response and _is_api_key_error(last_response.text):
        raise Exception(
            f"Tất cả {key_count} Gemini API Key đều không hợp lệ hoặc không có quyền gọi API.{status_info}\n\n"
            "Hãy kiểm tra lại key trong .env. Gemini API key thường được tạo tại: https://aistudio.google.com/apikey"
        )
    if key_count == 1:
        raise Exception(
            f"Không thể kết nối tới Gemini API sau nhiều lần thử lại.{status_info}\n\n"
            "💡 API Key của bạn đã hết quota miễn phí cho hôm nay.\n"
            "Hãy tạo thêm API key tại: https://aistudio.google.com/apikey\n"
            "Sau đó thêm vào .env: GEMINI_API_KEY_2=<key mới>"
        )
    raise Exception(
        f"Tất cả {key_count} API Key đều đã hết quota miễn phí cho hôm nay!{status_info}\n\n"
        "💡 Tạo thêm API key tại: https://aistudio.google.com/apikey và thêm GEMINI_API_KEY_3=..."
    )


def gemini_post_request(url: str, headers: dict, json_payload: dict, max_retries: int = 3, timeout: int = 120) -> requests.Response:
    """
    Gọi Gemini API với cơ chế Retry + chờ đúng thời gian Google gợi ý (retryDelay).
    Wrapper cũ được giữ lại để tương thích, nhưng nội bộ sẽ tự xử lý retry thông minh.
    """
    last_err = None
    last_response = None
    for attempt in range(1, max_retries + 1):
        try:
            logger.info(f"Đang gọi Gemini API (Lần {attempt}/{max_retries}, timeout={timeout}s)...")
            response = requests.post(url, headers=headers, json=json_payload, timeout=timeout)
            last_response = response

            if response.status_code == 429:
                wait_sec = _parse_retry_delay(response.text)
                logger.warning(f"Gemini API trả về 429. Chờ {wait_sec:.0f} giây rồi thử lại...")
                time.sleep(wait_sec)
                continue

            if response.status_code in [500, 502, 503, 504]:
                logger.warning(f"Gemini API trả về lỗi tạm thời {response.status_code}. Đang chờ để thử lại...")
                time.sleep(5 * attempt)
                continue

            return response
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
            logger.warning(f"Lỗi Timeout hoặc Kết nối khi gọi Gemini API (Lần {attempt}): {e}")
            last_err = e
            time.sleep(3 * attempt)

    if last_err:
        raise last_err

    status_info = f" (Mã HTTP {last_response.status_code}: {last_response.text})" if last_response else ""
    raise Exception(f"Không thể kết nối tới Gemini API sau nhiều lần thử lại.{status_info}")

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

    def build_url(key):
        return f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={key}"

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

    response = gemini_post_request_with_key_rotation(build_url, headers=headers, json_payload=payload)
    if response.status_code != 200:
        raise Exception(f"Gemini API Error (status {response.status_code}): {response.text}")

    res_data = response.json()
    try:
        text_response = res_data["candidates"][0]["content"]["parts"][0]["text"]
        segments = json.loads(text_response)
        return segments
    except (KeyError, IndexError, json.JSONDecodeError) as e:
        raise Exception(f"Lỗi phân tích phản hồi từ Gemini: {e}. Raw: {response.text}")

def translate_segments(segments: list, target_lang: str, api_key: str, model_name: str) -> list:
    """
    Dịch danh sách các phân đoạn hội thoại sang ngôn ngữ đích sử dụng Gemini API.
    Giữ nguyên các mốc thời gian start/end.
    """
    if not segments:
        return []

    def build_url(key):
        return f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={key}"

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
                        "start": {"type": "NUMBER"},
                        "end": {"type": "NUMBER"},
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

    response = gemini_post_request_with_key_rotation(build_url, headers=headers, json_payload=payload)
    if response.status_code != 200:
        raise Exception(f"Gemini Translation API Error (status {response.status_code}): {response.text}")

    res_data = response.json()
    try:
        text_response = res_data["candidates"][0]["content"]["parts"][0]["text"]
        translated_segments = json.loads(text_response)
        return translated_segments
    except (KeyError, IndexError, json.JSONDecodeError) as e:
        raise Exception(f"Lỗi phân tích phản hồi dịch từ Gemini: {e}. Raw: {response.text}")

def generate_seo(transcript_text: str, target_lang: str, api_key: str, model_name: str) -> dict:
    """
    Sinh nội dung SEO (Tiêu đề, mô tả tóm tắt, thẻ hashtags) dựa vào nội dung hội thoại của video.
    """
    def build_url(key):
        return f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={key}"

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
    response = gemini_post_request_with_key_rotation(build_url, headers=headers, json_payload=payload)

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
