"""
TTS Server - Wraps edge-tts for speech generation
Run this before starting pipeline: python tts_server.py
"""

import asyncio
import os
from pathlib import Path
import edge_tts
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uvicorn

# Output folder for generated audio - relative to this script
OUTPUT_DIR = Path(__file__).parent / "tts_output"
OUTPUT_DIR.mkdir(exist_ok=True)

app = FastAPI(title="Edge TTS Server", version="1.0")

# Serve the audio files directly over HTTP
app.mount("/audio", StaticFiles(directory=str(OUTPUT_DIR)), name="audio")


class TTSRequest(BaseModel):
    text: str
    voice: str = "en-US-GuyNeural"   # Deep male narrator - great for Manhwa
    rate: str = "+0%"                  # Speed: +10% faster, -10% slower
    pitch: str = "+0Hz"                # Pitch adjustment
    filename: str = None               # Optional custom filename


class TTSResponse(BaseModel):
    success: bool
    filename: str
    file_path: str
    url: str                           # Accessible via host.docker.internal


@app.get("/")
def root():
    return {
        "status": "running",
        "endpoints": {
            "POST /tts": "Generate speech from text",
            "GET /voices": "List available voices",
            "GET /audio/{filename}": "Download generated audio"
        }
    }


@app.get("/voices")
async def list_voices():
    """List all available voices"""
    voices = await edge_tts.list_voices()
    en_voices = [
        {"name": v["Name"], "gender": v["Gender"], "locale": v["Locale"]}
        for v in voices if v["Locale"].startswith("en-")
    ]
    return {"voices": en_voices, "total": len(en_voices)}


@app.post("/tts", response_model=TTSResponse)
async def generate_tts(request: TTSRequest):
    if not request.text or len(request.text.strip()) == 0:
        raise HTTPException(status_code=400, detail="Text cannot be empty")

    if len(request.text) > 10000:
        raise HTTPException(status_code=400, detail="Text too long (max 10000 chars)")

    filename = request.filename or f"narration_{uuid.uuid4().hex[:8]}.mp3"
    if not filename.endswith(".mp3"):
        filename += ".mp3"

    output_path = OUTPUT_DIR / filename

    max_retries = 3
    last_error = None
    
    for attempt in range(max_retries):
        try:
            communicate = edge_tts.Communicate(
                text=request.text,
                voice=request.voice,
                rate=request.rate,
                pitch=request.pitch
            )
            await communicate.save(str(output_path))
            break # Success!
        except Exception as e:
            last_error = e
            print(f"TTS attempt {attempt+1} failed: {e}")
            await asyncio.sleep(2)
    else:
        raise HTTPException(status_code=500, detail=f"TTS generation failed after {max_retries} attempts: {str(last_error)}")

    return TTSResponse(
        success=True,
        filename=filename,
        file_path=str(output_path),
        url=f"http://host.docker.internal:8765/audio/{filename}"
    )


@app.delete("/tts/{filename}")
def delete_audio(filename: str):
    """Clean up old audio files"""
    file_path = OUTPUT_DIR / filename
    if file_path.exists():
        file_path.unlink()
        return {"deleted": filename}
    raise HTTPException(status_code=404, detail="File not found")


if __name__ == "__main__":
    print("=" * 50)
    print("TTS Server starting on http://localhost:8765")
    print("Test URL: http://localhost:8765/docs")
    print("=" * 50)
    uvicorn.run(app, host="0.0.0.0", port=8765, log_level="info")
