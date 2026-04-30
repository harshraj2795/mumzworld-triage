"""
Mumzworld AI Email Triage System
Classifies incoming customer service emails into structured output
with bilingual (EN/AR) suggested replies and uncertainty handling.
"""

import os
import json
from dotenv import load_dotenv
load_dotenv()
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, ValidationError
from typing import Optional
import httpx

app = FastAPI(title="Mumzworld Email Triage")
app.mount("/static", StaticFiles(directory="static"), name="static")

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_URL = "https://api.mistral.ai/v1/chat/completions"
MODEL = "mistral-small-latest"

# ── Pydantic schema ──────────────────────────────────────────────────────────

class TriageResult(BaseModel):
    intent: str                        # return_request | order_issue | product_query | complaint | spam | other
    urgency: str                       # high | medium | low
    confidence: float                  # 0.0 – 1.0
    escalate: bool                     # True if human must review
    reasoning: str                     # Why this classification
    suggested_reply_en: Optional[str]  # English reply (null if spam/uncertain)
    suggested_reply_ar: Optional[str]  # Arabic reply (null if spam/uncertain)
    uncertainty_note: Optional[str]    # Filled when confidence < 0.7


# ── System prompt ────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are an AI triage assistant for Mumzworld, the largest mother-and-baby e-commerce platform in the Middle East.
Your job is to classify incoming customer service emails and draft bilingual replies.

You MUST respond with ONLY a valid JSON object — no markdown fences, no preamble, no extra text.

Schema:
{
  "intent": one of ["return_request", "order_issue", "product_query", "complaint", "spam", "other"],
  "urgency": one of ["high", "medium", "low"],
  "confidence": float between 0.0 and 1.0,
  "escalate": boolean (true if angry, legal threat, media mention, or safety concern),
  "reasoning": "1-2 sentences explaining your classification",
  "suggested_reply_en": "A warm, professional reply in English. Use the customer's name if present. null if spam or confidence < 0.5",
  "suggested_reply_ar": "نفس الرد باللغة العربية الفصحى المناسبة. يجب أن تكون الترجمة طبيعية وليست حرفية. null إذا كانت البريد مزعج أو الثقة أقل من 0.5",
  "uncertainty_note": "Explain what is unclear if confidence < 0.7, otherwise null"
}

Rules:
- If the email is gibberish, clearly spam, or cannot be meaningfully triaged, set confidence ≤ 0.3 and escalate: false, replies: null
- If safety of a child is mentioned (allergic reaction, injury), set urgency: "high" and escalate: true
- Arabic replies must be natural Gulf-dialect-friendly Modern Standard Arabic — NOT a word-for-word translation
- Never invent order numbers, dates, or product names not present in the email
- Be honest: if you cannot determine intent, say so in uncertainty_note
"""


# ── Triage endpoint ──────────────────────────────────────────────────────────

@app.post("/triage")
async def triage_email(payload: dict):
    email_text = payload.get("email", "").strip()
    if not email_text:
        raise HTTPException(status_code=400, detail="Email text is required")

    if not OPENROUTER_API_KEY:
        raise HTTPException(status_code=500, detail="OPENROUTER_API_KEY not set")

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Triage this customer email:\n\n{email_text}"}
    ]

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            OPENROUTER_URL,
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": MODEL,
                "messages": messages,
                "temperature": 0.2,   # Low temp = more consistent structured output
                "max_tokens": 1000
            }
        )

    if response.status_code != 200:
        raise HTTPException(status_code=502, detail=f"Model API error: {response.text}")

    raw_content = response.json()["choices"][0]["message"]["content"].strip()

    # Strip markdown fences if model wraps JSON anyway
    if raw_content.startswith("```"):
        raw_content = raw_content.split("```")[1]
        if raw_content.startswith("json"):
            raw_content = raw_content[4:]

    # Parse and validate against schema — failures are explicit, never silent
    try:
        parsed = json.loads(raw_content)
        result = TriageResult(**parsed)
    except (json.JSONDecodeError, ValidationError) as e:
        raise HTTPException(
            status_code=422,
            detail=f"Model returned invalid structure: {str(e)}\nRaw: {raw_content[:300]}"
        )

    return result.model_dump()


@app.get("/")
async def root():
    return FileResponse("static/index.html")