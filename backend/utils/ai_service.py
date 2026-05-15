import json
import re
import os
import time
from typing import List, Dict, Tuple

PROVIDER_MODELS = {
    'gemini': 'gemini-2.5-flash',
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
    provider = _get_provider()
    try:
        if provider == 'gemini':
            api_key = os.getenv('GEMINI_API_KEY', '')
            if not api_key:
                raise ValueError("GEMINI_API_KEY is not set. Get a free key at: https://aistudio.google.com")
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
            raise ValueError(f"Unknown AI_PROVIDER: '{provider}'. Must be: gemini, groq, openai")

    except Exception as e:
        err_str = str(e)
        if any(x in err_str.lower() for x in ['per minute', 'tpm', '413']):
            raise Exception(f"Rate limit (per-minute) hit on {provider.upper()}. Wait 60s and retry.")
        if any(x in err_str.lower() for x in ['per day', 'quota exceeded', 'resource_exhausted', 'limit: 0', 'exceeded your current quota']):
            match = re.search(r'retry in ([\d\.]+)s', err_str, re.IGNORECASE)
            wait = f" Retry in {match.group(1)}s." if match else ""
            raise Exception(
                f"Daily quota exhausted for {provider.upper()}.{wait} "
                f"Options: (1) Wait for reset, (2) New API key from aistudio.google.com, "
                f"(3) Set AI_PROVIDER=groq with a new GROQ_API_KEY from console.groq.com"
            )
        raise


# ── JSON extraction ────────────────────────────────────────────

def _extract_json_array(raw: str) -> list:
    """
    Robustly extract a JSON array from AI response.
    Handles: markdown fences, thinking tags, preamble, truncated responses.
    If response is cut off mid-array, salvages all complete objects.
    """
    if not raw:
        raise ValueError("AI returned empty response")

    print(f"[AI] Raw response length: {len(raw)} chars")
    print(f"[AI] Raw response preview: {raw[:200]}")

    # Step 1: Strip thinking blocks
    text = re.sub(r'<think>.*?</think>', '', raw, flags=re.DOTALL | re.IGNORECASE)

    # Step 2: Strip markdown fences
    text = re.sub(r'```json\s*', '', text, flags=re.IGNORECASE)
    text = re.sub(r'```\s*', '', text)
    text = text.strip()

    # Step 3: Find the start of the JSON array
    start = text.find('[')
    if start == -1:
        raise ValueError(f"No JSON array found. Preview: {text[:300]}")

    array_text = text[start:]

    # Step 4: Try parsing the full array
    clean = re.sub(r',\s*([}\]])', r'\1', array_text)
    try:
        result = json.loads(clean)
        if isinstance(result, list):
            print(f"[AI] JSON parsed fully: {len(result)} items")
            return result
    except json.JSONDecodeError:
        pass

    # Step 5: Response was truncated — salvage complete objects
    # Extract every complete {...} object from the array
    print(f"[AI] Response truncated — salvaging complete objects...")
    objects = []
    depth = 0
    in_string = False
    escape_next = False
    obj_start = -1

    for i, ch in enumerate(array_text):
        if escape_next:
            escape_next = False
            continue
        if ch == '\\' and in_string:
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue

        if ch == '{':
            if depth == 0:
                obj_start = i
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0 and obj_start != -1:
                obj_str = array_text[obj_start:i+1]
                obj_str = re.sub(r',\s*}', '}', obj_str)
                try:
                    obj = json.loads(obj_str)
                    if isinstance(obj, dict):
                        objects.append(obj)
                except json.JSONDecodeError:
                    pass
                obj_start = -1

    if objects:
        print(f"[AI] Salvaged {len(objects)} complete objects from truncated response")
        return objects

    raise ValueError(f"Could not extract any valid objects. Preview: {array_text[:300]}")


def _clean_html(raw: str) -> str:
    content = raw.strip()
    # Strip thinking blocks
    content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL | re.IGNORECASE)
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
    return f"""You are a Nigerian university lecturer generating CBT exam questions for: "{course_name}".

Read the content carefully and generate exactly {count} multiple-choice questions.

STRICT RULES:
- Base every question on the content provided
- Each question has exactly 4 options: A, B, C, D — only ONE is correct
- No duplicate questions
- Mix difficulty: easy, medium, hard
- Distribute correct answers evenly across A, B, C, D
- One short explanation per question

CONTENT:
{text}

YOU MUST RESPOND WITH ONLY A JSON ARRAY. NO INTRODUCTION. NO EXPLANATION. NO MARKDOWN. JUST THE RAW JSON ARRAY STARTING WITH [ AND ENDING WITH ]:

[
  {{
    "question": "Question text here?",
    "option_a": "First option",
    "option_b": "Second option",
    "option_c": "Third option",
    "option_d": "Fourth option",
    "correct_answer": "A",
    "explanation": "Short reason."
  }}
]"""


