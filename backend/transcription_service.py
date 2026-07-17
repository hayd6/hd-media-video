import os
import logging
import json
import gemini_service

logger = logging.getLogger("transcription_service")

try:
    from faster_whisper import WhisperModel
    HAS_FASTER_WHISPER = True
except ImportError:
    HAS_FASTER_WHISPER = False
    logger.warning("Không thể import faster-whisper. Quá trình nhận dạng giọng nói sẽ fallback sang Gemini API.")

# Initialize model lazily
_whisper_model = None

def get_whisper_model():
    global _whisper_model
    if _whisper_model is None and HAS_FASTER_WHISPER:
        logger.info("Đang tải Faster-Whisper model (base)...")
        try:
            _whisper_model = WhisperModel("base", device="cuda", compute_type="float16")
            logger.info("Đã tải Faster-Whisper trên GPU (CUDA).")
        except Exception as e:
            logger.warning(f"Không thể tải trên GPU, chuyển sang CPU: {e}")
            _whisper_model = WhisperModel("base", device="cpu", compute_type="int8")
            logger.info("Đã tải Faster-Whisper trên CPU.")
    return _whisper_model

def transcribe_audio(audio_path: str, gemini_key: str = None) -> list:
    """
    Sử dụng Faster-Whisper để nhận dạng giọng nói.
    Nếu không cài được Faster-Whisper, tự động fallback sang Gemini.
    """
    if not HAS_FASTER_WHISPER:
        logger.warning("Sử dụng Gemini API làm fallback cho Speech-to-Text do Faster-Whisper không khả dụng.")
        # Cần gọi lại hàm transcribe_audio cũ của gemini_service
        # (Lưu ý: bạn cần đảm bảo hàm này vẫn tồn tại trong gemini_service.py)
        if not hasattr(gemini_service, 'transcribe_audio'):
            raise Exception("Cả Faster-Whisper và Gemini Fallback đều không khả dụng.")
        return gemini_service.transcribe_audio(audio_path, gemini_key)

    logger.info(f"Đang chuẩn bị nhận dạng giọng nói với Faster-Whisper từ: {audio_path}")
    
    model = get_whisper_model()
    
    segments_gen, info = model.transcribe(audio_path, beam_size=5)
    
    logger.info(f"Phát hiện ngôn ngữ gốc: {info.language} với độ tin cậy {info.language_probability:.2f}")
    
    segments = []
    for segment in segments_gen:
        segments.append({
            "start": segment.start,
            "end": segment.end,
            "text": segment.text.strip()
        })
        
    return segments
