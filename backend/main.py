import os
import uuid
import cv2
import numpy as np
from fastapi import FastAPI, File, UploadFile, Request, Form
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import time
from starlette.background import BackgroundTask
import mimetypes
import subprocess

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Setup directories
UPLOAD_DIR = "uploads"
PROCESSED_DIR = "processed"
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(PROCESSED_DIR, exist_ok=True)

# Local development fallback will be mounted at the end of the file

def process_frame(frame, x, y, width, height, algorithm="ns", radius=7, alpha=0.0, prev_roi=None, inflation=10, feather=31):
    if width <= 0 or height <= 0:
        return frame, prev_roi, 0.0
        
    frame_height, frame_width = frame.shape[:2]
    
    x1 = max(0, x)
    y1 = max(0, y)
    x2 = min(frame_width, x + width)
    y2 = min(frame_height, y + height)
    
    if x2 <= x1 or y2 <= y1:
        return frame, prev_roi, 0.0
        
    # Expand the ROI to give inpainting surrounding context
    margin = 25
    ex1 = max(0, x1 - margin)
    ey1 = max(0, y1 - margin)
    ex2 = min(frame_width, x2 + margin)
    ey2 = min(frame_height, y2 + margin)
    
    # Extract the expanded region to process
    roi_expanded = frame[ey1:ey2, ex1:ex2]
    
    # Coordinates of the watermark inside the expanded ROI
    ix1 = x1 - ex1
    iy1 = y1 - ey1
    ix2 = x2 - ex1
    iy2 = y2 - ey1
    
    # Create the hard binary mask for inpainting
    mask = np.zeros(roi_expanded.shape[:2], dtype=np.uint8)
    
    # INFLATE the mask by user-defined pixels to cover compression artifacts around the watermark
    miy1 = max(0, iy1 - inflation)
    miy2 = min(roi_expanded.shape[0], iy2 + inflation)
    mix1 = max(0, ix1 - inflation)
    mix2 = min(roi_expanded.shape[1], ix2 + inflation)
    mask[miy1:miy2, mix1:mix2] = 255
    # Perform inpainting using the selected algorithm
    inpaint_start = time.time()
    inpaint_flag = cv2.INPAINT_TELEA if algorithm == "telea" else cv2.INPAINT_NS
    inpainted_roi = cv2.inpaint(roi_expanded, mask, inpaintRadius=radius, flags=inpaint_flag)
    inpaint_time = time.time() - inpaint_start
    
    # Temporal smoothing to reduce flickering (only applied to video frames)
    if prev_roi is not None and alpha > 0.0 and prev_roi.shape == inpainted_roi.shape:
        inpainted_roi = cv2.addWeighted(inpainted_roi, 1.0 - alpha, prev_roi, alpha, 0)
        
    current_inpainted_roi = inpainted_roi.copy()
    
    # Calculate noise variance from a safe background patch to add back natural video grain
    # This prevents the inpainted patch from looking artificially smooth
    noise_patch = roi_expanded[0:margin, 0:margin]
    mean, stddev = cv2.meanStdDev(noise_patch)
    noise = np.zeros(inpainted_roi.shape, np.int16)
    cv2.randn(noise, 0, float(stddev[0][0]))
    inpainted_with_noise = cv2.add(inpainted_roi, noise, dtype=cv2.CV_8UC3)
    
    # Create a soft mask for blending to feather the edges
    soft_mask = np.zeros(roi_expanded.shape[:2], dtype=np.float32)
    soft_mask[miy1:miy2, mix1:mix2] = 1.0
    # Blur the mask to create feathered edges using user-defined feather value
    # Feather must be an odd number for GaussianBlur
    feather_kernel = int(feather) if int(feather) % 2 != 0 else int(feather) + 1
    soft_mask = cv2.GaussianBlur(soft_mask, (feather_kernel, feather_kernel), 0)
    
    # Expand soft mask to 3 channels for broadcasting with the color frame
    soft_mask_3c = cv2.cvtColor(soft_mask, cv2.COLOR_GRAY2BGR)
    
    # Blend the original expanded ROI and the inpainted ROI for a natural merge
    blended_roi = roi_expanded.astype(np.float32) * (1.0 - soft_mask_3c) + inpainted_with_noise.astype(np.float32) * soft_mask_3c
    
    # Put the blended ROI back into the frame
    frame[ey1:ey2, ex1:ex2] = blended_roi.astype(np.uint8)
    return frame, current_inpainted_roi, inpaint_time

MAX_FILE_SIZE = 50 * 1024 * 1024 # 50 MB

def cleanup_old_files():
    now = time.time()
    for directory in [UPLOAD_DIR, PROCESSED_DIR]:
        for filename in os.listdir(directory):
            filepath = os.path.join(directory, filename)
            if os.path.isfile(filepath):
                # Delete files older than 15 minutes (900 seconds)
                if now - os.path.getmtime(filepath) > 900:
                    try:
                        os.remove(filepath)
                    except:
                        pass

@app.post("/upload")
async def upload_video(file: UploadFile = File(...)):
    cleanup_old_files()
    file_id = str(uuid.uuid4())
    ext = os.path.splitext(file.filename)[1] or ".mp4"
    filename = f"{file_id}{ext}"
    filepath = os.path.join(UPLOAD_DIR, filename)
    
    size = 0
    with open(filepath, "wb") as f:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > MAX_FILE_SIZE:
                os.remove(filepath)
                return {"error": "File size exceeds 50MB limit"}
            f.write(chunk)
        
    return {"file_id": filename, "url": f"/download_input/{filename}"}

