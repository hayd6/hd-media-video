import os
import asyncio
import subprocess
import wave
import array
import logging
import edge_tts
from config import FFMPEG_PATH, DOWNLOAD_DIR

logger = logging.getLogger("tts_service")

# Danh sách giọng đọc mặc định
VOICES = {
    "Vietnamese": {
        "Female": "vi-VN-HoaiMyNeural",
        "Male": "vi-VN-NamMinhNeural"
    },
    "English": {
        "Female": "en-US-JennyNeural",
        "Male": "en-US-GuyNeural"
    }
}

def get_voice_name(lang: str, gender: str) -> str:
    """Lấy tên giọng đọc Edge TTS dựa trên ngôn ngữ và giới tính."""
    lang_voices = VOICES.get(lang, VOICES["Vietnamese"])
    return lang_voices.get(gender, lang_voices["Female"])

def get_audio_duration(audio_path: str) -> float:
    """
    Đo thời lượng của một file âm thanh bằng cách chạy FFmpeg.
    Trả về số giây (float).
    """
    command = [FFMPEG_PATH, "-i", audio_path]
    try:
        process = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        )
        # Parse Duration từ stderr của FFmpeg
        for line in process.stderr.splitlines():
            if "Duration:" in line:
                parts = line.split("Duration:")[1].split(",")[0].strip().split(":")
                hours = float(parts[0])
                minutes = float(parts[1])
                seconds = float(parts[2])
                return hours * 3600 + minutes * 60 + seconds
    except Exception as e:
        logger.error(f"Lỗi khi đo thời lượng file {audio_path}: {e}")
    return 0.0

def stretch_audio(input_path: str, output_path: str, speed_factor: float):
    """
    Thay đổi tốc độ của file âm thanh sử dụng bộ lọc 'atempo' của FFmpeg.
    """
    # atempo của FFmpeg hỗ trợ từ 0.5 đến 2.0. Nếu vượt quá, ta phải kết hợp nhiều bộ lọc.
    filters = []
    temp_factor = speed_factor
    while temp_factor > 2.0:
        filters.append("atempo=2.0")
        temp_factor /= 2.0
    while temp_factor < 0.5:
        filters.append("atempo=0.5")
        temp_factor /= 0.5
        
    filters.append(f"atempo={temp_factor}")
    filter_str = ",".join(filters)
    
    command = [
        FFMPEG_PATH,
        "-y",
        "-i", input_path,
        "-filter:a", filter_str,
        "-vn",
        output_path
    ]
    
    process = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    )
    if process.returncode != 0:
        err = process.stderr.decode('utf-8', errors='ignore')
        raise Exception(f"Lỗi FFmpeg stretch_audio: {err}")

