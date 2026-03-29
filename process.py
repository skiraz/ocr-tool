#!/usr/bin/env python3
"""
OCR PDF Processor
Processes cover.pdf and mcq3.pdf, extracts student data via OCR,
and injects results into CoverPage.csv and mcq.csv.
"""

import os
import re
import sys
import csv
import argparse
import tempfile
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from datalab_sdk import DatalabClient, ConvertOptions


# ── API key helpers ──────────────────────────────────────────────────────────

def get_api_key(cli_key=None):
    if cli_key:
        return cli_key
    api_key = os.environ.get("DATALAB_API_KEY")
    if not api_key:
        env_file = Path(__file__).parent / ".env"
        if env_file.exists():
            with open(env_file, "r") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("DATALAB_API_KEY="):
                        api_key = line.split("=", 1)[1].strip().strip("'\"")
                        break
    if not api_key:
        print("Error: DATALAB_API_KEY not found. Use --api-key, env var, or .env file.", file=sys.stderr)
        sys.exit(1)
    return api_key


# ── PDF helpers ──────────────────────────────────────────────────────────────

def extract_page(input_pdf, page_index, output_path):
    """Extract a single page from a PDF."""
    reader = PdfReader(str(input_pdf))
    writer = PdfWriter()
    writer.add_page(reader.pages[page_index])
    with open(output_path, "wb") as f:
        writer.write(f)
    return output_path


def get_pdf_page_count(pdf_path):
    return len(PdfReader(str(pdf_path)).pages)


# ── OCR helper ───────────────────────────────────────────────────────────────

def ocr_file(file_path, client, options):
    """OCR a file and return markdown string."""
    print(f"  OCR: {Path(file_path).name}", file=sys.stderr)
    result = client.convert(str(file_path), options=options)
    return result.markdown


# ── Cover page parsing ───────────────────────────────────────────────────────

def parse_cover_markdown(md_text):
    """
    Parse cover page markdown to extract:
      - student_name (string)
      - student_no (string)
      - marks_str (string): space-separated marks earned, e.g. "20 3 3 7 7"
    """
    student_name = ""
    student_no = ""
    marks_values = []

    # Extract student name (stop at "Student No" if on same line)
    m = re.search(r'Student\s+Name\s*[:\-]\s*(.+?)(?:\s*Student\s+No|$)', md_text, re.IGNORECASE)
    if m:
        student_name = m.group(1).strip()

    # Extract student number – could be in a table or inline
    m = re.search(r'Student\s+No[:\.]?\s*[:\-]?\s*([\d\s]+)', md_text, re.IGNORECASE)
    if m:
        student_no = re.sub(r'\s+', '', m.group(1)).strip()

    # If student_no is empty, look for digit table after "Student No:"
    if not student_no:
        m = re.search(r'Student\s+No[:\.]?\s*[:\-]?\s*\n(.*)', md_text, re.IGNORECASE | re.DOTALL)
        if m:
            remaining = m.group(1)
            for line in remaining.split('\n'):
                stripped = line.strip()
                if re.match(r'^\|[\s\d\|]+\|$', stripped):
                    digits = re.findall(r'\d', stripped)
                    if digits:
                        student_no = ''.join(digits)
                        break

    # Parse the examiners table – extract only the "Marks Earned" values
    lines = md_text.split('\n')
    in_table = False

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        # Detect header row containing "Marks Earned"
        if 'Marks Earned' in stripped:
            in_table = True
            continue

        if in_table:
            # Skip separator rows
            if re.match(r'^\|[\s\-\|]+\|$', stripped):
                continue
            # Stop if we hit a non-table line
            if not stripped.startswith('|'):
                break
            # Parse table row
            cells = [c.strip() for c in stripped.split('|')]
            cells = [c for c in cells if c != '']
            if len(cells) >= 3:
                marks_earned = re.sub(r'<[^>]+>', '', cells[2]).strip()
                if marks_earned:
                    marks_values.append(marks_earned)

    marks_str = " ".join(marks_values)
    return student_name, student_no, marks_str


