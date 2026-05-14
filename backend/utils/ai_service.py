"""
CBT Mock AI — AI Service
Default: gemini-2.5-flash-lite (free, 1500 req/day, 15 RPM)
"""

import json
import re
import os
import time
from typing import List, Dict, Tuple

PROVIDER_MODELS = {
    'gemini': 'gemini-2.5-flash-lite-preview-06-17',
    'groq':   'llama-3.3-70b-versatile',
    'openai': 'gpt-4o-mini',
}


def _get_provider() -> str:
    return os.getenv('AI_PROVIDER', 'gemini').strip().lower()


def _call_openai_compatible(api_key: str, base_url: str, model: str,
                             prompt: str, temperature: float, max_tokens: int) -> str:
    try:
        from openai import OpenAI
    except ImportError:
        raise ImportError("Run: pip install openai")
    if not api_key:
        provider = 'GROQ' if 'groq' in base_url else 'GEMINI'
        raise ValueError(f"{provider}_API_KEY is not set in your .env file.")
    client = OpenAI(api_key=api_key, base_url=base_url)
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return response.choices[0].message.content


def _call_ai(prompt: str, temperature: float, max_tokens: int) -> str:
    """
    Call the configured AI provider.
    NO sleep/retry — Gunicorn sync workers timeout at 30s and get SIGKILL.
    Rate limit errors surface immediately with a clear human-readable message.
    """
    provider = _get_provider()

    try:
        if provider == 'gemini':
            api_key = os.getenv('GEMINI_API_KEY', '')
            if not api_key:
                raise ValueError(
                    "GEMINI_API_KEY is not set. "
                    "Get a free key at: https://aistudio.google.com"
                )
            return _call_openai_compatible(
                api_key=api_key,
                base_url='https://generativelanguage.googleapis.com/v1beta/openai/',
                model=PROVIDER_MODELS['gemini'],
                prompt=prompt,
                temperature=temperature,
                max_tokens=max_tokens,
            )

        elif provider == 'groq':
            return _call_openai_compatible(
                api_key=os.getenv('GROQ_API_KEY', ''),
                base_url='https://api.groq.com/openai/v1',
                model=PROVIDER_MODELS['groq'],
                prompt=prompt,
                temperature=temperature,
                max_tokens=max_tokens,
            )

        elif provider == 'openai':
            return _call_openai_compatible(
                api_key=os.getenv('OPENAI_API_KEY', ''),
                base_url='https://api.openai.com/v1',
                model=PROVIDER_MODELS['openai'],
                prompt=prompt,
                temperature=temperature,
                max_tokens=max_tokens,
            )

        else:
            raise ValueError(
                f"Unknown AI_PROVIDER: '{provider}'. Must be: gemini, groq, openai"
            )

    except Exception as e:
        err_str = str(e)

        # Per-minute rate limit
        if any(x in err_str.lower() for x in ['per minute', 'tpm', '413']):
            raise Exception(
                f"Rate limit (per-minute) hit on {provider.upper()}. "
                f"Wait 60 seconds and try again."
            )

        # Daily / quota exhausted
        if any(x in err_str.lower() for x in [
            'per day', 'quota exceeded', 'resource_exhausted',
            'limit: 0', 'exceeded your current quota'
        ]):
            match = re.search(r'retry in ([\d\.]+)s', err_str, re.IGNORECASE)
            wait = f" Retry in {match.group(1)}s." if match else ""
            raise Exception(
                f"Daily quota exhausted for {provider.upper()}.{wait} "
                f"Options: (1) Wait for quota reset, "
                f"(2) Create a fresh API key at aistudio.google.com, "
                f"(3) Set AI_PROVIDER=groq with a new GROQ_API_KEY from console.groq.com"
            )

        raise


# ── Helpers ────────────────────────────────────────────────────

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


def _clean_extracted_text(text: str) -> str:
    """Strip OCR noise: page numbers, duplicate lines, excessive whitespace."""
    text = re.sub(r'\r\n|\r', '\n', text)
    lines = text.split('\n')
    cleaned = []
    seen_lines = set()
    for line in lines:
        stripped = line.strip()
        if not stripped:
            cleaned.append('')
            continue
        if len(stripped) <= 2:
            continue
        if re.match(r'^\d+$', stripped):
            continue
        key = stripped.lower()
        if key in seen_lines:
            continue
        seen_lines.add(key)
        cleaned.append(stripped)
    text = '\n'.join(cleaned)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


# ── Prompts ────────────────────────────────────────────────────

