import logging
import ai_provider

logger = logging.getLogger("seo_service")

def generate_seo(transcript_text: str, target_lang: str, provider: str = None, model: str = None, api_key: str = None) -> dict:
    """
    Sinh nội dung SEO (Tiêu đề, mô tả, hashtag) bằng cách gọi AI Provider Manager.
    Tách biệt logic SEO khỏi các phần khác để dễ dàng nâng cấp (VD: gọi Summary, Title, ... riêng biệt).
    """
    logger.info("Bắt đầu sinh nội dung SEO...")
    try:
        seo_data = ai_provider.seo(
            transcript_text=transcript_text,
            target_lang=target_lang,
            provider=provider,
            model=model,
            api_key=api_key
        )
        logger.info("Sinh nội dung SEO thành công.")
        return seo_data
    except Exception as e:
        logger.error(f"Lỗi khi sinh SEO qua AI Provider: {e}")
        raise