# ── MCQ page parsing ─────────────────────────────────────────────────────────

def parse_mcq_markdown(md_text):
    """
    Parse MCQ markdown to extract:
      - student_name (string)
      - student_no (string)
      - answers_str (space-separated capital letters, e.g. "A B C D A B ...")

    Supports two table formats:
      1. Answer column: | Question # | Answer |  with letter in Answer cell
      2. X-grid:        | Question # | A | B | C | D |  with X marking the choice
    """
    student_name = ""
    student_no = ""
    answers = []

    # Extract student name (stop at "Student No" if on same line)
    m = re.search(r'Student\s+Name\s*[:\-]\s*(.+?)(?:\s*Student\s+No|$)', md_text, re.IGNORECASE)
    if m:
        student_name = m.group(1).strip()

    # Extract student number
    m = re.search(r'Student\s+No[:\.]?\s*[:\-]?\s*([\d\s]+)', md_text, re.IGNORECASE)
    if m:
        student_no = re.sub(r'\s+', '', m.group(1)).strip()

    # If student_no is empty, look for digit table after "Student No:"
    if not student_no:
        m = re.search(r'Student\s+No[:\.]?\s*[:\-]?\s*\n(.*)', md_text, re.IGNORECASE | re.DOTALL)
        if m:
            remaining = m.group(1)
            for line in remaining.split('\n'):
                stripped = line.strip()
                if re.match(r'^\|[\s\d\|]+\|$', stripped):
                    digits = re.findall(r'\d', stripped)
                    if digits:
                        student_no = ''.join(digits)
                        break

    # Parse answer table
    lines = md_text.split('\n')
    in_table = False
    is_x_grid = False
    choice_cols = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        # Detect table header
        if not in_table:
            # Check for X-grid format: headers A B C D
            if re.search(r'\|\s*Question\s*#?\s*\|\s*A\s*\|\s*B\s*\|', stripped, re.IGNORECASE):
                in_table = True
                is_x_grid = True
                # Parse header to find which columns are A, B, C, D, E
                header_cells = [c.strip().upper() for c in stripped.split('|')]
                header_cells = [c for c in header_cells if c]
                choice_cols = header_cells[1:]  # skip "Question #"
                continue
            # Check for Answer column format
            if 'Answer' in stripped and 'Question' in stripped:
                in_table = True
                is_x_grid = False
                continue

        if in_table:
            if re.match(r'^\|[\s\-\|]+\|$', stripped):
                continue
            if not stripped.startswith('|'):
                break

            cells = [c.strip() for c in stripped.split('|')]
            # Remove first and last empty from leading/trailing |
            if cells and cells[0] == '':
                cells = cells[1:]
            if cells and cells[-1] == '':
                cells = cells[:-1]

            if is_x_grid and len(cells) >= 2:
                # X-grid: find which column has the X (check cells after question #)
                for ci, col_name in enumerate(choice_cols):
                    if ci + 1 < len(cells) and cells[ci + 1].strip().upper() in ('X', '✓', 'V'):
                        answers.append(col_name)
                        break
            elif not is_x_grid and len(cells) >= 2:
                # Answer column format
                answer = cells[-1].strip().upper()
                if answer in ('A', 'B', 'C', 'D', 'E'):
                    answers.append(answer)

    answers_str = " ".join(answers)
    return student_name, student_no, answers_str


# ── Name matching ────────────────────────────────────────────────────────────

def normalize_name(name):
    """Normalize a name for fuzzy matching."""
    return re.sub(r'\s+', ' ', name.strip().lower())


def find_csv_row_by_name(rows, target_name):
    """Find a CSV row matching the target name (case-insensitive)."""
    norm_target = normalize_name(target_name)
    for i, row in enumerate(rows):
        csv_name = normalize_name(row.get('Student Name', ''))
        if csv_name == norm_target:
            return i
    return None


# ── CSV operations ───────────────────────────────────────────────────────────

