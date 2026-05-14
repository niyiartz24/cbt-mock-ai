"""
CBT Mock AI — AI Service
Default provider: Gemini (free, generous limits)
Fallback: Groq, OpenAI
"""

import json
import re
import os
import time
from typing import List, Dict, Tuple

PROVIDER_MODELS = {
    'gemini': 'gemini-1.5-flash',
    'groq':   'llama-3.3-70b-versatile',
    'openai': 'gpt-4o-mini',
}


# ── Provider dispatch ──────────────────────────────────────────

def _get_provider() -> str:
    return os.getenv('AI_PROVIDER', 'gemini').strip().lower()


def _call_gemini(api_key: str, prompt: str, temperature: float, max_tokens: int) -> str:
    try:
        import google.generativeai as genai
    except ImportError:
        raise ImportError("Run: pip install google-generativeai")
    if not api_key:
        raise ValueError("GEMINI_API_KEY is not set in your .env file.\nGet a free key at: https://aistudio.google.com")
    genai.configure(api_key=api_key)
    cfg = genai.types.GenerationConfig(temperature=temperature, max_output_tokens=max_tokens)
    model = genai.GenerativeModel(model_name=PROVIDER_MODELS['gemini'], generation_config=cfg)
    response = model.generate_content(prompt)
    return response.text


def _call_openai_compatible(api_key: str, base_url: str, model: str, prompt: str, temperature: float, max_tokens: int) -> str:
    try:
        from openai import OpenAI
    except ImportError:
        raise ImportError("Run: pip install openai")
    if not api_key:
        provider = 'GROQ' if 'groq' in base_url else 'OPENAI'
        raise ValueError(f"{provider}_API_KEY is not set in your .env file.")
    client = OpenAI(api_key=api_key, base_url=base_url)
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return response.choices[0].message.content


def _call_ai(prompt: str, temperature: float, max_tokens: int, retries: int = 3) -> str:
    """
    Call the configured AI provider.
    Retries on per-minute rate limits (TPM/413/429).
    Raises a clear human-readable error on daily quota exhaustion.
    """
    provider = _get_provider()

    def _dispatch():
        if provider == 'gemini':
            return _call_gemini(os.getenv('GEMINI_API_KEY', ''), prompt, temperature, max_tokens)
        elif provider == 'groq':
            return _call_openai_compatible(
                os.getenv('GROQ_API_KEY', ''),
                'https://api.groq.com/openai/v1',
                PROVIDER_MODELS['groq'], prompt, temperature, max_tokens)
        elif provider == 'openai':
            return _call_openai_compatible(
                os.getenv('OPENAI_API_KEY', ''),
                'https://api.openai.com/v1',
                PROVIDER_MODELS['openai'], prompt, temperature, max_tokens)
        else:
            raise ValueError(f"Unknown AI_PROVIDER: '{provider}'. Must be: gemini, groq, openai")

    attempt = 0
    while True:
        try:
            return _dispatch()

        except Exception as e:
            err_str = str(e).lower()

            # Daily quota exhausted — no point retrying
            if 'tokens per day' in err_str or ('tpd' in err_str and '429' in str(e)):
                import re as _re
                wait_match = _re.search(r'try again in ([\w\s\.]+)', str(e), _re.IGNORECASE)
                wait_hint = f" Try again in {wait_match.group(1)}." if wait_match else ""
                raise Exception(
                    f"Daily AI quota exhausted for {provider.upper()}.{wait_hint} "
                    f"Switch provider or wait for reset. "
                    f"To use Gemini: set AI_PROVIDER=gemini and GEMINI_API_KEY in .env"
                )

            # Per-minute rate limit — retry with backoff
            is_rate_limit = (
                'tokens per minute' in err_str or
                'tpm' in err_str or
                '413' in str(e) or
                ('429' in str(e) and 'tpd' not in err_str)
            )
            if is_rate_limit and attempt < retries:
                wait = 15 * (attempt + 1)
                print(f"[AI] Rate limit hit — waiting {wait}s (attempt {attempt + 1}/{retries})...")
                time.sleep(wait)
                attempt += 1
                continue

            raise


# ── Shared helpers ─────────────────────────────────────────────

def _clean_json_response(raw: str) -> str:
    raw = raw.strip()
    raw = re.sub(r'^```json\s*', '', raw, flags=re.IGNORECASE)
    raw = re.sub(r'^```\s*', '', raw)
    raw = re.sub(r'\s*```$', '', raw)
    return raw.strip()


