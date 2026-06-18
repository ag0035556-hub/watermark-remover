// API Configuration
// Using relative paths since frontend and backend are hosted together on Render.
const API_URL = 'https://watermark-remover-gt3d.onrender.com';

const mediaUpload = document.getElementById('mediaUpload');
const editorSection = document.getElementById('editorSection');
const videoPreview = document.getElementById('videoPreview');
const imagePreview = document.getElementById('imagePreview');
const drawCanvas = document.getElementById('drawCanvas');
const ctx = drawCanvas.getContext('2d');
const clearBtn = document.getElementById('clearBtn');
const processBtn = document.getElementById('processBtn');
const loadingSection = document.getElementById('loadingSection');
const resultSection = document.getElementById('resultSection');
const downloadLink = document.getElementById('downloadLink');

const previewBtn = document.getElementById('previewBtn');
const finalPreviewContainer = document.getElementById('finalPreviewContainer');
const finalVideoPreview = document.getElementById('finalVideoPreview');
const finalImagePreview = document.getElementById('finalImagePreview');

const algorithmSelect = document.getElementById('algorithmSelect');
const radiusRange = document.getElementById('radiusRange');
const radiusVal = document.getElementById('radiusVal');
const inflationRange = document.getElementById('inflationRange');
const inflationVal = document.getElementById('inflationVal');
const featherRange = document.getElementById('featherRange');
const featherVal = document.getElementById('featherVal');
const smoothingRange = document.getElementById('smoothingRange');
const smoothingVal = document.getElementById('smoothingVal');

radiusRange.addEventListener('input', (e) => radiusVal.textContent = e.target.value);
inflationRange.addEventListener('input', (e) => inflationVal.textContent = e.target.value);
featherRange.addEventListener('input', (e) => featherVal.textContent = e.target.value);
smoothingRange.addEventListener('input', (e) => smoothingVal.textContent = e.target.value);

let currentFileId = null;
let isDrawing = false;
let startX = 0;
let startY = 0;
let rect = { x: 0, y: 0, w: 0, h: 0 };
let hasRect = false;
let isVideo = true;

const uploadSection = document.getElementById('uploadSection');
const startOverBtn = document.getElementById('startOverBtn');

// Handle drag and drop styling
uploadSection.addEventListener('dragover', (e) => {
    e.preventDefault();
    uploadSection.classList.add('dragover');
});

uploadSection.addEventListener('dragleave', () => {
    uploadSection.classList.remove('dragover');
});

uploadSection.addEventListener('drop', (e) => {
    e.preventDefault();
    uploadSection.classList.remove('dragover');
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
        mediaUpload.files = e.dataTransfer.files;
        handleFileUpload(e.dataTransfer.files[0]);
    }
});

// Handle click upload
mediaUpload.addEventListener('change', (e) => {
    if (e.target.files && e.target.files.length > 0) {
        handleFileUpload(e.target.files[0]);
    }
});

async function handleFileUpload(file) {
    if (!file) return;

    isVideo = file.type.startsWith('video/');

    const formData = new FormData();
    formData.append('file', file);

    try {
        const response = await fetch(`${API_URL}/upload`, {
            method: 'POST',
            body: formData
        });
        
        if (!response.ok) {
            let errorMsg = `Server error ${response.status}`;
            try {
                const errData = await response.json();
                errorMsg = errData.error || errData.detail || errorMsg;
            } catch (e) {
                errorMsg = await response.text();
            }
            throw new Error(errorMsg);
        }
        
        const data = await response.json();

        if (data.file_id) {
            currentFileId = data.file_id;
            
            if (isVideo) {
                videoPreview.src = `${API_URL}${data.url}`;
                videoPreview.style.display = 'block';
                imagePreview.style.display = 'none';
            } else {
                imagePreview.src = `${API_URL}${data.url}`;
                imagePreview.style.display = 'block';
                videoPreview.style.display = 'none';
            }
            
            editorSection.style.display = 'block';
            uploadSection.style.display = 'none';
            resultSection.style.display = 'none';
            
            // Clear previous drawings
            rect = { x: 0, y: 0, w: 0, h: 0 };
            hasRect = false;
            
            if (!isVideo) {
                imagePreview.onload = () => {
                    drawCanvas.width = imagePreview.clientWidth;
                    drawCanvas.height = imagePreview.clientHeight;
                    ctx.clearRect(0, 0, drawCanvas.width, drawCanvas.height);
                };
            }
        }
    } catch (error) {
        console.error('Upload failed:', error);
        alert('Upload failed');
    }
}

// Setup canvas over video
videoPreview.addEventListener('loadedmetadata', () => {
    if (isVideo) {
        drawCanvas.width = videoPreview.clientWidth;
        drawCanvas.height = videoPreview.clientHeight;
        ctx.clearRect(0, 0, drawCanvas.width, drawCanvas.height);
    }
});

window.addEventListener('resize', () => {
    if (isVideo && videoPreview.src) {
        drawCanvas.width = videoPreview.clientWidth;
        drawCanvas.height = videoPreview.clientHeight;
    } else if (!isVideo && imagePreview.src) {
        drawCanvas.width = imagePreview.clientWidth;
        drawCanvas.height = imagePreview.clientHeight;
    }
    drawRect(); // Redraw if exists
});

// Drawing logic
// Prevent scrolling on touch devices
drawCanvas.style.touchAction = 'none';

