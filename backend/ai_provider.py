import logging
import config
import ollama_service
import gemini_service

logger = logging.getLogger("ai_provider")

# Global variables keeping current state if needed
# Although requests will mostly use what is passed by the job
CURRENT_PROVIDER = config.AI_PROVIDER
CURRENT_OLLAMA_MODEL = config.OLLAMA_MODEL
CURRENT_GEMINI_MODEL = config.GEMINI_MODEL
OLLAMA_STATUS = "Offline"

def check_ollama_status():
    global OLLAMA_STATUS
    models = ollama_service.get_models()
    if models:
        OLLAMA_STATUS = "Ready"
        logger.info(f"Ollama is Ready. Available models: {models}")
    else:
        OLLAMA_STATUS = "Offline"
        logger.info("Ollama is Offline or no models installed.")
    return OLLAMA_STATUS

def get_status():
    return {
        "provider": CURRENT_PROVIDER,
        "ollama_status": OLLAMA_STATUS,
        "current_ollama_model": CURRENT_OLLAMA_MODEL,
        "current_gemini_model": CURRENT_GEMINI_MODEL
    }

def update_settings(provider: str = None, ollama_model: str = None, gemini_model: str = None):
    global CURRENT_PROVIDER, CURRENT_OLLAMA_MODEL, CURRENT_GEMINI_MODEL
    if provider:
        CURRENT_PROVIDER = provider.lower()
    if ollama_model:
        CURRENT_OLLAMA_MODEL = ollama_model
    if gemini_model:
        CURRENT_GEMINI_MODEL = gemini_model
    logger.info(f"Updated AI settings: Provider={CURRENT_PROVIDER}, OllamaModel={CURRENT_OLLAMA_MODEL}, GeminiModel={CURRENT_GEMINI_MODEL}")

def get_supported_providers():
    return ["ollama", "gemini"]

def get_models(provider: str):
    if provider.lower() == "ollama":
        if OLLAMA_STATUS == "Offline":
            # Thử kết nối lại
            check_ollama_status()
        return ollama_service.get_models()
    elif provider.lower() == "gemini":
        return ["gemini-2.0-flash", "gemini-2.0-pro-exp"]
    return []

def translate(segments: list, target_lang: str, provider: str = None, model: str = None, api_key: str = None) -> list:
    use_provider = (provider or CURRENT_PROVIDER).lower()
    
    if use_provider == "ollama":
        use_model = model or CURRENT_OLLAMA_MODEL
        logger.info(f"Translating using Ollama ({use_model})...")
        return ollama_service.translate_segments(segments, target_lang, use_model)
        
    elif use_provider == "gemini":
        use_model = model or CURRENT_GEMINI_MODEL
        if not api_key:
            pass
        logger.info(f"Translating using Gemini ({use_model})...")
        return gemini_service.translate_segments(segments, target_lang, api_key, use_model)
        
    else:
        raise ValueError(f"Provider {use_provider} is not supported.")

def seo(transcript_text: str, target_lang: str, provider: str = None, model: str = None, api_key: str = None) -> dict:
    use_provider = (provider or CURRENT_PROVIDER).lower()
    
    if use_provider == "ollama":
        use_model = model or CURRENT_OLLAMA_MODEL
        logger.info(f"Generating SEO using Ollama ({use_model})...")
        return ollama_service.generate_seo(transcript_text, target_lang, use_model)
        
    elif use_provider == "gemini":
        use_model = model or CURRENT_GEMINI_MODEL
        logger.info(f"Generating SEO using Gemini ({use_model})...")
        return gemini_service.generate_seo(transcript_text, target_lang, api_key, use_model)
        
    else:
        raise ValueError(f"Provider {use_provider} is not supported.")