def _clean_html(raw: str) -> str:
    content = raw.strip()
    content = re.sub(r'^```html\s*', '', content, flags=re.IGNORECASE)
    content = re.sub(r'\s*```$', '', content)
    return content.strip()


def _validate_questions(raw_list: list) -> List[Dict]:
    required = {'question', 'option_a', 'option_b', 'option_c', 'option_d', 'correct_answer'}
    valid_answers = {'A', 'B', 'C', 'D'}
    validated = []
    seen = set()

    for item in raw_list:
        if not isinstance(item, dict) or not required.issubset(item.keys()):
            continue
        q_text = str(item['question']).strip()
        answer = str(item.get('correct_answer', '')).strip().upper()
        if len(q_text) < 10 or answer not in valid_answers:
            continue
        if q_text.lower() in seen:
            continue
        seen.add(q_text.lower())
        validated.append({
            'question':       q_text,
            'option_a':       str(item['option_a']).strip(),
            'option_b':       str(item['option_b']).strip(),
            'option_c':       str(item['option_c']).strip(),
            'option_d':       str(item['option_d']).strip(),
            'correct_answer': answer,
            'explanation':    str(item.get('explanation', '')).strip(),
        })
    return validated


# ── Prompts ────────────────────────────────────────────────────

def _questions_prompt(text: str, course_name: str, count: int) -> str:
    return f"""You are an expert Nigerian university lecturer creating a CBT exam for the course: "{course_name}".

The content below may have been extracted from a scanned document or PowerPoint slides, so the formatting may be imperfect. Read carefully and generate exactly {count} multiple-choice questions based on the actual educational concepts in the text.

REQUIREMENTS:
- Every question must come directly from concepts in this content
- Each question has exactly 4 options labeled A, B, C, D — only ONE is correct
- No duplicate or near-duplicate questions
- Mix difficulty: easy, medium, hard
- Spread correct answers across A, B, C, D evenly
- Include a one-sentence explanation for each correct answer
- Write clear, unambiguous questions

CONTENT:
{text}

Output ONLY a valid JSON array with no preamble, explanation, or markdown fences:
[
  {{
    "question": "Question text here?",
    "option_a": "First option",
    "option_b": "Second option",
    "option_c": "Third option",
    "option_d": "Fourth option",
    "correct_answer": "A",
    "explanation": "Brief reason why A is correct."
  }}
]"""


def _summary_prompt(text: str, course_name: str) -> str:
    return f"""You are an expert academic summariser creating study notes for the course: "{course_name}".

The content below may have been extracted from a scanned document or slides, so formatting may be imperfect. Extract the key educational concepts and produce well-structured study notes.

CONTENT:
{text}

Return ONLY valid HTML — no explanation, no markdown fences:
<div class="summary-content">
  <h2>Topic Name</h2>
  <p>Brief introduction...</p>
  <h3>Subtopic</h3>
  <ul>
    <li><strong>Key term</strong>: Explanation</li>
  </ul>
</div>

Rules:
- h2 for major topics, h3 for subtopics
- ul/li for lists, strong for key terms
- Cover ALL major concepts
- Do not add intro/conclusion sentences about this being a summary"""


# ── Public API ─────────────────────────────────────────────────