drawCanvas.addEventListener('pointerdown', (e) => {
    const rectBounds = drawCanvas.getBoundingClientRect();
    startX = e.clientX - rectBounds.left;
    startY = e.clientY - rectBounds.top;
    isDrawing = true;
    hasRect = false;
    drawCanvas.setPointerCapture(e.pointerId);
});

drawCanvas.addEventListener('pointermove', (e) => {
    if (!isDrawing) return;
    
    const rectBounds = drawCanvas.getBoundingClientRect();
    const currentX = e.clientX - rectBounds.left;
    const currentY = e.clientY - rectBounds.top;
    
    rect.x = Math.min(startX, currentX);
    rect.y = Math.min(startY, currentY);
    rect.w = Math.abs(currentX - startX);
    rect.h = Math.abs(currentY - startY);
    
    drawRect();
});

drawCanvas.addEventListener('pointerup', (e) => {
    isDrawing = false;
    if (rect.w > 0 && rect.h > 0) {
        hasRect = true;
    }
    drawCanvas.releasePointerCapture(e.pointerId);
});

drawCanvas.addEventListener('pointercancel', (e) => {
    isDrawing = false;
    drawCanvas.releasePointerCapture(e.pointerId);
});

function drawRect() {
    ctx.clearRect(0, 0, drawCanvas.width, drawCanvas.height);
    if (rect.w > 0 && rect.h > 0) {
        ctx.strokeStyle = 'red';
        ctx.lineWidth = 2;
        ctx.setLineDash([5, 5]);
        ctx.strokeRect(rect.x, rect.y, rect.w, rect.h);
        ctx.fillStyle = 'rgba(255, 0, 0, 0.2)';
        ctx.fillRect(rect.x, rect.y, rect.w, rect.h);
    }
}

clearBtn.addEventListener('click', () => {
    rect = { x: 0, y: 0, w: 0, h: 0 };
    hasRect = false;
    ctx.clearRect(0, 0, drawCanvas.width, drawCanvas.height);
});

// Process media
processBtn.addEventListener('click', async () => {
    if (!currentFileId) return alert('Please upload a file first');
    if (!hasRect) return alert('Please draw a rectangle over the watermark/patch');

    // Calculate relative coordinates based on intrinsic media resolution
    let scaleX, scaleY;
    if (isVideo) {
        scaleX = videoPreview.videoWidth / drawCanvas.width;
        scaleY = videoPreview.videoHeight / drawCanvas.height;
    } else {
        scaleX = imagePreview.naturalWidth / drawCanvas.width;
        scaleY = imagePreview.naturalHeight / drawCanvas.height;
    }

    const realX = Math.round(rect.x * scaleX);
    const realY = Math.round(rect.y * scaleY);
    const realW = Math.round(rect.w * scaleX);
    const realH = Math.round(rect.h * scaleY);

    const formData = new FormData();
    formData.append('file_id', currentFileId);
    formData.append('x', realX);
    formData.append('y', realY);
    formData.append('width', realW);
    formData.append('height', realH);
    formData.append('algorithm', algorithmSelect.value);
    formData.append('radius', radiusRange.value);
    formData.append('inflation', inflationRange.value);
    formData.append('feather', featherRange.value);
    formData.append('smoothing', smoothingRange.value);
    formData.append('is_video', isVideo);

    editorSection.style.display = 'none';
    loadingSection.style.display = 'block';

    try {
        const response = await fetch(`${API_URL}/process`, {
            method: 'POST',
            body: formData
        });
        const data = await response.json();
        
        loadingSection.style.display = 'none';
        
        if (data.status === 'success') {
            resultSection.style.display = 'block';
            downloadLink.href = `${API_URL}${data.download_url}`;
            
            // Setup preview logic
            finalPreviewContainer.style.display = 'none';
            finalVideoPreview.style.display = 'none';
            finalImagePreview.style.display = 'none';
            previewBtn.textContent = 'Preview Result';
            
            previewBtn.onclick = () => {
                if (finalPreviewContainer.style.display === 'none') {
                    finalPreviewContainer.style.display = 'block';
                    previewBtn.textContent = 'Hide Preview';
                    
                    if (isVideo) {
                        finalVideoPreview.src = `${API_URL}${data.download_url}`;
                        finalVideoPreview.style.display = 'block';
                    } else {
                        finalImagePreview.src = `${API_URL}${data.download_url}`;
                        finalImagePreview.style.display = 'block';
                    }
                } else {
                    finalPreviewContainer.style.display = 'none';
                    previewBtn.textContent = 'Preview Result';
                    if (isVideo) {
                        finalVideoPreview.pause();
                    }
                }
            };
            
        } else {
            throw new Error(data.error || 'Unknown processing error');
        }
    } catch (error) {
        console.error('Processing failed with detailed error:', error);
        alert(`Processing failed:\n${error.message}`);
        loadingSection.style.display = 'none';
        editorSection.style.display = 'block';
    }
});

startOverBtn.addEventListener('click', () => {
    currentFileId = null;
    resultSection.style.display = 'none';
    uploadSection.style.display = 'block';
    editorSection.style.display = 'none';
    mediaUpload.value = '';
    
    if (isVideo) {
        finalVideoPreview.pause();
        finalVideoPreview.removeAttribute('src');
        videoPreview.removeAttribute('src');
    } else {
        finalImagePreview.removeAttribute('src');
        imagePreview.removeAttribute('src');
    }
});
