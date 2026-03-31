#!/usr/bin/env python3
"""
OCR API Server
Two endpoints:
  POST /mcq   - receives PDF files, returns JSON with MCQ answers
  POST /cover - receives PDF files, returns JSON with marks

Run:  py -3.10 server.py
Docs: http://localhost:8000/docs
Test: http://localhost:8000/
"""

import os
import io
import sys
import asyncio
import tempfile
from pathlib import Path
from typing import List
from concurrent.futures import ThreadPoolExecutor

# Ensure process.py can be imported regardless of working directory
sys.path.insert(0, str(Path(__file__).parent))

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from pypdf import PdfReader, PdfWriter
from datalab_sdk import DatalabClient, ConvertOptions

from process import parse_mcq_markdown, parse_cover_markdown

app = FastAPI(title="OCR Exam Processor")
executor = ThreadPoolExecutor()


def load_api_key():
    """Load API key from env var or .env file."""
    key = os.environ.get("DATALAB_API_KEY", "")
    if not key:
        env_file = Path(__file__).parent / ".env"
        if env_file.exists():
            with open(env_file, "r") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("DATALAB_API_KEY="):
                        key = line.split("=", 1)[1].strip().strip("'\"")
                        break
    return key


API_KEY = load_api_key()


def get_client():
    if not API_KEY:
        raise HTTPException(status_code=500, detail="DATALAB_API_KEY not configured. Set env var or add to .env file.")
    return DatalabClient(API_KEY)


@app.get("/", response_class=HTMLResponse)
def home():
    return """
    <html>
    <head><title>OCR Exam Processor</title></head>
    <body style="font-family: Arial; max-width: 800px; margin: 40px auto;">
        <h1>OCR Exam Processor API</h1>

        <h2>Test MCQ Endpoint</h2>
        <form action="/mcq" method="post" enctype="multipart/form-data">
            <input type="file" name="files" accept=".pdf" multiple><br><br>
            <button type="submit">Process MCQ</button>
        </form>

        <h2>Test Cover Endpoint</h2>
        <form action="/cover" method="post" enctype="multipart/form-data">
            <input type="file" name="files" accept=".pdf" multiple><br><br>
            <button type="submit">Process Cover</button>
        </form>

        <hr>
        <p>API Docs: <a href="/docs">/docs</a></p>
    </body>
    </html>
    """


def extract_first_page(input_bytes: bytes) -> bytes:
    """Extract first page from a PDF given as bytes."""
    reader = PdfReader(io.BytesIO(input_bytes))
    writer = PdfWriter()
    writer.add_page(reader.pages[0])
    buf = io.BytesIO()
    writer.write(buf)
    buf.seek(0)
    return buf.read()


def ocr_sync(file_bytes: bytes, api_key: str, options) -> str:
    """Run OCR in a sync thread to avoid event loop conflicts."""
    client = DatalabClient(api_key)
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(file_bytes)
        tmp_path = tmp.name
    try:
        result = client.convert(tmp_path, options=options)
        return result.markdown
    finally:
        os.unlink(tmp_path)


async def ocr_bytes(file_bytes: bytes, options) -> str:
    """OCR a file in a thread to avoid asyncio event loop conflicts."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(executor, ocr_sync, file_bytes, API_KEY, options)


@app.post("/mcq")
async def process_mcq(files: List[UploadFile] = File(...)):
    """
    Upload MCQ PDF file(s). Returns JSON array of students with answers.
    Each PDF can contain one or more pages (one student per page).
    Supports both answer-column and X-grid formats.

    Response:
    [
        {"id": "20180321", "name": "Ali Ahmad", "answers": "A B B B A A B D D C B C B D C B C A A A"},
        ...
    ]
    """
    try:
        if not API_KEY:
            return JSONResponse(status_code=500, content={"error": "DATALAB_API_KEY not configured"})

        options = ConvertOptions(output_format="markdown", mode="balanced", paginate=True)
        results = []

        for upload_file in files:
            content = await upload_file.read()
            reader = PdfReader(io.BytesIO(content))
            page_count = len(reader.pages)

            for i in range(page_count):
                writer = PdfWriter()
                writer.add_page(reader.pages[i])
                buf = io.BytesIO()
                writer.write(buf)
                page_bytes = buf.getvalue()

                md = await ocr_bytes(page_bytes, options)
                student_name, student_no, answers_str = parse_mcq_markdown(md)

                if not student_name.strip():
                    continue

                results.append({
                    "id": student_no,
                    "name": student_name,
                    "answers": answers_str,
                })

        return JSONResponse(content=results)
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.post("/cover")
async def process_cover(files: List[UploadFile] = File(...)):
    """
    Upload cover page PDF file(s). Returns JSON array of students with marks.
    Only the first page of each PDF is processed.

    Response:
    [
        {"id": "20221084", "name": "Lori Ketchjian", "grades": "20 3 3 7 7 40"},
        ...
    ]
    """
    try:
        if not API_KEY:
            return JSONResponse(status_code=500, content={"error": "DATALAB_API_KEY not configured"})

        options = ConvertOptions(output_format="markdown", mode="balanced", paginate=True)
        results = []

        for upload_file in files:
            content = await upload_file.read()
            page_bytes = extract_first_page(content)

            md = await ocr_bytes(page_bytes, options)
            student_name, student_no, marks_str = parse_cover_markdown(md)

            if not student_name.strip():
                continue

            results.append({
                "id": student_no,
                "name": student_name,
                "grades": marks_str,
            })

        return JSONResponse(content=results)
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
