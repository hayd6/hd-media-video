# HD Media

## AI Video Translator Platform

### Product Requirement Document (PRD)

Version: 1.1

---

# 1. Mục tiêu

Xây dựng website **HD Media**, một nền tảng AI tự động dịch và xử lý video.

Người dùng chỉ cần:

```text
Dán link video
        ↓
Nhấn Start
        ↓
Đợi xử lý
        ↓
Download video
        hoặc
Upload Google Drive
```

Toàn bộ quy trình phải được AI tự động hóa.

Không yêu cầu người dùng có kiến thức kỹ thuật.

---

# 2. Mục tiêu chính

Website cần:

- Download video từ nhiều nền tảng
- Phân tích video
- Nhận diện lời nói
- OCR nếu cần
- Dịch AI
- Tạo phụ đề
- Lồng tiếng AI
- Giảm tiếng gốc
- Giữ nhạc nền
- Render video
- Sinh Thumbnail
- Sinh SEO
- Upload Google Drive
- Xuất video hoàn chỉnh

---

# 3. Công nghệ

## Frontend

- Next.js
- React
- TailwindCSS

---

## Backend

Python

Framework:

FastAPI

---

## Database

SQLite

Thiết kế để sau này chuyển sang PostgreSQL.

---

## Queue

Redis

RQ hoặc Celery

---

## Storage

Local Storage

hoặc

MinIO

---

# 4. Công cụ (100% miễn phí)

Downloader

- yt-dlp

Video

- FFmpeg

Speech Recognition

- faster-whisper

OCR

- PaddleOCR

Subtitle

- pysubs2

Audio Separation

- Demucs

Voice

- Edge TTS

AI Translation

- Gemini API
  (API Key do người dùng nhập)

Cloud Upload

- Google Drive API

---

# 5. Pipeline

```text
User

↓

Paste URL

↓

Download

↓

Extract Metadata

↓

Extract Audio

↓

Speech Detection

↓

Language Detection

↓

Whisper

↓

Gemini Translation

↓

Subtitle Optimization

↓

Edge TTS

↓

Demucs

↓

Audio Ducking

↓

Subtitle Rendering (ASS)

↓

FFmpeg Render

↓

Thumbnail

↓

SEO

↓

Google Drive Upload (Optional)

↓

Done
```

---

# 6 → 31

(Giữ nguyên toàn bộ nội dung từ phiên bản PRD trước.)

---

# 32. Google Drive Integration

## Mục tiêu

Sau khi render thành công.

Website có thể:

- Upload video lên Google Drive
- Upload phụ đề
- Upload thumbnail
- Upload file SEO
- Upload audio
- Tạo Link Share
- Lưu lịch sử

---

## Đăng nhập

Lần đầu:

```text
Login Google

↓

Cho phép quyền Drive

↓

Lưu Token
```

Sau này:

Không cần đăng nhập lại.

---

## Chế độ Upload

### Mode 1

Không upload.

Chỉ download.

---

### Mode 2

Upload sau khi Render.

---

### Mode 3

Render

↓

Upload

↓

Hiện nút Download.

---

## Upload File

Sau khi Render.

Upload:

- video.mp4
- subtitle.ass
- subtitle.srt
- audio_vi.mp3
- thumbnail.jpg
- seo.txt

---

## Cấu trúc thư mục Drive

```text
Google Drive

HD Media/

├── Finished/
├── Subtitle/
├── Audio/
├── Thumbnail/
├── SEO/
└── Archive/
```

Nếu chưa có.

AI tự tạo.

---

## Link Share

Sau Upload.

AI tự:

- Lấy Link Share
- Copy Link
- Open Drive
- Download

---

## History

Lưu:

Tên video

Link gốc

Link Google Drive

Ngày Upload

Dung lượng

ID File

Trạng thái Upload

---

## Retry

Nếu Upload lỗi.

Retry

3 lần.

---

## Resume Upload

Nếu mạng mất.

Upload tiếp phần còn lại.

Không upload lại từ đầu.

---

## API

POST

/api/google/login

Đăng nhập Google.

---

POST

/api/google/upload/{job_id}

Upload.

---

GET

/api/google/files/{job_id}

Danh sách file.

---

DELETE

/api/google/file/{file_id}

Xóa file Drive.

---

# 33. Workflow Engine

