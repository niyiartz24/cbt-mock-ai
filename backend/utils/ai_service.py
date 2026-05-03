"""
CBT Mock AI — AI Service
Supports: groq (default/free), gemini (free), openai (paid)
Set AI_PROVIDER + the matching key in .env.
"""

import json
import re
import os
import time
from typing import List, Dict, Tuple

PROVIDER_MODELS = {
    'groq':   'llama-3.3-70b-versatile',
    'gemini': 'gemini-1.5-flash',
    'openai': 'gpt-4o-mini',
}


# ── Provider dispatch ──────────────────────────────────────────

def _get_provider() -> str:
    return os.getenv('AI_PROVIDER', 'groq').strip().lower()


def _get_openai_compatible_client(api_key: str, base_url: str, provider: str):
    try:
        from openai import OpenAI
    except ImportError:
        raise ImportError("Run: pip install openai")
    if not api_key:
        raise ValueError(f"{provider.upper()}_API_KEY is not set in your .env file.")
    return OpenAI(api_key=api_key, base_url=base_url)


def _call_openai_compatible(client, model: str, prompt: str, temperature: float, max_tokens: int) -> str:
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return response.choices[0].message.content


def _call_gemini(api_key: str, prompt: str, temperature: float, max_tokens: int) -> str:
    try:
        import google.generativeai as genai
    except ImportError:
        raise ImportError("Run: pip install google-generativeai")
    if not api_key:
        raise ValueError("GEMINI_API_KEY is not set in your .env file.")
    genai.configure(api_key=api_key)
    cfg = genai.types.GenerationConfig(temperature=temperature, max_output_tokens=max_tokens)
    model = genai.GenerativeModel(model_name=PROVIDER_MODELS['gemini'], generation_config=cfg)
    return model.generate_content(prompt).text


def _call_ai(prompt: str, temperature: float, max_tokens: int) -> str:
    provider = _get_provider()

    if provider == 'groq':
        client = _get_openai_compatible_client(
            os.getenv('GROQ_API_KEY', ''), 'https://api.groq.com/openai/v1', 'groq')
        return _call_openai_compatible(client, PROVIDER_MODELS['groq'], prompt, temperature, max_tokens)

    elif provider == 'gemini':
        return _call_gemini(os.getenv('GEMINI_API_KEY', ''), prompt, temperature, max_tokens)

    elif provider == 'openai':
        client = _get_openai_compatible_client(
            os.getenv('OPENAI_API_KEY', ''), 'https://api.openai.com/v1', 'openai')
        return _call_openai_compatible(client, PROVIDER_MODELS['openai'], prompt, temperature, max_tokens)

    else:
        raise ValueError(f"Unknown AI_PROVIDER: '{provider}'. Must be: groq, gemini, openai")


# ── Helpers ────────────────────────────────────────────────────

def _clean_json_response(raw: str) -> str:
    raw = raw.strip()
    raw = re.sub(r'^```json\s*', '', raw, flags=re.IGNORECASE)
    raw = re.sub(r'^```\s*', '', raw)
    raw = re.sub(r'\s*```$', '', raw)
    return raw.strip()


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


def _questions_prompt(text: str, course_name: str, count: int = 20) -> str:
    return f"""You are an expert Nigerian university lecturer creating a CBT for: "{course_name}".

Generate exactly {count} multiple-choice questions from the content below.

REQUIREMENTS:
- Every question must come directly from this content
- Each question has 4 options (A, B, C, D) — only ONE correct
- No duplicate questions
- Vary difficulty: easy / medium / hard
- Spread correct answers across A, B, C, D
- Include a one-sentence explanation per question
- Clear, unambiguous wording

CONTENT:
{text}

Output ONLY a valid JSON array — no preamble, no markdown:
[
  {{
    "question": "Question text?",
    "option_a": "First option",
    "option_b": "Second option",
    "option_c": "Third option",
    "option_d": "Fourth option",
    "correct_answer": "A",
    "explanation": "Because..."
  }}
]"""


def _summary_prompt(text: str, course_name: str) -> str:
    return f"""You are an expert academic summariser creating study notes for: "{course_name}".

CONTENT:
{text}

Return ONLY valid HTML — no explanation, no markdown fences:
<div class="summary-content">
  <h2>Topic</h2>
  <p>Introduction...</p>
  <h3>Subtopic</h3>
  <ul>
    <li><strong>Key term</strong>: explanation</li>
  </ul>
</div>

Rules: h2 for major topics, h3 for subtopics, ul/li for bullets, strong for key terms.
Cover ALL major concepts. Do not add an intro sentence about this being a summary."""


