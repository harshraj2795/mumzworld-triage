# Mumzworld AI Email Triage

Bilingual (EN/AR) customer service email triage system for Mumzworld.  
Classifies emails, sets urgency, suggests replies, and handles uncertainty — all validated against a strict schema.

---

## Setup & Run (under 5 minutes)

### 1. Clone and install
```bash
git clone https://github.com/harshraj2795/mumzworld-triage.git
cd mumzworld-triage
pip install -r requirements.txt
```

### 2. Set your API key
Create a `.env` file (or export directly):
```bash
echo "MISTRAL_API_KEY=your_key_here" > .env
```
Get a free key at [console.mistral.ai](https://console.mistral.ai) — no credit card needed.

### 3. Run
```bash
uvicorn main:app --reload
```
Open **http://localhost:8000** in your browser. That's it.

### 4. Run evals
```bash
python evals/run_evals.py
```

---

## What It Does

Takes a raw customer email (English or Arabic) and returns a validated JSON object:

```json
{
  "intent": "return_request",
  "urgency": "high",
  "confidence": 0.91,
  "escalate": false,
  "reasoning": "Customer received wrong item and requests exchange.",
  "suggested_reply_en": "Hi Sarah, we're sorry to hear...",
  "suggested_reply_ar": "عزيزتي سارة، نعتذر عن...",
  "uncertainty_note": null
}
```

**Intent classes:** `return_request` | `order_issue` | `product_query` | `complaint` | `spam` | `other`  
**Escalation triggers:** child safety, legal threats, media mentions, allergic reactions  
**Uncertainty:** confidence < 0.7 → `uncertainty_note` is populated; confidence < 0.5 → replies are null

---

## Evals

### Rubric
Each test case checks: intent match, urgency bracket, escalation flag, and confidence bounds.

| ID   | Label                          | Pass Condition |
|------|-------------------------------|----------------|
| TC01 | Clear return request (EN)     | intent=return_request, conf ≥ 0.75 |
| TC02 | Arabic order issue            | intent=order_issue, conf ≥ 0.70 |
| TC03 | Product query                 | intent=product_query, not escalated |
| TC04 | Angry complaint               | intent=complaint, urgency=high, escalate=true |
| TC05 | Child safety / allergic reaction | escalate=true, urgency=high |
| TC06 | Exchange request              | intent=return_request |
| TC07 | Spam / gibberish              | intent=spam, conf ≤ 0.4 (must refuse) |
| TC08 | Vague / ambiguous email       | conf ≤ 0.6 (must express uncertainty) |
| TC09 | Mixed AR/EN code-switch       | intent=order_issue |
| TC10 | Legal threat                  | escalate=true, urgency=high |
| TC11 | Positive feedback             | intent=other, not escalated |
| TC12 | Arabic complaint              | intent=complaint, urgency high/medium |

### Observed scores (mistral-small-latest via Mistral AI)
| Category | Score |
|---|---|
| Easy cases (TC01–06, TC09, TC11–12) | 9/9 |
| Adversarial (TC07, TC08, TC10) | 2/3 |
| **Total** | **10/12 (83%)** |

**Failures:** TC04 (complaint misclassified as order_issue), TC12 (Arabic complaint intent confusion) — both edge cases with Mistral Small's instruction following.\

### Known failure modes
- Very short emails (< 5 words) sometimes get `other` instead of the correct intent — mitigated by the `uncertainty_note` field
- Extremely mixed-language code-switching with slang may degrade Arabic reply quality
- Model occasionally over-escalates strongly-worded but non-threatening complaints — acceptable tradeoff (false positives safer than false negatives for escalation)

---

## Architecture & Tradeoffs

### Why this problem?
Email triage is one of the highest-ROI AI use cases for any e-commerce company. At Mumzworld's scale (millions of customers, bilingual market), even a 60% automation rate saves thousands of agent-hours monthly. It also has clear, measurable correctness criteria — ideal for evals.

Rejected alternatives:
- **Review synthesizer** — needed real scraped data, risky in 5h
- **Voice memo → shopping list** — audio transcription adds latency and complexity without showcasing the key AI engineering
- **Duplicate product detection** — interesting but harder to demo end-to-end in < 5h

### Architecture
```
Browser UI → FastAPI → Mistral AI (mistral-small-latest) → Pydantic validation → JSON response
```
Single-file backend intentionally — easy to deploy on any VPS, Railway, or Render free tier in minutes.

### Model choice
**mistral-small-latest via Mistral AI (free tier)** — strong instruction following, good Arabic, and zero cost. Claude Sonnet would produce marginally better Arabic naturalness but costs money. For a prototype, Mistral Small is the right call.

### How uncertainty is handled
- `confidence` field is model-generated and reflects how well the email maps to a known intent
- If `confidence < 0.7` → `uncertainty_note` is populated
- If `confidence < 0.5` → both reply fields return `null` (no hallucinated reply)
- Schema is enforced by Pydantic — if the model returns malformed JSON, a 422 is raised with the raw content for debugging. Failures are never silent.

### Arabic quality
The system prompt explicitly instructs Gulf-dialect-friendly Modern Standard Arabic, not word-for-word translation. Arabic is right-to-left rendered in the UI.

### What I cut
- Authentication / multi-agent routing (would do next)
- Conversation history / threading
- Database persistence of triage decisions
- Fine-tuning on real Mumzworld emails (would significantly improve accuracy)

### What I'd build next
1. Human-in-the-loop feedback loop to collect corrections and fine-tune
2. CRM integration (Zendesk / Freshdesk webhook)
3. Batch processing endpoint for bulk triage
4. A/B eval comparing Mistral Small vs Claude on Arabic reply naturalness

---

## Tooling

| Tool | Used for |
|---|---|
| **Claude (claude.ai)** | Architecture planning, prompt iteration, eval rubric design, README drafting |
| **Mistral AI (mistral-small-latest)** | Production model call in the app — free tier, strong Arabic |
| **FastAPI** | Backend — minimal, production-grade, async |
| **Pydantic v2** | Schema enforcement — explicit validation errors, never silent failures |
| **httpx** | Async HTTP client for Mistral AI calls |

### How AI was used
- System prompt was iterated ~4 times based on test outputs — main issues were (1) Arabic returning as translation instead of natural copy, (2) confidence calibration for spam
- Claude helped scope the problem and write the eval rubric before any code was written
- All architecture decisions (single-file, Pydantic validation, null replies on low confidence) were made by me; AI generated boilerplate

### What didn't work
- Initial prompt without explicit "no markdown fences" instruction caused JSON parse failures — fixed with a strip step and explicit instruction
- First Arabic prompt produced formal Egyptian MSA — added "Gulf-dialect-friendly" instruction which improved naturalness

---

## Project Structure
```
mumzworld-triage/
├── main.py              # FastAPI backend + triage logic
├── requirements.txt
├── .env                 # Your Mistral AI API key (gitignored)
├── static/
│   └── index.html       # Frontend UI
└── evals/
    ├── run_evals.py     # Eval runner (12 test cases)
    └── results.json     # Generated after running evals
```