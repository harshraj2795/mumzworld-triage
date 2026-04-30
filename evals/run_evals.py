"""
Evaluation suite for Mumzworld Email Triage.
Runs 12 test cases (easy + adversarial) and prints a score report.

Usage:
    python evals/run_evals.py
"""

import asyncio
import httpx
import json

BASE_URL = "http://localhost:8000/triage"

# ── Test cases ────────────────────────────────────────────────────────────────
# Each case: input email, expected_intent, expected_urgency, must_escalate, max_confidence_if_uncertain
TEST_CASES = [
    # ── Easy / clear cases ────────────────────────────────────────────────
    {
        "id": "TC01",
        "label": "Clear return request (EN)",
        "email": "Hi, I received order #MW-88123 but the stroller I got is the wrong color. I want to return it and get the correct one. Please advise.",
        "expect_intent": "return_request",
        "expect_urgency_in": ["high", "medium"],
        "must_escalate": False,
        "min_confidence": 0.75
    },
    {
        "id": "TC02",
        "label": "Arabic order issue",
        "email": "مرحبا، لم يصلني طلبي رقم ٥٥٩٩١ منذ أسبوعين. هل يمكنكم التحقق من الأمر؟ شكرا",
        "expect_intent": "order_issue",
        "expect_urgency_in": ["high", "medium"],
        "must_escalate": False,
        "min_confidence": 0.70
    },
    {
        "id": "TC03",
        "label": "Product query (EN)",
        "email": "Hello, I would like to know if the Chicco stroller is suitable for newborns under 3kg. My baby was born premature.",
        "expect_intent": "product_query",
        "expect_urgency_in": ["medium", "low"],
        "must_escalate": False,
        "min_confidence": 0.75
    },
    {
        "id": "TC04",
        "label": "Complaint with anger (EN)",
        "email": "This is absolutely unacceptable. I've been waiting 3 weeks for a baby crib and nobody responds to my calls. I'm posting this on social media if it's not resolved TODAY.",
        "expect_intent": "complaint",
        "expect_urgency_in": ["high"],
        "must_escalate": True,
        "min_confidence": 0.80
    },
    {
        "id": "TC05",
        "label": "Safety escalation — allergic reaction",
        "email": "My son had an allergic reaction after using the baby lotion I bought from you last week. His face is swollen. What do I do?",
        "expect_intent": "complaint",
        "expect_urgency_in": ["high"],
        "must_escalate": True,
        "min_confidence": 0.85
    },
    {
        "id": "TC06",
        "label": "Simple exchange request (EN)",
        "email": "I bought a baby monitor but I want to exchange it for the model with two cameras. Order number MW-77201.",
        "expect_intent": "return_request",
        "expect_urgency_in": ["medium", "low"],
        "must_escalate": False,
        "min_confidence": 0.75
    },
    # ── Adversarial / tricky cases ─────────────────────────────────────────
    {
        "id": "TC07",
        "label": "Spam / gibberish — must refuse",
        "email": "Buy cheap Rolex!!! Click here now!! www.fakewatch.ru Great deals!!!",
        "expect_intent": "spam",
        "expect_urgency_in": ["low"],
        "must_escalate": False,
        "max_confidence": 0.4   # Should be low confidence / spam
    },
    {
        "id": "TC08",
        "label": "Ambiguous — no clear intent",
        "email": "Hi, I have a question about something.",
        "expect_intent": "other",
        "expect_urgency_in": ["low"],
        "must_escalate": False,
        "max_confidence": 0.6   # Must express uncertainty
    },
    {
        "id": "TC09",
        "label": "Mixed Arabic/English (code-switch)",
        "email": "السلام عليكم، I got the wrong item delivered. Order is MW-30021. Can you help بسرعة please?",
        "expect_intent": "order_issue",
        "expect_urgency_in": ["high", "medium"],
        "must_escalate": False,
        "min_confidence": 0.70
    },
    {
        "id": "TC10",
        "label": "Legal threat — must escalate",
        "email": "I am contacting my lawyer regarding the defective product you sold me. This is your last chance to resolve this before I take legal action.",
        "expect_intent": "complaint",
        "expect_urgency_in": ["high"],
        "must_escalate": True,
        "min_confidence": 0.80
    },
    {
        "id": "TC11",
        "label": "Positive feedback — not a complaint",
        "email": "Just wanted to say the delivery was super fast and the baby gym is exactly as described. My daughter loves it! Thank you Mumzworld.",
        "expect_intent": "other",
        "expect_urgency_in": ["low"],
        "must_escalate": False,
        "min_confidence": 0.70
    },
    {
        "id": "TC12",
        "label": "Arabic complaint with urgency",
        "email": "أنا غاضب جداً. اشتريت سرير أطفال وكان به خدوش كبيرة عند الاستلام. أريد استرداد كامل المبلغ فوراً.",
        "expect_intent": "complaint",
        "expect_urgency_in": ["high", "medium"],
        "must_escalate": False,
        "min_confidence": 0.75
    },
]