# ── Public API ─────────────────────────────────────────────────

def generate_questions(text: str, course_name: str, api_key: str = '') -> Tuple[List[Dict], str]:
    """
    Generate MCQ questions from PDF text.
    Automatically splits large texts into chunks to stay within provider TPM limits.
    Returns (questions_list, warning_message).
    """
    from utils.pdf_parser import split_into_chunks

    chunks = split_into_chunks(text)
    print(f"[AI] Generating questions from {len(chunks)} chunk(s) of text")

    # Questions per chunk — aim for ~20 per chunk so combined = 50-60
    questions_per_chunk = max(20, 55 // len(chunks))

    all_questions: List[Dict] = []
    seen_questions = set()

    for i, chunk in enumerate(chunks):
        print(f"[AI] Processing chunk {i+1}/{len(chunks)} ({len(chunk)} chars)...")

        prompt = _questions_prompt(chunk, course_name, count=questions_per_chunk)
        try:
            raw = _call_ai(prompt, temperature=0.6, max_tokens=6000)
        except Exception as e:
            print(f"[AI] Chunk {i+1} failed: {e}")
            # Don't fail the whole job if one chunk errors — continue
            continue

        cleaned = _clean_json_response(raw)
        try:
            raw_list = json.loads(cleaned)
            chunk_questions = _validate_questions(raw_list)
        except json.JSONDecodeError as e:
            print(f"[AI] Chunk {i+1} JSON parse error: {e}")
            continue

        # Cross-chunk deduplication
        for q in chunk_questions:
            key = q['question'].lower()
            if key not in seen_questions:
                seen_questions.add(key)
                all_questions.append(q)

        print(f"[AI] Chunk {i+1}: {len(chunk_questions)} questions generated, "
              f"{len(all_questions)} total so far")

        # Small delay between chunks to respect rate limits
        if i < len(chunks) - 1:
            time.sleep(2)

    warning = ""
    if len(all_questions) < 40:
        warning = (
            f"Only {len(all_questions)} valid questions were generated "
            f"(minimum 40 needed to publish). Upload richer content for better results."
        )

    return all_questions, warning


def generate_summary(text: str, course_name: str, api_key: str = '') -> str:
    """
    Generate a structured HTML summary.
    For large texts, summarises each chunk then merges into one final summary.
    """
    from utils.pdf_parser import split_into_chunks

    chunks = split_into_chunks(text)
    print(f"[AI] Generating summary from {len(chunks)} chunk(s)")

    if len(chunks) == 1:
        # Simple path — single call
        prompt = _summary_prompt(chunks[0], course_name)
        raw = _call_ai(prompt, temperature=0.4, max_tokens=4000)
        return _clean_html(raw)

    # Multi-chunk: summarise each chunk, then merge
    partial_summaries = []
    for i, chunk in enumerate(chunks):
        print(f"[AI] Summarising chunk {i+1}/{len(chunks)}...")
        prompt = _summary_prompt(chunk, course_name)
        try:
            raw = _call_ai(prompt, temperature=0.4, max_tokens=3000)
            partial_summaries.append(_clean_html(raw))
        except Exception as e:
            print(f"[AI] Summary chunk {i+1} failed: {e}")

        if i < len(chunks) - 1:
            time.sleep(2)

    if not partial_summaries:
        raise ValueError("Summary generation failed for all chunks.")

    if len(partial_summaries) == 1:
        return partial_summaries[0]

    # Merge partial summaries into one clean document
    combined = "\n\n".join(partial_summaries)
    merge_prompt = f"""You are an academic editor. Merge these partial HTML study note sections for "{course_name}" into one clean, non-repetitive HTML document.

{combined}

Return ONLY a single merged HTML block using h2, h3, p, ul, li, strong — no duplicates, no markdown fences."""

    try:
        print("[AI] Merging partial summaries...")
        time.sleep(2)
        raw = _call_ai(merge_prompt, temperature=0.3, max_tokens=4000)
        return _clean_html(raw)
    except Exception:
        # If merge fails, just concatenate the partials
        return "\n".join(partial_summaries)


def _clean_html(raw: str) -> str:
    content = raw.strip()
    content = re.sub(r'^```html\s*', '', content, flags=re.IGNORECASE)
    content = re.sub(r'\s*```$', '', content)
    return content.strip()


def get_active_provider() -> Dict:
    provider = _get_provider()
    return {
        'provider': provider,
        'model':    PROVIDER_MODELS.get(provider, 'unknown'),
        'free':     provider in ('groq', 'gemini'),
    }