def _summary_prompt(text: str, course_name: str) -> str:
    return f"""You are an academic summariser creating study notes for: "{course_name}".

Read the content and produce structured study notes.

CONTENT:
{text}

Respond with ONLY valid HTML using these tags: h2, h3, p, ul, li, strong.
No markdown. No explanation. Start directly with <div class="summary-content">:

<div class="summary-content">
  <h2>Topic</h2>
  <p>Introduction...</p>
  <h3>Subtopic</h3>
  <ul>
    <li><strong>Key term</strong>: explanation</li>
  </ul>
</div>"""


# ── Public API ─────────────────────────────────────────────────

def generate_questions(text: str, course_name: str, api_key: str = '') -> Tuple[List[Dict], str]:
    from utils.pdf_parser import split_into_chunks

    text = _clean_extracted_text(text)
    if len(text) < 200:
        return [], "Extracted text too short to generate questions."

    chunks = split_into_chunks(text)
    print(f"[AI] Generating questions: {len(chunks)} chunk(s), {len(text)} total chars")

    questions_per_chunk = max(20, 55 // len(chunks))
    all_questions: List[Dict] = []
    seen = set()

    for i, chunk in enumerate(chunks):
        print(f"[AI] Questions chunk {i+1}/{len(chunks)} ({len(chunk)} chars)...")
        prompt = _questions_prompt(chunk, course_name, count=questions_per_chunk)

        try:
            raw = _call_ai(prompt, temperature=0.6, max_tokens=16000)
            raw_list = _extract_json_array(raw)
            chunk_qs = _validate_questions(raw_list)
        except Exception as e:
            print(f"[AI] Chunk {i+1} failed: {type(e).__name__}: {e}")
            raise

        for q in chunk_qs:
            key = q['question'].lower()
            if key not in seen:
                seen.add(key)
                all_questions.append(q)

        print(f"[AI] Chunk {i+1} done: {len(chunk_qs)} valid questions. Total: {len(all_questions)}")

        if i < len(chunks) - 1:
            time.sleep(2)

    warning = ""
    if len(all_questions) < 40:
        warning = (
            f"Only {len(all_questions)} questions generated "
            f"(40 needed to publish). Upload a longer document."
        )
    return all_questions, warning


def generate_summary(text: str, course_name: str, api_key: str = '') -> str:
    from utils.pdf_parser import split_into_chunks

    text = _clean_extracted_text(text)
    if len(text) < 200:
        return "<div class='summary-content'><p>Insufficient content to generate a summary.</p></div>"

    chunks = split_into_chunks(text)
    print(f"[AI] Generating summary: {len(chunks)} chunk(s)")

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
Remove duplicates. Return ONLY a single HTML block. No markdown. No explanation.

{combined}"""

    try:
        print("[AI] Merging summary chunks...")
        time.sleep(2)
        raw = _call_ai(merge_prompt, temperature=0.3, max_tokens=4000)
        return _clean_html(raw)
    except Exception as e:
        print(f"[AI] Merge failed ({e}) — returning concatenated")
        return "\n".join(partials)


def get_active_provider() -> Dict:
    provider = _get_provider()
    return {
        'provider': provider,
        'model':    PROVIDER_MODELS.get(provider, 'unknown'),
        'free':     provider in ('gemini', 'groq'),
    }