# ── Eval runner ───────────────────────────────────────────────────────────────

async def run_single(client: httpx.AsyncClient, tc: dict) -> dict:
    try:
        r = await client.post(BASE_URL, json={"email": tc["email"]}, timeout=30)
        r.raise_for_status()
        result = r.json()
    except Exception as e:
        return {"id": tc["id"], "label": tc["label"], "passed": False, "error": str(e)}

    passes = []
    failures = []

    # Check intent
    if result.get("intent") == tc.get("expect_intent"):
        passes.append("intent ✓")
    else:
        failures.append(f"intent: got '{result.get('intent')}', expected '{tc.get('expect_intent')}'")

    # Check urgency
    if result.get("urgency") in tc.get("expect_urgency_in", []):
        passes.append("urgency ✓")
    else:
        failures.append(f"urgency: got '{result.get('urgency')}', expected one of {tc.get('expect_urgency_in')}")

    # Check escalate
    if "must_escalate" in tc:
        if result.get("escalate") == tc["must_escalate"]:
            passes.append("escalate ✓")
        else:
            failures.append(f"escalate: got {result.get('escalate')}, expected {tc['must_escalate']}")

    # Check confidence bounds
    conf = result.get("confidence", 0)
    if "min_confidence" in tc:
        if conf >= tc["min_confidence"]:
            passes.append(f"confidence ✓ ({conf:.2f})")
        else:
            failures.append(f"confidence too low: {conf:.2f} < {tc['min_confidence']}")
    if "max_confidence" in tc:
        if conf <= tc["max_confidence"]:
            passes.append(f"confidence (uncertain) ✓ ({conf:.2f})")
        else:
            failures.append(f"confidence too high for uncertain case: {conf:.2f} > {tc['max_confidence']}")

    passed = len(failures) == 0
    return {
        "id": tc["id"],
        "label": tc["label"],
        "passed": passed,
        "passes": passes,
        "failures": failures,
        "result": result
    }


async def main():
    print("\n🧪 Mumzworld Email Triage — Eval Suite\n" + "=" * 50)
    async with httpx.AsyncClient() as client:
        results = await asyncio.gather(*[run_single(client, tc) for tc in TEST_CASES])

    passed = sum(1 for r in results if r["passed"])
    total = len(results)

    for r in results:
        status = "✅ PASS" if r["passed"] else "❌ FAIL"
        print(f"\n{status} [{r['id']}] {r['label']}")
        if not r["passed"]:
            for f in r.get("failures", []):
                print(f"   ↳ {f}")
        if "error" in r:
            print(f"   ↳ ERROR: {r['error']}")

    print(f"\n{'=' * 50}")
    print(f"Score: {passed}/{total} ({100*passed//total}%)")
    print("=" * 50)

    # Save results to file
    with open("evals/results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print("Full results saved to evals/results.json\n")


if __name__ == "__main__":
    asyncio.run(main())