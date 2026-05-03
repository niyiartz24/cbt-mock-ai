import io
import os


# Safe content chars per AI call, per provider
_PROVIDER_CHUNK_CHARS = {
    'groq':   6500,   # ~1,600 tokens content + ~500 prompt = ~2,100/call, 3 calls = ~6,300 — safe under 12k TPM
    'gemini': 10000,
    'openai': 10000,
}

MAX_TOTAL_CHARS = 20000  # Hard cap on total extracted text sent for processing


def get_chunk_size() -> int:
    provider = os.getenv('AI_PROVIDER', 'groq').lower()
    return _PROVIDER_CHUNK_CHARS.get(provider, 6500)


def extract_text_from_pdf(file_bytes: bytes) -> str:
    """
    Extract text from a PDF.
    Method 1: PyMuPDF native text extraction (fast, works on text-based PDFs)
    Method 2: pdfplumber (fallback for text-based)
    Method 3: OCR via Tesseract (fallback for scanned/image-based PDFs)
    Raises ValueError only if all three methods fail.
    """
    # ── Method 1: PyMuPDF native ────────────────────────────────
    text = _try_pymupdf_text(file_bytes)
    if text:
        print(f"[PDF] Extracted {len(text)} chars via PyMuPDF text")
        return text

    # ── Method 2: pdfplumber ────────────────────────────────────
    text = _try_pdfplumber(file_bytes)
    if text:
        print(f"[PDF] Extracted {len(text)} chars via pdfplumber")
        return text

    # ── Method 3: OCR via Tesseract ─────────────────────────────
    print("[PDF] No text found via native extraction — attempting OCR...")
    text = _try_ocr(file_bytes)
    if text:
        print(f"[PDF] Extracted {len(text)} chars via OCR")
        return text

    raise ValueError(
        "Unable to extract readable text from this PDF. "
        "The file may be corrupted, password-protected, or in an unsupported format."
    )


def _try_pymupdf_text(file_bytes: bytes) -> str:
    try:
        import fitz
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        if doc.page_count == 0:
            raise ValueError("PDF has no pages.")
        text = ""
        for page in doc:
            page_text = page.get_text("text")
            if page_text:
                text += page_text + "\n"
        doc.close()
        cleaned = text.strip()
        return cleaned if len(cleaned) > 100 else ""
    except ValueError:
        raise
    except Exception as e:
        print(f"[PDF] PyMuPDF text failed: {e}")
        return ""


def _try_pdfplumber(file_bytes: bytes) -> str:
    try:
        import pdfplumber
        text = ""
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            if len(pdf.pages) == 0:
                raise ValueError("PDF has no pages.")
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
        cleaned = text.strip()
        return cleaned if len(cleaned) > 100 else ""
    except ValueError:
        raise
    except Exception as e:
        print(f"[PDF] pdfplumber failed: {e}")
        return ""


def _try_ocr(file_bytes: bytes) -> str:
    """
    Render each PDF page as an image using PyMuPDF, then run Tesseract OCR.
    Requires: pip install pytesseract Pillow
    Requires: tesseract binary installed on the OS.
    """
    try:
        import fitz
        import pytesseract
        from PIL import Image
        import numpy as np
    except ImportError as e:
        print(f"[PDF] OCR dependencies missing: {e}. "
              "Install with: pip install pytesseract Pillow  "
              "and ensure Tesseract is installed on your OS.")
        return ""

    try:
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        text = ""
        # Process up to 15 pages (more than enough for most notes)
        max_pages = min(doc.page_count, 15)

        for page_num in range(max_pages):
            page = doc.load_page(page_num)
            # Render at 200 DPI — good OCR quality without being too slow
            mat = fitz.Matrix(200 / 72, 200 / 72)
            pix = page.get_pixmap(matrix=mat, colorspace=fitz.csRGB)
            img_bytes = pix.tobytes("png")

            # Convert to PIL Image for Tesseract
            img = Image.open(io.BytesIO(img_bytes))
            page_text = pytesseract.image_to_string(img, lang='eng')
            if page_text.strip():
                text += page_text + "\n"

            print(f"[PDF] OCR page {page_num + 1}/{max_pages}: {len(page_text)} chars")

        doc.close()
        cleaned = text.strip()
        return cleaned if len(cleaned) > 100 else ""

    except Exception as e:
        print(f"[PDF] OCR failed: {e}")
        return ""


def split_into_chunks(text: str, chunk_size: int = None) -> list:
    """
    Split text into chunks of chunk_size chars, cutting at sentence boundaries.
    Total input is capped at MAX_TOTAL_CHARS.
    """
    if chunk_size is None:
        chunk_size = get_chunk_size()

    # Cap total input
    if len(text) > MAX_TOTAL_CHARS:
        text = text[:MAX_TOTAL_CHARS]
        # Try to cut at a sentence boundary
        last_period = text.rfind('. ')
        if last_period > MAX_TOTAL_CHARS * 0.9:
            text = text[:last_period + 1]
        text += "\n\n[Content truncated]"

    if len(text) <= chunk_size:
        return [text]

    chunks = []
    remaining = text

    while remaining:
        if len(remaining) <= chunk_size:
            chunks.append(remaining)
            break

        segment = remaining[:chunk_size]
        # Cut at sentence boundary
        cut = segment.rfind('. ')
        if cut > chunk_size * 0.7:
            segment = segment[:cut + 1]

        chunks.append(segment.strip())
        remaining = remaining[len(segment):].strip()

    return chunks


# Keep backward compat — used in a few places
def chunk_text(text: str, max_chars: int = None) -> str:
    if max_chars is None:
        max_chars = get_chunk_size()
    if len(text) <= max_chars:
        return text
    truncated = text[:max_chars]
    last_period = truncated.rfind('. ')
    if last_period > max_chars * 0.8:
        truncated = truncated[:last_period + 1]
    return truncated + "\n\n[Content truncated for processing]"
