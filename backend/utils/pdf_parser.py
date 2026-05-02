import io
import os


# Token budget per provider (conservative — prompt template adds ~1,500 tokens on top)
# ~4 chars per token on average for English text
_PROVIDER_MAX_CHARS = {
    'groq':   7000,   # 12k TPM limit on free tier; 7k chars ≈ 1,750 tokens for content
    'gemini': 10000,  # Generous free tier
    'openai': 10000,  # Paid; 10k chars is plenty for good question generation
}


def get_max_chars() -> int:
    """Return the safe content character limit for the active AI provider."""
    provider = os.getenv('AI_PROVIDER', 'groq').lower()
    return _PROVIDER_MAX_CHARS.get(provider, 7000)


def extract_text_from_pdf(file_bytes: bytes) -> str:
    """
    Extract text from PDF bytes.
    Tries PyMuPDF first, falls back to pdfplumber.
    Raises ValueError if text cannot be extracted.
    """
    text = ""

    # --- Attempt 1: PyMuPDF (fitz) ---
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        if doc.page_count == 0:
            raise ValueError("PDF has no pages.")
        for page_num in range(doc.page_count):
            page = doc.load_page(page_num)
            page_text = page.get_text("text")
            if page_text:
                text += page_text + "\n"
        doc.close()
        cleaned = text.strip()
        if cleaned and len(cleaned) > 50:
            return cleaned
    except ValueError:
        raise
    except Exception as e:
        print(f"[PDF] PyMuPDF extraction failed: {e}")

    # --- Attempt 2: pdfplumber ---
    try:
        import pdfplumber
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            if len(pdf.pages) == 0:
                raise ValueError("PDF has no pages.")
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
        cleaned = text.strip()
        if cleaned and len(cleaned) > 50:
            return cleaned
    except ValueError:
        raise
    except Exception as e:
        print(f"[PDF] pdfplumber extraction failed: {e}")

    # --- Both failed ---
    if text.strip():
        return text.strip()

    raise ValueError(
        "Unable to extract readable text from this PDF. "
        "The file may be image-based (scanned), corrupted, or password-protected. "
        "Please upload a text-based PDF."
    )


def chunk_text(text: str, max_chars: int = None) -> str:
    """
    Truncate text to max_chars for AI processing while preserving sentence boundaries.
    If max_chars is not given, uses the provider-aware default from get_max_chars().
    """
    if max_chars is None:
        max_chars = get_max_chars()

    if len(text) <= max_chars:
        return text

    truncated = text[:max_chars]
    # Try to cut at a sentence boundary
    last_period = truncated.rfind('. ')
    if last_period > max_chars * 0.8:
        truncated = truncated[:last_period + 1]

    return truncated + "\n\n[Content truncated for processing]"