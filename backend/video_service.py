import os
import subprocess
import logging
from config import FFMPEG_PATH

logger = logging.getLogger("video_service")

def escape_ffmpeg_path(path: str) -> str:
    """
    Format đường dẫn Windows để hoạt động chính xác trong filter của FFmpeg (ví dụ: filter subtitles).
    Thay thế backslash '\' thành '/' và escape dấu hai chấm ':' thành '\\:'.
    """
    path = path.replace("\\", "/")
    if ":" in path:
        drive, rest = path.split(":", 1)
        path = f"{drive}\\\\:{rest}"
    return path

def render_video(video_path: str, audio_path: str, subtitle_path: str, output_path: str, job: dict) -> str:
    """
    Thực hiện render video bằng FFmpeg, ghép âm thanh đã trộn (dubbed + bg) và chèn phụ đề ASS,
    đồng thời áp dụng toàn bộ cấu hình nâng cao nếu ở chế độ Reup Mode.
    """
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Không tìm thấy video gốc: {video_path}")
        
    mode = job.get("mode", "standard")
    
    # 1. Chuẩn bị các bộ lọc Video (Video Filter Graph)
    v_filters = []
    
    # --- Chế độ Reup Mode ---
    if mode == "reup":
        # Tốc độ (Speed)
        speed = job.get("speed", 1.0)
        if speed != 1.0:
            # setpts = 1/speed * PTS
            v_filters.append(f"setpts={1.0/speed:.4f}*PTS")
            
        # Điều chỉnh Brightness, Contrast, Saturation
        brightness = job.get("brightness", 0.0) # -20 đến +20
        contrast = job.get("contrast", 0.0)     # -20 đến +20
        saturation = job.get("saturation", 0.0) # -20 đến +20
        
        # Ánh xạ từ (-20 -> +20) sang giá trị chuẩn của FFmpeg eq filter
        # Brightness: -0.1 đến 0.1
        # Contrast: 0.8 đến 1.2
        # Saturation: 0.8 đến 1.2
        b_val = brightness / 200.0
        c_val = 1.0 + (contrast / 100.0)
        s_val = 1.0 + (saturation / 100.0)
        
        if b_val != 0.0 or c_val != 1.0 or s_val != 1.0:
            v_filters.append(f"eq=brightness={b_val:.3f}:contrast={c_val:.3f}:saturation={s_val:.3f}")
            
        # Làm nét (Sharpen)
        if job.get("sharpen"):
            v_filters.append("unsharp=5:5:0.8:5:5:0.0")
            
        # Khử nhiễu (Denoise)
        if job.get("denoise"):
            v_filters.append("hqdn3d=1.5:1.5:6:6")
            
        # Đối xứng/Lật hình (Mirror)
        mirror = job.get("mirror", "none")
        if mirror == "horizontal":
            v_filters.append("hflip")
        elif mirror == "vertical":
            v_filters.append("vflip")
            
        # Cắt khung hình (Crop)
        crop = job.get("crop", "none")
        if crop == "9:16":
            v_filters.append("crop=ih*9/16:ih")
        elif crop == "16:9":
            v_filters.append("crop=iw:iw*9/16")
        elif crop == "1:1":
            v_filters.append("crop=ih:ih")
            
        # Thay đổi kích thước (Resize/Scale)
        resize = job.get("resize", "none")
        if resize == "720p":
            v_filters.append("scale=-2:720")
        elif resize == "1080p":
            v_filters.append("scale=-2:1080")
        elif resize == "2k":
            v_filters.append("scale=-2:1440")
        elif resize == "4k":
            v_filters.append("scale=-2:2160")

    # 2. Xử lý âm thanh (Audio Filters & Concat)
    # Nếu thay đổi tốc độ ở Reup Mode, ta phải tăng/giảm tốc độ âm thanh tương ứng
    a_filters = []
    if mode == "reup":
        speed = job.get("speed", 1.0)
        if speed != 1.0:
            temp_speed = speed
            while temp_speed > 2.0:
                a_filters.append("atempo=2.0")
                temp_speed /= 2.0
            while temp_speed < 0.5:
                a_filters.append("atempo=0.5")
                temp_speed /= 0.5
            a_filters.append(f"atempo={temp_speed:.4f}")
            
    a_filter_str = ",".join(a_filters) if a_filters else "copy"

    # 3. Chuẩn bị Watermark (Logo) nếu có
    # Tải Watermark và overlay nếu có trong cấu hình
    watermark_path = job.get("watermark_path")
    has_watermark = False
    if mode == "reup" and watermark_path and os.path.exists(watermark_path):
        has_watermark = True

    # 4. Xây dựng lệnh chạy FFmpeg
    command = [FFMPEG_PATH, "-y"]
    
    # Input 0: Video gốc
    command.extend(["-i", video_path])
    
    # Input 1: Âm thanh đã trộn (lồng tiếng + nhạc nền)
    if audio_path and os.path.exists(audio_path):
        command.extend(["-i", audio_path])
    else:
        # Nếu không có audio trộn, lấy âm thanh gốc của video
        pass

    # Nếu có Watermark, thêm làm Input 2 (hoặc 1 nếu không có audio ngoài)
    watermark_input_idx = 2 if (audio_path and os.path.exists(audio_path)) else 1
    if has_watermark:
        command.extend(["-i", watermark_path])

    # 2. Xây dựng Filter Complex cho Watermark + Phụ đề + Làm mờ nền + Video Filters cùng lúc
    filter_complex = []
    
    # Khởi tạo luồng video hiện tại
    curr_v = "0:v"
    
    # --- Áp dụng Reup Filters nếu ở chế độ reup ---
    if mode == "reup" and v_filters:
        v_filter_str = ",".join(v_filters)
        filter_complex.append(f"[{curr_v}]{v_filter_str}[v_reup]")
        curr_v = "v_reup"
        
    # --- Áp dụng Blur Bar (Che sub Trung/Sub gốc) nếu được bật ---
    sub_blur_bar = job.get("sub_blur_bar", True)
    if sub_blur_bar:
        blur_bar_h = job.get("sub_blur_bar_h", 80)
        sub_margin_v = job.get("sub_margin_v", 30)
        sub_alignment = job.get("sub_alignment", 2)
        
        sub_blur_bar_y = job.get("sub_blur_bar_y")
        if sub_blur_bar_y is not None:
            y_crop_expr = str(sub_blur_bar_y)
            y_overlay_expr = str(sub_blur_bar_y)
        else:
            if sub_alignment == 8: # Top
                # Tránh crop âm, sử dụng max(0, margin_v - blur_bar_h/2)
                y_crop_expr = f"max(0\\,{sub_margin_v}-{blur_bar_h}/2)"
                y_overlay_expr = f"max(0\\,{sub_margin_v}-{blur_bar_h}/2)"
            elif sub_alignment == 5: # Middle
                y_crop_expr = f"ih/2-{blur_bar_h}/2"
                y_overlay_expr = f"main_h/2-{blur_bar_h}/2"
            else: # Bottom (2)
                # y = ih - margin_v - blur_bar_h/2 (cho crop) và main_h - margin_v - blur_bar_h/2 (cho overlay)
                y_crop_expr = f"ih-{sub_margin_v}-{blur_bar_h}/2"
                y_overlay_expr = f"main_h-{sub_margin_v}-{blur_bar_h}/2"
                
        # Thực hiện split luồng, crop vùng cần mờ, làm mờ, rồi overlay đè lại
        filter_complex.append(f"[{curr_v}]split=2[v_orig][v_to_blur]")
        filter_complex.append(f"[v_to_blur]crop=w=iw:h={blur_bar_h}:x=0:y={y_crop_expr}[v_cropped]")
        filter_complex.append(f"[v_cropped]boxblur=20:5[v_blurred]")
        filter_complex.append(f"[v_orig][v_blurred]overlay=x=0:y={y_overlay_expr}[v_blur_applied]")
        curr_v = "v_blur_applied"
        
    # --- Chèn phụ đề ASS ---
    if subtitle_path and os.path.exists(subtitle_path):
        escaped_sub_path = escape_ffmpeg_path(subtitle_path)
        filter_complex.append(f"[{curr_v}]subtitles={escaped_sub_path}[v_subbed]")
        curr_v = "v_subbed"
        
    # --- Chèn Watermark ---
    if has_watermark:
        opacity = job.get("watermark_opacity", 0.5)
        size = job.get("watermark_size", 0.15)
        pos = job.get("watermark_position", "bottom_right")
        
        filter_complex.append(
            f"[{watermark_input_idx}:v]scale=iw*0.5:-1,format=pix_fmts=yuva420p,colorchannelmixer=aa={opacity}[wm]"
        )
        
        # Xác định vị trí overlay
        if pos == "top_left":
            overlay_expr = "x=15:y=15"
        elif pos == "top_right":
            overlay_expr = "x=main_w-overlay_w-15:y=15"
        elif pos == "bottom_left":
            overlay_expr = "x=15:y=main_h-overlay_h-15"
        else: # bottom_right
            overlay_expr = "x=main_w-overlay_w-15:y=main_h-overlay_h-15"
            
        filter_complex.append(f"[{curr_v}][wm]overlay={overlay_expr}[v_wm_applied]")
        curr_v = "v_wm_applied"
        
    # Xác định map video đầu ra
    video_map = f"[{curr_v}]" if curr_v != "0:v" else "0:v"

    # Lọc âm thanh (atempo nếu đổi tốc độ)
    if a_filter_str != "copy":
        # Xác định input audio: nếu có audio ngoài thì dùng 1:a, ngược lại dùng 0:a
        audio_in = "1:a" if (audio_path and os.path.exists(audio_path)) else "0:a"
        filter_complex.append(f"[{audio_in}]{a_filter_str}[a_out]")
        audio_map = "[a_out]"
    else:
        audio_map = "1:a" if (audio_path and os.path.exists(audio_path)) else "0:a"

    # Ráp các chuỗi filter complex
    if filter_complex:
        command.extend(["-filter_complex", ";".join(filter_complex)])
        command.extend(["-map", video_map])
        command.extend(["-map", audio_map])
    else:
        # Copy trực tiếp luồng nếu không có filter nào
        command.extend(["-map", "0:v"])
        command.extend(["-map", "1:a" if (audio_path and os.path.exists(audio_path)) else "0:a"])

    # Thiết lập codec đầu ra (H.264 mp4 chất lượng trung bình tốt, nén nhanh)
    command.extend([
        "-c:v", "libx264",
        "-preset", "faster",
        "-crf", "22",
        "-c:a", "aac",
        "-b:a", "128k",
        output_path
    ])
    
    logger.info(f"[Job {job.get('id')}] Đang kết xuất video cuối cùng sang {output_path}...")
    logger.info(f"Lệnh chạy FFmpeg: {' '.join(command)}")
    
    process = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    )
    
    if process.returncode != 0:
        err = process.stderr.decode('utf-8', errors='ignore')
        logger.error(f"[Job {job.get('id')}] Lỗi kết xuất video: {err}")
        raise Exception(f"Không thể kết xuất video: {err}")
        
    logger.info(f"[Job {job.get('id')}] Đã hoàn thành kết xuất video: {output_path}")
    return output_path
