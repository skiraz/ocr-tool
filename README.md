# OCR Document Converter

Convert images/PDFs to markdown text using the Datalab OCR API, and process exam PDFs to inject grades and MCQ answers into CSV files.

## Requirements

- Python 3.10+
- A Datalab API key (get one at https://www.datalab.to)

## Setup

### 1. Create a virtual environment

```bash
python3.10 -m venv venv
```

### 2. Activate the virtual environment

**Linux/macOS:**
```bash
source venv/bin/activate
```

**Windows:**
```bash
venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Set your API key

Three ways to provide the API key (in order of priority):

**Option A: CLI argument (highest priority)**
```bash
python api.py page_1.png --api-key your-api-key-here
```

**Option B: Environment variable**

**Linux/macOS:**
```bash
export DATALAB_API_KEY='your-api-key-here'
```

**Windows (CMD):**
```cmd
set DATALAB_API_KEY=your-api-key-here
```

**Windows (PowerShell):**
```powershell
$env:DATALAB_API_KEY='your-api-key-here'
```

**Option C: .env file (lowest priority)**
```bash
cp .env.example .env
```
Then edit `.env` and replace `your-api-key-here` with your actual key. The script reads this automatically.

---

## Processing Exam PDFs (`process.py`)

The main workflow. Extracts data from cover page PDFs and MCQ PDFs, then injects the results into CSV files.

### How it works

1. **Cover PDF** (`cover.pdf`): Extracts the first page, OCRs it, parses the student name and marks from the "For Examiners Use Only" table, and fills the `Q1 - 30` column in `CoverPage.csv`.

2. **MCQ PDF** (`mcq3.pdf`): OCRs each page, parses the student name and MCQ answers (A/B/C/D), splits them into `Q1 - 10` and `Q2 - 20` columns (space-separated capitals), and fills `mcq.csv`.

Students are matched between PDF and CSV by **name** (case-insensitive).

### Usage

**Process both PDFs:**
```bash
python process.py --cover cover.pdf --cover-csv CoverPage.csv --mcq mcq3.pdf --mcq-csv mcq.csv
```

**Process only the cover PDF:**
```bash
python process.py --cover cover.pdf --cover-csv CoverPage.csv
```

**Process only the MCQ PDF:**
```bash
python process.py --mcq mcq3.pdf --mcq-csv mcq.csv
```

**With API key:**
```bash
python process.py --cover cover.pdf --cover-csv CoverPage.csv --api-key YOUR_KEY
```

**Custom output directory:**
```bash
python process.py --cover cover.pdf --cover-csv CoverPage.csv -o my_output/
```

### CSV format

**CoverPage.csv:**
```
Student ID,Student Name,Q1 - 30
88886,Khaled Hassan,20, 3, 3, 7, 7
```

**mcq.csv:**
```
Student ID,Student Name,Q1 - 10,Q2 - 20
88886,Khaled Hassan,C C D A A B B D C C,D D A B A A B B C A
```

### process.py options

```
--cover PATH        Path to the cover page PDF
--cover-csv PATH    Path to CoverPage CSV (default: CoverPage.csv)
--mcq PATH          Path to the MCQ PDF
--mcq-csv PATH      Path to MCQ CSV (default: mcq.csv)
-o, --output-dir    Directory for OCR output files (default: output)
--api-key KEY       Datalab API key (overrides env var and .env file)
```

---

## Raw OCR Conversion (`api.py`)

For direct file-to-markdown conversion without CSV injection.

### Convert a single file

```bash
# Print markdown to stdout
python api.py page_1.png

# Save markdown to a file
python api.py page_1.png -o output/page_1.md
```

### Batch convert a directory

```bash
python api.py --batch input_folder/ -o output_folder/
```

### api.py options

```
positional:
  input               Input file path (image or PDF)

optional:
  -o, --output        Output file path or directory
  -f, --format        Output format: markdown, json, text
  -m, --mode          Conversion mode: fast, balanced, accurate
  --no-paginate       Disable pagination
  --batch DIR         Batch mode: convert all files in directory
  --api-key KEY       Datalab API key
```

---

## Supported File Types

- PDF (`.pdf`)
- PNG (`.png`)
- JPEG (`.jpg`, `.jpeg`)
- TIFF (`.tiff`)
- BMP (`.bmp`)
- WebP (`.webp`)

## Running as a Service (Linux)

```ini
[Unit]
Description=OCR Exam Processor
After=network.target

[Service]
Type=simple
User=your-user
WorkingDirectory=/path/to/ocr-tool
Environment=DATALAB_API_KEY=your-api-key-here
ExecStart=/path/to/ocr-tool/venv/bin/python /path/to/ocr-tool/process.py --cover cover.pdf --cover-csv CoverPage.csv --mcq mcq3.pdf --mcq-csv mcq.csv
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

## Project Structure

```
ocr-tool/
  api.py             Raw OCR conversion script
  process.py         Exam PDF processor (cover + MCQ -> CSV injection)
  requirements.txt   Python dependencies
  .env.example       Example environment config
  .gitignore         Git ignore rules
  run.sh             Linux/macOS run script
  run.bat            Windows run script
  README.md          This file
```
