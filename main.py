import asyncio
import re
from pathlib import Path
import aiofiles
from fastapi import FastAPI, UploadFile, File, Form, HTTPException

app = FastAPI()
BASE = Path("uploads")
SAFE_ID = re.compile(r"^[a-zA-Z0-9_-]{8,64}$")
CHUNK_SIZE = 1024 * 1024

def get_dir(upload_id: str) -> Path:
    if not SAFE_ID.match(upload_id):
        raise HTTPException(400, "upload_id tidak valid")
    d = BASE / upload_id
    d.mkdir(parents=True, exist_ok=True)
    return d

@app.post("/upload/chunk")
async def upload_chunk(
    upload_id: str = Form(...),
    index: int = Form(...),
    chunk: UploadFile = File(...),
):
    d = get_dir(upload_id)
    tmp = d / f"part_{index:06d}.wav.tmp"
    final = d / f"part_{index:06d}.wav"

    async with aiofiles.open(tmp, "wb") as f:
        while data := await chunk.read(CHUNK_SIZE):
            await f.write(data)
    tmp.rename(final)
    return {"received": index}

@app.post("/upload/complete")
async def complete(upload_id: str = Form(...), total: int = Form(...)):
    d = get_dir(upload_id)
    parts = sorted(d.glob("part_*.wav"))
    if len(parts) != total:
        raise HTTPException(400, f"Potongan kurang: {len(parts)}/{total}")

    list_file = d / "list.txt"
    list_file.write_text("".join(f"file '{p.name}'\n" for p in parts))

    out_path = d / "final.wav"
    try:
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", str(list_file), "-c", "copy", str(out_path),
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError:
        raise HTTPException(500, "ffmpeg belum terpasang di server")

    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise HTTPException(500, f"ffmpeg gagal: {stderr.decode()[-500:]}")

    for p in parts:
        p.unlink()
    list_file.unlink()

    return {"path": str(out_path)}