async def generate_speech_for_segment(text: str, voice: str, target_duration: float, output_path: str):
    """
    Sinh file âm thanh từ văn bản sử dụng Edge TTS, sau đó co giãn tốc độ để khớp với target_duration.
    """
    temp_tts_path = output_path + ".temp.mp3"
    temp_wav_path = output_path + ".temp.wav"
    
    # 1. Gọi Edge TTS sinh file MP3
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(temp_tts_path)
    
    # 2. Chuyển sang WAV 16kHz Mono bằng FFmpeg để chuẩn hóa
    conv_cmd = [
        FFMPEG_PATH, "-y",
        "-i", temp_tts_path,
        "-acodec", "pcm_s16le",
        "-ar", "16000",
        "-ac", "1",
        temp_wav_path
    ]
    subprocess.run(conv_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    
    # Đo thời lượng thực tế của tiếng nói vừa sinh
    actual_dur = get_audio_duration(temp_wav_path)
    
    # Dọn dẹp file MP3 tạm
    if os.path.exists(temp_tts_path):
        os.remove(temp_tts_path)
        
    # 3. Tính toán co giãn tốc độ nếu giọng đọc dài hơn thời gian phân đoạn cho phép
    if actual_dur > target_duration and target_duration > 0:
        speed_factor = actual_dur / target_duration
        # Giới hạn tốc độ tối đa là 1.8x để tránh giọng đọc bị quá méo, không nghe kịp
        if speed_factor > 1.8:
            speed_factor = 1.8
        logger.info(f"Đang co giãn tốc độ giọng đọc ({speed_factor:.2f}x): {text[:20]}...")
        stretch_audio(temp_wav_path, output_path, speed_factor)
    else:
        # Nếu thời lượng phù hợp, chỉ cần đổi tên file
        if os.path.exists(output_path):
            os.remove(output_path)
        os.rename(temp_wav_path, output_path)
        
    # Dọn dẹp file WAV tạm
    if os.path.exists(temp_wav_path):
        os.remove(temp_wav_path)

def mix_audio_tracks(segments_paths: list, segments_starts: list, total_duration: float, output_path: str, sample_rate: int = 16000):
    """
    Trộn các phân đoạn âm thanh lồng tiếng riêng lẻ vào một file âm thanh tổng dài bằng video gốc.
    Phương pháp: Đọc PCM dạng 16-bit Short bằng module wave/array của Python và gộp đè tại vị trí timestamps.
    """
    num_samples = int(total_duration * sample_rate)
    master_data = array.array('h', [0] * num_samples)
    
    for path, start_time in zip(segments_paths, segments_starts):
        if not os.path.exists(path):
            continue
            
        with wave.open(path, 'rb') as w:
            params = w.getparams()
            nchannels, sampwidth, framerate, nframes = params[:4]
            data = w.readframes(nframes)
            
            seg_array = array.array('h')
            seg_array.frombytes(data)
            
            # Tính toán mẫu bắt đầu trong master track
            start_sample = int(start_time * sample_rate)
            for i in range(len(seg_array)):
                idx = start_sample + i
                if idx < len(master_data):
                    # Trộn âm thanh và clipping để chống vỡ tiếng
                    val = master_data[idx] + seg_array[i]
                    if val > 32767:
                        val = 32767
                    elif val < -32768:
                        val = -32768
                    master_data[idx] = val
                    
    # Ghi file WAV tổng hợp đầu ra
    with wave.open(output_path, 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)  # 16-bit
        w.setframerate(sample_rate)
        w.writeframes(master_data.tobytes())

async def generate_dubbed_track_async(translated_segments: list, voice: str, total_duration: float, job_id: int) -> str:
    """
    Sinh luồng âm thanh lồng tiếng hoàn chỉnh cho toàn bộ video.
    """
    temp_dir = os.path.join(DOWNLOAD_DIR, f"job_{job_id}_tts_parts")
    os.makedirs(temp_dir, exist_ok=True)
    
    part_paths = []
    starts = []
    
    # 1. Sinh tiếng nói cho từng phân đoạn phụ đề dịch
    for i, seg in enumerate(translated_segments):
        target_dur = seg["end"] - seg["start"]
        part_path = os.path.join(temp_dir, f"part_{i}.wav")
        
        await generate_speech_for_segment(seg["text"], voice, target_dur, part_path)
        
        part_paths.append(part_path)
        starts.append(seg["start"])
        
    # 2. Trộn các phân đoạn thành một file âm thanh duy nhất khớp thời lượng video gốc
    dubbed_track_path = os.path.join(DOWNLOAD_DIR, f"job_{job_id}_dubbed.wav")
    mix_audio_tracks(part_paths, starts, total_duration, dubbed_track_path)
    
    # 3. Dọn dẹp thư mục tạm chứa các mảnh cắt
    for path in part_paths:
        if os.path.exists(path):
            try:
                os.remove(path)
            except Exception:
                pass
    try:
        os.rmdir(temp_dir)
    except Exception:
        pass
        
    return dubbed_track_path

def generate_dubbed_track(translated_segments: list, voice: str, total_duration: float, job_id: int) -> str:
    """Đầu gói đồng bộ (sync wrapper) để gọi hàm sinh âm thanh lồng tiếng bất đồng bộ."""
    return asyncio.run(generate_dubbed_track_async(translated_segments, voice, total_duration, job_id))

def apply_audio_ducking(original_audio_path: str, dubbed_audio_path: str, segments: list, bg_music_volume: float, output_mixed_path: str):
    """
    Áp dụng hiệu ứng Audio Ducking: Giảm âm lượng nhạc nền gốc khi có tiếng nói lồng tiếng vang lên,
    sau đó trộn nhạc nền đã duck với giọng nói lồng tiếng mới thành file âm thanh duy nhất.
    """
    if not os.path.exists(original_audio_path) or not os.path.exists(dubbed_audio_path):
        raise FileNotFoundError("Không tìm thấy file âm thanh gốc hoặc file lồng tiếng.")
        
    reduction = 1.0 - bg_music_volume
    terms = []
    for seg in segments:
        terms.append(f"between(t,{seg['start']},{seg['end']})")
        
    if terms:
        sum_expression = " + ".join(terms)
        filter_expr = f"[0:a]volume=1.0-{reduction}*({sum_expression}):eval=frame[bg];[bg][1:a]amix=inputs=2:duration=first[out]"
    else:
        # Nếu không có phân đoạn nào nói, chỉ trộn đơn thuần hoặc giữ nguyên nhạc nền
        filter_expr = "[0:a]volume=1.0[bg];[bg][1:a]amix=inputs=2:duration=first[out]"
        
    command = [
        FFMPEG_PATH,
        "-y",
        "-i", original_audio_path,
        "-i", dubbed_audio_path,
        "-filter_complex", filter_expr,
        "-map", "[out]",
        output_mixed_path
    ]
    
    process = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    )
    
    if process.returncode != 0:
        err = process.stderr.decode('utf-8', errors='ignore')
        logger.error(f"Lỗi FFmpeg khi trộn âm thanh ducking: {err}")
        raise Exception(f"Không thể trộn âm thanh ducking: {err}")
