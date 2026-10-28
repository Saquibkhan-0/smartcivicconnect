import os
import json
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

CATEGORIES = {"pothole", "garbage", "streetlight", "water_leak", "drainage", "other"}

PROMPT = """
You are an AI civic infrastructure assistant. Analyze this citizen report
(it may include text, an image, and/or a voice note in any language).

Tasks:
1. Categorize into ONE of: "pothole", "garbage", "streetlight", "water_leak", "drainage", "other".
2. description_original: the citizen's words as given (if audio only, transcribe it).
   description_english: a clear English translation/normalisation.
3. severity: integer 1 (minor nuisance) to 10 (life-threatening hazard).
4. estimated_cost: numeric municipal repair cost in INR-equivalent units
   (e.g. 150.0 minor, 1200.0 major).
5. estimated_hours: numeric labour hours (e.g. 2.5).

Return ONLY valid JSON with exactly these keys:
{"category": str, "description_original": str, "description_english": str,
 "severity": int, "estimated_cost": float, "estimated_hours": float}
"""


def _fallback(text):
    text = text or ""
    return {
        "category": "other",
        "description_original": text,
        "description_english": text,
        "severity": 5,
        "estimated_cost": 100.0,
        "estimated_hours": 2.0,
    }


def _clean(result, text):
    cat = str(result.get("category", "other")).strip().lower()
    if cat not in CATEGORIES:
        cat = "other"
    sev = max(1, min(10, int(result.get("severity", 5))))
    return {
        "category": cat,
        "description_original": result.get("description_original") or text or "",
        "description_english": result.get("description_english") or text or "",
        "severity": sev,
        "estimated_cost": float(result.get("estimated_cost", 100.0)),
        "estimated_hours": float(result.get("estimated_hours", 2.0)),
    }


def _call(contents):
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=contents,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.2,
        ),
    )
    return json.loads(response.text)


def analyse_report(text=None, image_bytes=None, image_mime=None,
                   audio_bytes=None, audio_mime=None, language="en"):
    base = [PROMPT, f"Language selected by the citizen: {language}"]
    if text:
        base.append(f"Citizen description: {text}")

    full = list(base)
    if image_bytes and image_mime:
        full.append(types.Part.from_bytes(data=image_bytes, mime_type=image_mime))
    if audio_bytes and audio_mime:
        full.append(types.Part.from_bytes(data=audio_bytes, mime_type=audio_mime))

    # Try everything; if the audio format is rejected, retry without audio.
    attempts = [full]
    if audio_bytes:
        no_audio = list(base)
        if image_bytes and image_mime:
            no_audio.append(types.Part.from_bytes(data=image_bytes, mime_type=image_mime))
        attempts.append(no_audio)

    for contents in attempts:
        try:
            return _clean(_call(contents), text)
        except Exception as e:
            print("AI error:", repr(e))

    return _fallback(text)