def generate_questions(text: str, course_name: str, api_key: str = '') -> Tuple[List[Dict], str]:
    """
    Generate MCQ questions from extracted PDF text.
    Splits large text into chunks and calls AI once per chunk.
    Returns (questions_list, warning_message).
    """
    from utils.pdf_parser import split_into_chunks

    # Clean up noisy OCR text before sending
    text = _clean_extracted_text(text)

    if len(text) < 200:
        return [], "Extracted text is too short to generate questions. The PDF may be empty or unreadable."

    chunks = split_into_chunks(text)
    print(f"[AI] Generating questions: {len(chunks)} chunk(s), {len(text)} total chars")

    questions_per_chunk = max(20, 55 // len(chunks))
    all_questions: List[Dict] = []
    seen = set()

    for i, chunk in enumerate(chunks):
        print(f"[AI] Questions chunk {i+1}/{len(chunks)} ({len(chunk)} chars)...")
        prompt = _questions_prompt(chunk, course_name, count=questions_per_chunk)

        try:
            raw = _call_ai(prompt, temperature=0.6, max_tokens=6000)
            cleaned = _clean_json_response(raw)
            raw_list = json.loads(cleaned)
            chunk_qs = _validate_questions(raw_list)
        except json.JSONDecodeError as e:
            print(f"[AI] Chunk {i+1} JSON error: {e} — raw: {cleaned[:300]}")
            chunk_qs = []
        except Exception as e:
            print(f"[AI] Chunk {i+1} error: {type(e).__name__}: {e}")
            raise

        # Deduplicate across chunks
        for q in chunk_qs:
            key = q['question'].lower()
            if key not in seen:
                seen.add(key)
                all_questions.append(q)

        print(f"[AI] Chunk {i+1} done: {len(chunk_qs)} questions. Total: {len(all_questions)}")

        if i < len(chunks) - 1:
            time.sleep(3)

    warning = ""
    if len(all_questions) < 40:
        warning = (
            f"Only {len(all_questions)} valid questions generated "
            f"(40 needed to publish). Try uploading a longer or clearer document."
        )

    return all_questions, warning


def generate_summary(text: str, course_name: str, api_key: str = '') -> str:
    """
    Generate structured HTML study notes from extracted PDF text.
    """
    from utils.pdf_parser import split_into_chunks

    text = _clean_extracted_text(text)

    if len(text) < 200:
        return "<div class='summary-content'><p>Insufficient content extracted from the PDF to generate a summary.</p></div>"

    chunks = split_into_chunks(text)
    print(f"[AI] Generating summary: {len(chunks)} chunk(s)")

    if len(chunks) == 1:
        raw = _call_ai(_summary_prompt(chunks[0], course_name), temperature=0.4, max_tokens=4000)
        return _clean_html(raw)

    # Multi-chunk: summarise each, then merge
    partials = []
    for i, chunk in enumerate(chunks):
        print(f"[AI] Summary chunk {i+1}/{len(chunks)}...")
        try:
            raw = _call_ai(_summary_prompt(chunk, course_name), temperature=0.4, max_tokens=3000)
            partials.append(_clean_html(raw))
        except Exception as e:
            print(f"[AI] Summary chunk {i+1} failed: {e}")
            raise
        if i < len(chunks) - 1:
            time.sleep(3)

    if len(partials) == 1:
        return partials[0]

    # Merge all partials into one clean document
    combined = "\n\n".join(partials)
    merge_prompt = f"""You are an academic editor. Merge these partial HTML study note sections for "{course_name}" into one clean, non-repetitive HTML document.

{combined}

Return ONLY a single merged HTML block using h2, h3, p, ul, li, strong. Remove duplicates. No markdown fences."""

    try:
        print("[AI] Merging summary chunks...")
        time.sleep(3)
        raw = _call_ai(merge_prompt, temperature=0.3, max_tokens=4000)
        return _clean_html(raw)
    except Exception as e:
        print(f"[AI] Merge failed: {e} — returning concatenated partials")
        return "\n".join(partials)


def _clean_extracted_text(text: str) -> str:
    """
    Clean up noisy text from PDF extraction or OCR before sending to AI.
    Removes garbage characters, excessive whitespace, and repeated lines.
    """
    # Normalise whitespace
    text = re.sub(r'\r\n', '\n', text)
    text = re.sub(r'\r', '\n', text)

    # Remove lines that are purely noise (single chars, page numbers, dots)
    lines = text.split('\n')
    cleaned_lines = []
    seen_lines = set()

    for line in lines:
        stripped = line.strip()
        # Skip empty, single-char, page-number-only, or fully duplicate lines
        if not stripped:
            cleaned_lines.append('')
            continue
        if len(stripped) <= 2:
            continue
        if re.match(r'^\d+$', stripped):  # pure page numbers
            continue
        # Skip heavily repeated lines (common in bad OCR)
        key = stripped.lower()
        if key in seen_lines:
            continue
        seen_lines.add(key)
        cleaned_lines.append(stripped)

    # Collapse multiple blank lines into one
    text = '\n'.join(cleaned_lines)
    text = re.sub(r'\n{3,}', '\n\n', text)

    return text.strip()


def get_active_provider() -> Dict:
    provider = _get_provider()
    return {
        'provider': provider,
        'model':    PROVIDER_MODELS.get(provider, 'unknown'),
        'free':     provider in ('gemini', 'groq'),
    }
