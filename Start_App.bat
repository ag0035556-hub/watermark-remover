@echo off
echo Starting Magic Watermark Remover...
echo.
echo Please wait a moment while the server starts up.
echo DO NOT close this black window!
echo.
start http://127.0.0.1:8000
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