@app.get("/download_input/{file_id}")
async def download_input(file_id: str):
    file_path = os.path.join(UPLOAD_DIR, file_id)
    if os.path.exists(file_path):
        mime_type, _ = mimetypes.guess_type(file_path)
        mime_type = mime_type or 'application/octet-stream'
        return FileResponse(file_path, media_type=mime_type)
    return {"error": "File not found"}

@app.post("/process")
async def process_media(
    file_id: str = Form(...),
    x: int = Form(...),
    y: int = Form(...),
    width: int = Form(...),
    height: int = Form(...),
    algorithm: str = Form("telea"),
    radius: int = Form(15),
    smoothing: float = Form(0.5),
    inflation: int = Form(20),
    feather: int = Form(45),
    is_video: str = Form(...)
):
    total_start_time = time.time()
    total_inpaint_time = 0.0
    total_frame_processing_time = 0.0
    ffmpeg_time = 0.0
    
    input_path = os.path.join(UPLOAD_DIR, file_id)
    if not os.path.exists(input_path):
        return {"error": "File not found"}
        
    is_video_bool = is_video.lower() == "true"
    
    output_filename = f"processed_{file_id}"
    output_path = os.path.join(PROCESSED_DIR, output_filename)
    
    if is_video_bool:
        # Process video with OpenCV
        cap = cv2.VideoCapture(input_path)
        if not cap.isOpened():
            return {"error": "Could not open video"}
            
        fps = cap.get(cv2.CAP_PROP_FPS)
        frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        
        # We need a temp path for the video without audio
        temp_output_path = os.path.join(PROCESSED_DIR, f"temp_{output_filename}")
        
        fourcc_h264 = cv2.VideoWriter_fourcc(*'avc1')
        out = cv2.VideoWriter(temp_output_path, fourcc_h264, fps, (frame_width, frame_height))
        
        # If H264 is not supported by the system's OpenCV build, fallback to standard mp4v
        if not out.isOpened():
            fourcc_mp4v = cv2.VideoWriter_fourcc(*'mp4v')
            out = cv2.VideoWriter(temp_output_path, fourcc_mp4v, fps, (frame_width, frame_height))
            
        prev_roi = None
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            frame_start_time = time.time()
            frame, prev_roi, inpaint_time = process_frame(frame, x, y, width, height, algorithm, radius, smoothing, prev_roi, inflation, feather)
            total_inpaint_time += inpaint_time
            out.write(frame)
            total_frame_processing_time += (time.time() - frame_start_time)
            
        cap.release()
        out.release()
        
        # Combine the processed video with original audio using ffmpeg and re-encode for mobile compatibility
        ffmpeg_start_time = time.time()
        try:
            subprocess.run([
                "ffmpeg", "-y", 
                "-i", temp_output_path, 
                "-i", input_path, 
                "-map", "0:v:0", 
                "-map", "1:a:0?", 
                "-c:v", "libx264", 
                "-preset", "ultrafast",
                "-crf", "28",
                "-pix_fmt", "yuv420p",
                "-c:a", "aac", 
                "-b:a", "128k",
                "-movflags", "+faststart",
                output_path
            ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            # Clean up temp file
            if os.path.exists(temp_output_path):
                os.remove(temp_output_path)
        except Exception as e:
            # If ffmpeg fails, fallback to the silent video
            if os.path.exists(temp_output_path):
                os.rename(temp_output_path, output_path)
        ffmpeg_time = time.time() - ffmpeg_start_time
    else:
        # Process image (no temporal smoothing)
        img = cv2.imread(input_path)
        if img is None:
            return {"error": "Could not open image"}
        frame_start_time = time.time()
        img, _, inpaint_time = process_frame(img, x, y, width, height, algorithm, radius, 0.0, None, inflation, feather)
        total_inpaint_time += inpaint_time
        cv2.imwrite(output_path, img)
        total_frame_processing_time += (time.time() - frame_start_time)
        
    # Auto-delete the input file to save disk space
    if os.path.exists(input_path):
        os.remove(input_path)
        
    print("\n" + "="*40)
    print("TIMING LOGS:")
    print(f"  Watermark removal time: {total_inpaint_time:.3f}s")
    print(f"  Frame processing time:  {total_frame_processing_time:.3f}s")
    print(f"  FFmpeg encoding time:   {ffmpeg_time:.3f}s")
    print(f"  Total processing time:  {(time.time() - total_start_time):.3f}s")
    print("="*40 + "\n")
    
    return {"status": "success", "download_url": f"/download/{output_filename}"}

def delete_file(path: str):
    if os.path.exists(path):
        os.remove(path)

@app.get("/download/{file_id}")
async def download_media(file_id: str):
    file_path = os.path.join(PROCESSED_DIR, file_id)
    if os.path.exists(file_path):
        mime_type, _ = mimetypes.guess_type(file_path)
        mime_type = mime_type or 'application/octet-stream'
        return FileResponse(file_path, media_type=mime_type, filename=f"cleaned_{file_id}")
    return {"error": "File not found"}

# Mount frontend for local development testing (must be at the end to not override API routes)
FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")
if os.path.exists(FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
