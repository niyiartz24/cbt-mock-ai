"""
CBT Mock AI — AI Service
Supports three providers, selected via the AI_PROVIDER env variable:

  AI_PROVIDER=groq    (default) — Free. Fast. Uses Llama 3.3 70B.
                                   Get key: https://console.groq.com
  AI_PROVIDER=gemini             — Free tier. Uses Gemini 1.5 Flash.
                                   Get key: https://aistudio.google.com
  AI_PROVIDER=openai             — Paid. Uses GPT-4o-mini.
                                   Get key: https://platform.openai.com

Set the corresponding key in your .env:
  GROQ_API_KEY=gsk_...
  GEMINI_API_KEY=AIza...
  OPENAI_API_KEY=sk-...
"""

import json
import re
import os
from typing import List, Dict, Tuple

PROVIDER_MODELS = {
    'groq':   'llama-3.3-70b-versatile',
    'gemini': 'gemini-1.5-flash',
    'openai': 'gpt-4o-mini',
}


def _get_provider() -> str:
    return os.getenv('AI_PROVIDER', 'groq').strip().lower()


def _get_openai_compatible_client(api_key: str, base_url: str, provider: str):
    try:
        from openai import OpenAI
    except ImportError:
        raise ImportError(
            "The 'openai' package is required for Groq and OpenAI providers.\n"
            "Run: pip install openai"
        )
    if not api_key:
        raise ValueError(
            f"{provider.upper()}_API_KEY is not set. Add it to your .env file."
        )
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
        raise ImportError(
            "The 'google-generativeai' package is required for Gemini.\n"
            "Run: pip install google-generativeai"
        )
    if not api_key:
        raise ValueError(
            "GEMINI_API_KEY is not set. Add it to your .env file.\n"
            "Get a free key at: https://aistudio.google.com"
        )
    genai.configure(api_key=api_key)
    generation_config = genai.types.GenerationConfig(
        temperature=temperature,
        max_output_tokens=max_tokens,
    )
    model = genai.GenerativeModel(
        model_name=PROVIDER_MODELS['gemini'],
        generation_config=generation_config,
    )
    response = model.generate_content(prompt)
    return response.text