def _questions_prompt(text: str, course_name: str, count: int) -> str:
    return f"""You are an expert Nigerian university lecturer creating a CBT exam for: "{course_name}".

The content may be from scanned documents or slides — formatting may be imperfect.
Generate exactly {count} multiple-choice questions from the educational concepts below.

REQUIREMENTS:
- Questions must come directly from the content
- Each question has exactly 4 options (A, B, C, D) — only ONE correct
- No duplicate questions
- Mix difficulty: easy, medium, hard
- Spread correct answers across A, B, C, D evenly
- One-sentence explanation per question

CONTENT:
{text}

Output ONLY a valid JSON array — no preamble, no markdown fences:
[
  {{
    "question": "Question text?",
    "option_a": "First",
    "option_b": "Second",
    "option_c": "Third",
    "option_d": "Fourth",
    "correct_answer": "A",
    "explanation": "Because..."
  }}
]"""


def _summary_prompt(text: str, course_name: str) -> str:
    return f"""You are an academic summariser creating study notes for: "{course_name}".

Content may be from scanned documents or slides — extract all key educational concepts.

CONTENT:
{text}

Return ONLY valid HTML — no markdown fences:
<div class="summary-content">
  <h2>Topic</h2>
  <p>Introduction...</p>
  <h3>Subtopic</h3>
  <ul>
    <li><strong>Key term</strong>: explanation</li>
  </ul>
</div>

Use h2 for major topics, h3 for subtopics, ul/li for lists, strong for key terms.
Cover ALL major concepts. No intro/outro sentences."""


# ── Public API ─────────────────────────────────────────────────

def generate_questions(text: str, course_name: str, api_key: str = '') -> Tuple[List[Dict], str]:
    """Generate MCQs from PDF text, split into chunks for large documents."""
    from utils.pdf_parser import split_into_chunks

    text = _clean_extracted_text(text)
    if len(text) < 200:
        return [], "Extracted text too short to generate questions."

    chunks = split_into_chunks(text)
    print(f"[AI] Questions: {len(chunks)} chunk(s), {len(text)} total chars")

    questions_per_chunk = max(20, 55 // len(chunks))
    all_questions: List[Dict] = []
    seen = set()

    for i, chunk in enumerate(chunks):
        print(f"[AI] Questions chunk {i+1}/{len(chunks)} ({len(chunk)} chars)...")
        prompt = _questions_prompt(chunk, course_name, count=questions_per_chunk)
        raw = _call_ai(prompt, temperature=0.6, max_tokens=6000)
        cleaned = _clean_json_response(raw)

        try:
            raw_list = json.loads(cleaned)
            chunk_qs = _validate_questions(raw_list)
        except json.JSONDecodeError as e:
            print(f"[AI] Chunk {i+1} JSON error: {e}")
            chunk_qs = []

        for q in chunk_qs:
            key = q['question'].lower()
            if key not in seen:
                seen.add(key)
                all_questions.append(q)

        print(f"[AI] Chunk {i+1}: {len(chunk_qs)} Qs. Total: {len(all_questions)}")

        if i < len(chunks) - 1:
            time.sleep(2)

    warning = ""
    if len(all_questions) < 40:
        warning = (
            f"Only {len(all_questions)} questions generated "
            f"(40 needed to publish). Upload a longer or clearer document."
        )
    return all_questions, warning


def generate_summary(text: str, course_name: str, api_key: str = '') -> str:
    """Generate structured HTML study notes from PDF text."""
    from utils.pdf_parser import split_into_chunks

    text = _clean_extracted_text(text)
    if len(text) < 200:
        return "<div class='summary-content'><p>Insufficient content to generate a summary.</p></div>"

    chunks = split_into_chunks(text)
    print(f"[AI] Summary: {len(chunks)} chunk(s)")

    if len(chunks) == 1:
        raw = _call_ai(_summary_prompt(chunks[0], course_name), temperature=0.4, max_tokens=4000)
        return _clean_html(raw)

    partials = []
    for i, chunk in enumerate(chunks):
        print(f"[AI] Summary chunk {i+1}/{len(chunks)}...")
        raw = _call_ai(_summary_prompt(chunk, course_name), temperature=0.4, max_tokens=3000)
        partials.append(_clean_html(raw))
        if i < len(chunks) - 1:
            time.sleep(2)

    combined = "\n\n".join(partials)
    merge_prompt = f"""Merge these partial HTML study notes for "{course_name}" into one clean document.
Remove duplicates. Return ONLY a single HTML block using h2, h3, p, ul, li, strong. No markdown.

{combined}"""

    try:
        print("[AI] Merging summary chunks...")
        time.sleep(2)
        raw = _call_ai(merge_prompt, temperature=0.3, max_tokens=4000)
        return _clean_html(raw)
    except Exception as e:
        print(f"[AI] Merge failed ({e}) — returning concatenated partials")
        return "\n".join(partials)


def get_active_provider() -> Dict:
    provider = _get_provider()
    return {
        'provider': provider,
        'model':    PROVIDER_MODELS.get(provider, 'unknown'),
        'free':     provider in ('gemini', 'groq'),
    }