def read_csv(filepath):
    """Read a CSV file and return header + rows as list of dicts."""
    with open(filepath, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        header = reader.fieldnames
        rows = list(reader)
    return header, rows


def write_csv(filepath, header, rows):
    """Write header + rows back to CSV."""
    with open(filepath, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=header)
        writer.writeheader()
        writer.writerows(rows)


# ── Cover PDF processor ──────────────────────────────────────────────────────

def process_cover_pdf(cover_pdf, cover_csv, api_key, output_dir):
    """Extract first page from cover.pdf, OCR it, and inject grades into CoverPage.csv."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    header, rows = read_csv(cover_csv)

    # Ensure "Marks Earned" column exists
    if 'Marks Earned' not in header:
        header.append('Marks Earned')
        for row in rows:
            row['Marks Earned'] = ''

    client = DatalabClient(api_key)
    options = ConvertOptions(output_format="markdown", mode="balanced", paginate=True)

    # Extract first page only
    tmp_path = output_dir / "_cover_page_1.pdf"
    extract_page(cover_pdf, 0, tmp_path)

    # OCR
    md = ocr_file(tmp_path, client, options)

    # Save OCR output for reference
    md_out = output_dir / "cover_page_1.md"
    with open(md_out, 'w', encoding='utf-8') as f:
        f.write(md)

    # Parse
    student_name, student_no, marks_str = parse_cover_markdown(md)
    print(f"  Page 1: {student_name} ({student_no}) -> marks: {marks_str}", file=sys.stderr)

    if not student_name.strip():
        print(f"    Skipped (no student name found)", file=sys.stderr)
        tmp_path.unlink(missing_ok=True)
        write_csv(cover_csv, header, rows)
        return

    # Match and inject
    idx = find_csv_row_by_name(rows, student_name)
    if idx is not None:
        rows[idx]['Marks Earned'] = marks_str
        print(f"    Matched CSV row {idx}: {rows[idx]['Student Name']}", file=sys.stderr)
    else:
        new_row = {h: '' for h in header}
        new_row['Student ID'] = student_no
        new_row['Student Name'] = student_name
        new_row['Marks Earned'] = marks_str
        rows.append(new_row)
        print(f"    Created new row: {student_name} ({student_no})", file=sys.stderr)

    # Clean up temp file
    tmp_path.unlink(missing_ok=True)

    # Write updated CSV
    write_csv(cover_csv, header, rows)
    print(f"\nCover: CSV updated: {cover_csv}", file=sys.stderr)


# ── MCQ PDF processor ────────────────────────────────────────────────────────

def process_mcq_pdf(mcq_pdf, mcq_csv, api_key, output_dir):
    """OCR mcq PDF and inject MCQ answers into mcq.csv."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    header, rows = read_csv(mcq_csv)

    # Ensure "Answers" column exists
    if 'Answers' not in header:
        header.append('Answers')
        for row in rows:
            row['Answers'] = ''

    client = DatalabClient(api_key)
    options = ConvertOptions(output_format="markdown", mode="balanced", paginate=True)

    page_count = get_pdf_page_count(mcq_pdf)
    print(f"MCQ PDF: {page_count} pages", file=sys.stderr)

    for i in range(page_count):
        # Extract page to temp file
        tmp_path = output_dir / f"_mcq_page_{i+1}.pdf"
        extract_page(mcq_pdf, i, tmp_path)

        # OCR
        md = ocr_file(tmp_path, client, options)

        # Save OCR output for reference
        md_out = output_dir / f"mcq_page_{i+1}.md"
        with open(md_out, 'w', encoding='utf-8') as f:
            f.write(md)

        # Parse
        student_name, student_no, answers_str = parse_mcq_markdown(md)
        print(f"  Page {i+1}: {student_name} ({student_no}) -> answers: {answers_str}", file=sys.stderr)

        if not student_name.strip():
            print(f"    Skipped (no student name found)", file=sys.stderr)
            tmp_path.unlink(missing_ok=True)
            continue

        # Match and inject
        idx = find_csv_row_by_name(rows, student_name)
        if idx is not None:
            rows[idx]['Answers'] = answers_str
            print(f"    Matched CSV row {idx}: {rows[idx]['Student Name']}", file=sys.stderr)
        else:
            new_row = {h: '' for h in header}
            new_row['Student ID'] = student_no
            new_row['Student Name'] = student_name
            new_row['Answers'] = answers_str
            rows.append(new_row)
            print(f"    Created new row: {student_name} ({student_no})", file=sys.stderr)

        # Clean up temp file
        tmp_path.unlink(missing_ok=True)

    # Write updated CSV
    write_csv(mcq_csv, header, rows)
    print(f"\nMCQ: CSV updated: {mcq_csv}", file=sys.stderr)


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Process cover.pdf and mcq3.pdf, inject data into CSVs.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Process a single cover PDF and a single MCQ PDF
  python process.py --cover cover.pdf --cover-csv CoverPage.csv --mcq mcq3.pdf --mcq-csv mcq.csv

  # Process a folder of cover PDFs
  python process.py --cover cover_folder/ --cover-csv CoverPage.csv

  # Process a folder of MCQ PDFs
  python process.py --mcq mcq_folder/ --mcq-csv mcq.csv

  # Process folders of both
  python process.py --cover cover_folder/ --cover-csv CoverPage.csv --mcq mcq_folder/ --mcq-csv mcq.csv

  # Specify API key directly
  python process.py --cover cover.pdf --cover-csv CoverPage.csv --api-key YOUR_KEY
        """,
    )

    parser.add_argument("--cover", help="Path to cover PDF", default=None)
    parser.add_argument("--cover-csv", help="Path to CoverPage CSV", default="CoverPage.csv")
    parser.add_argument("--mcq", help="Path to MCQ PDF", default=None)
    parser.add_argument("--mcq-csv", help="Path to MCQ CSV", default="mcq.csv")
    parser.add_argument("-o", "--output-dir", help="Directory for OCR output files", default="output")
    parser.add_argument("--api-key", help="Datalab API key", default=None)

    args = parser.parse_args()

    if not args.cover and not args.mcq:
        parser.error("Provide at least --cover or --mcq")

    api_key = get_api_key(args.api_key)
    output_dir = Path(args.output_dir)

    if args.cover:
        print("=" * 60, file=sys.stderr)
        print("Processing Cover PDF(s)", file=sys.stderr)
        print("=" * 60, file=sys.stderr)
        cover_path = Path(args.cover)
        if cover_path.is_dir():
            pdf_files = sorted(cover_path.glob("*.pdf"))
            if not pdf_files:
                print(f"No PDF files found in {cover_path}", file=sys.stderr)
            else:
                print(f"Found {len(pdf_files)} PDF(s) in {cover_path}", file=sys.stderr)
                for pdf in pdf_files:
                    print(f"\n--- Processing: {pdf.name} ---", file=sys.stderr)
                    process_cover_pdf(str(pdf), args.cover_csv, api_key, output_dir)
        else:
            process_cover_pdf(args.cover, args.cover_csv, api_key, output_dir)

    if args.mcq:
        print("\n" + "=" * 60, file=sys.stderr)
        print("Processing MCQ PDF(s)", file=sys.stderr)
        print("=" * 60, file=sys.stderr)
        mcq_path = Path(args.mcq)
        if mcq_path.is_dir():
            pdf_files = sorted(mcq_path.glob("*.pdf"))
            if not pdf_files:
                print(f"No PDF files found in {mcq_path}", file=sys.stderr)
            else:
                print(f"Found {len(pdf_files)} PDF(s) in {mcq_path}", file=sys.stderr)
                for pdf in pdf_files:
                    print(f"\n--- Processing: {pdf.name} ---", file=sys.stderr)
                    process_mcq_pdf(str(pdf), args.mcq_csv, api_key, output_dir)
        else:
            process_mcq_pdf(args.mcq, args.mcq_csv, api_key, output_dir)

    print("\nDone.", file=sys.stderr)


if __name__ == "__main__":
    main()