```text
Có lời nói?

YES

↓

Whisper

NO

↓

OCR

------------------------

Có phụ đề cứng?

↓

OCR Merge

------------------------

Có nhạc?

↓

Demucs

NO

↓

FFmpeg

------------------------

Render

↓

SEO

↓

Thumbnail

↓

Google Drive Upload (Nếu bật)

↓

Done
```

---

# 34. UI

Dashboard

```
HD Media

──────────────────────

Paste URL

[__________________]

Output Language

☑ Vietnamese

☑ English

Voice

☑ Female

☑ Male

Upload after Render

☑ Google Drive

──────────────────────

Start

──────────────────────

Progress

Download

Upload Drive

History
```

---

# 35. Mục tiêu cuối cùng

Người dùng chỉ cần:

```text
Paste URL

↓

Click Start

↓

AI tự:

Download

↓

Speech Recognition

↓

OCR (nếu cần)

↓

Translate

↓

Subtitle

↓

Voice

↓

Audio Separation

↓

Render

↓

Thumbnail

↓

SEO

↓

Upload Google Drive (nếu bật)

↓

Download
```

Toàn bộ quá trình được AI xử lý hoàn toàn tự động với các công cụ miễn phí và mã nguồn mở. Chỉ riêng Gemini API yêu cầu người dùng cung cấp API Key của chính họ để thực hiện dịch AI.

# 36. Processing Mode

Website có 2 chế độ xử lý.

## Mode 1 - Standard Translate

Dùng để:

- Dịch video
- Lồng tiếng
- Phụ đề
- Giữ nguyên video gốc

Workflow

Download

↓

Translate

↓

Subtitle

↓

Render

↓

Done

---

## Mode 2 - Reup Mode

Dùng để tạo phiên bản mới của video mà người dùng có quyền chỉnh sửa hoặc tái sử dụng.

Cho phép lựa chọn:

☑ Thay đổi tốc độ

0.90x

0.95x

1.00x

1.05x

1.10x

---

☑ Điều chỉnh Brightness

-20

↓

+20

---

☑ Điều chỉnh Contrast

-20

↓

+20

---

☑ Saturation

-20

↓

+20

---

☑ Sharpen

On / Off

---

☑ Denoise

On / Off

---

☑ Mirror

Flip Horizontal

Flip Vertical

---

☑ Crop

Custom

9:16

16:9

1:1

---

☑ Resize

720P

1080P

2K

4K

---

☑ Watermark

Không

Logo PNG

Logo SVG

Logo GIF

Logo Video

Có thể chỉnh:

Opacity

Size

Position

Animation

---

☑ Intro

Thêm Intro

0~10 giây

---

☑ Outro

Thêm Outro

0~10 giây

---

☑ Background Music

Không

Upload MP3

Điều chỉnh Volume

---

☑ Thumbnail

Tự sinh

Hoặc Upload

---

☑ Metadata

Title

Description

Tags

Category

# 37. Progress Monitor

Hiển thị tiến trình chi tiết.

Ví dụ

Download

100%

---

Analyze

100%

---

Speech Recognition

Đang xử lý

Segment

250 / 820

30%

---

Translate

Batch

15 / 48

42%

---

Subtitle

260 / 820

---

Voice

120 / 820

---

Audio Separation

65%

---

Render

Frame

35620 / 81234

74%

---

Upload Google Drive

480 MB

/

1.2 GB

---

Done

100%

# 38. History Center

Lưu toàn bộ lịch sử.

Mỗi Job gồm:

- Job ID
- Tên video
- URL gốc
- Nền tảng
- Thời gian bắt đầu
- Thời gian hoàn thành
- Thời gian xử lý
- Dung lượng
- Ngôn ngữ nguồn
- Ngôn ngữ đích
- Voice
- Chế độ
- Link Google Drive
- Link Download
- Thumbnail
- SEO
- Log

Có thể:

☑ Search

☑ Filter

☑ Delete

☑ Retry

☑ Re-render

☑ Download lại

# 39. Job Log

Lưu log theo từng bước.

Ví dụ

10:30:15

Download Started

10:31:52

Download Complete

10:32:05

Whisper Started

10:45:20

Whisper Finished

10:45:25

Gemini Started

10:48:33

Gemini Finished

10:49:10

Edge TTS Started

...

11:02:18

Render Finished

11:04:02

Google Drive Uploaded