def _call_ai(prompt: str, temperature: float, max_tokens: int) -> str:
    provider = _get_provider()

    if provider == 'groq':
        client = _get_openai_compatible_client(
            api_key=os.getenv('GROQ_API_KEY', ''),
            base_url='https://api.groq.com/openai/v1',
            provider='groq',
        )
        return _call_openai_compatible(client, PROVIDER_MODELS['groq'], prompt, temperature, max_tokens)

    elif provider == 'gemini':
        return _call_gemini(
            api_key=os.getenv('GEMINI_API_KEY', ''),
            prompt=prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    elif provider == 'openai':
        client = _get_openai_compatible_client(
            api_key=os.getenv('OPENAI_API_KEY', ''),
            base_url='https://api.openai.com/v1',
            provider='openai',
        )
        return _call_openai_compatible(client, PROVIDER_MODELS['openai'], prompt, temperature, max_tokens)

    else:
        raise ValueError(
            f"Unknown AI_PROVIDER: '{provider}'. Must be one of: groq, gemini, openai"
        )


def _clean_json_response(raw: str) -> str:
    raw = raw.strip()
    raw = re.sub(r'^```json\s*', '', raw, flags=re.IGNORECASE)
    raw = re.sub(r'^```\s*', '', raw)
    raw = re.sub(r'\s*```$', '', raw)
    return raw.strip()


def _validate_questions(raw_list: list) -> List[Dict]:
    required_keys = {'question', 'option_a', 'option_b', 'option_c', 'option_d', 'correct_answer'}
    valid_answers = {'A', 'B', 'C', 'D'}
    validated = []
    seen_questions = set()

    for item in raw_list:
        if not isinstance(item, dict):
            continue
        if not required_keys.issubset(item.keys()):
            continue
        q_text = str(item['question']).strip()
        answer = str(item.get('correct_answer', '')).strip().upper()
        if not q_text or len(q_text) < 10:
            continue
        if answer not in valid_answers:
            continue
        if q_text.lower() in seen_questions:
            continue
        seen_questions.add(q_text.lower())
        validated.append({
            'question': q_text,
            'option_a': str(item['option_a']).strip(),
            'option_b': str(item['option_b']).strip(),
            'option_c': str(item['option_c']).strip(),
            'option_d': str(item['option_d']).strip(),
            'correct_answer': answer,
            'explanation': str(item.get('explanation', '')).strip(),
        })

    return validated


def generate_questions(text: str, course_name: str, api_key: str = '') -> Tuple[List[Dict], str]:
    """
    Generate MCQ questions from extracted PDF text.
    Returns (questions_list, warning_message).
    api_key param kept for backwards compatibility — provider/key come from env.
    """
    prompt = f"""You are an expert Nigerian university lecturer creating a Computer-Based Test (CBT) for the course: "{course_name}".

Study the following lesson content carefully, then generate exactly 55 multiple-choice questions.

STRICT REQUIREMENTS:
1. Every question must be clearly derived from the provided content
2. Each question has exactly 4 options (A, B, C, D) — only ONE is correct
3. No duplicate or near-duplicate questions
4. Vary difficulty: 30% easy, 50% medium, 20% hard
5. Correct answers must be distributed fairly across A, B, C, D
6. Include a brief explanation for each correct answer
7. Questions must be clearly worded with no ambiguity

LESSON CONTENT:
{text}

RESPONSE FORMAT — Output ONLY a valid JSON array, no preamble, no markdown fences:
[
  {{
    "question": "The full question text goes here?",
    "option_a": "First option",
    "option_b": "Second option",
    "option_c": "Third option",
    "option_d": "Fourth option",
    "correct_answer": "A",
    "explanation": "Option A is correct because..."
  }}
]"""

    raw = _call_ai(prompt, temperature=0.6, max_tokens=10000)
    cleaned = _clean_json_response(raw)

    warning = ""
    try:
        raw_list = json.loads(cleaned)
        questions = _validate_questions(raw_list)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"AI returned malformed JSON: {e}. "
            f"Raw response (first 500 chars): {cleaned[:500]}"
        )

    if len(questions) < 40:
        warning = (
            f"Only {len(questions)} valid questions were generated "
            f"(minimum 40 required to publish). "
            "Consider uploading richer content."
        )

    return questions, warning


def generate_summary(text: str, course_name: str, api_key: str = '') -> str:
    """
    Generate a structured HTML summary from extracted PDF text.
    Returns HTML string.
    api_key param kept for backwards compatibility — provider/key come from env.
    """
    prompt = f"""You are an expert academic summariser creating structured study notes for the course: "{course_name}".

Analyse the following lesson content and produce comprehensive, well-organised study notes that a student can use for revision.

LESSON CONTENT:
{text}

OUTPUT FORMAT — Return ONLY valid HTML, no explanation, no markdown:
<div class="summary-content">
  <h2>Topic Name</h2>
  <p>Brief introduction...</p>
  <h3>Subtopic</h3>
  <ul>
    <li><strong>Key term</strong>: Definition or explanation</li>
  </ul>
</div>

RULES:
- Use <h2> for major topics, <h3> for subtopics
- Use <ul><li> for bullet points and lists
- Bold key terms with <strong>
- Use <p> for explanatory paragraphs
- Cover ALL major concepts from the content
- Be comprehensive but avoid unnecessary repetition
- Do NOT include an introduction or conclusion about this being a summary"""

    raw = _call_ai(prompt, temperature=0.4, max_tokens=4000)
    content = raw.strip()
    content = re.sub(r'^```html\s*', '', content, flags=re.IGNORECASE)
    content = re.sub(r'\s*```$', '', content)
    return content.strip()


def get_active_provider() -> Dict:
    """Return info about the currently configured AI provider."""
    provider = _get_provider()
    return {
        'provider': provider,
        'model': PROVIDER_MODELS.get(provider, 'unknown'),
        'free': provider in ('groq', 'gemini'),
    }
