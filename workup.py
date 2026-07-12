from __future__ import annotations
"""
Representment workup pipeline.

Flow per case:
  1. Load the case from cases.json
  2. Load its evidence documents (PDFs as document blocks, images as image blocks)
     and send them to the model in full. No OCR step, no truncation. Rationale:
     one provided case buries the decisive proof of delivery deep inside a long
     repetitive PDF; any truncation or naive text extraction risks missing it,
     and a vision-capable model reads scanned layouts and photos that OCR
     handles poorly. At 10 cases this costs pennies. At real volume (80 cases
     per analyst per day) you would add caching, batching and a cheaper
     first-pass triage model; deliberately out of scope here.
  3. Inject the reason code's compelling evidence requirements verbatim from
     rules.py. The model is instructed to assess ONLY against that checklist.
  4. Request strict JSON matching the workup schema. Validate. One retry on
     malformed output.
  5. Cache the workup to results/<case_id>.json so the UI never re-spends
     tokens on a case that has already been worked up.
"""

import base64
import json
import os
import re
from pathlib import Path

import anthropic
from dotenv import load_dotenv

from rules import format_rule_for_prompt, get_rule

load_dotenv()

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
DOCS_DIR = DATA_DIR / "documents"
RESULTS_DIR = BASE_DIR / "results"

MODEL = os.getenv("MODEL", "claude-sonnet-4-6")

VALID_ACTIONS = {"represent", "accept_liability", "request_more_evidence"}
VALID_STATUSES = {"satisfied", "partial", "missing"}
VALID_CONFIDENCE = {"high", "medium", "low"}

SYSTEM_PROMPT = """You are a chargeback representment analyst assistant at a payment \
service provider, preparing analyst-ready workups of disputed transactions.

Non-negotiable rules for every assessment:

1. Assess evidence ONLY against the compelling evidence requirements provided \
in this prompt. Never rely on your own memory of Visa or Mastercard scheme \
rules. If the provided rules say a reason code cannot be represented, that \
overrides evidence quality entirely.

2. A merchant's own assertions, internal risk scores, or confident language \
are NOT compelling evidence. A document only satisfies a requirement if its \
contents actually meet what the requirement asks for. Merchants frequently \
upload material that looks relevant but proves nothing. Say so plainly when \
that happens.

3. Read every document in full, including long or repetitive ones. Decisive \
evidence is sometimes buried many pages into an otherwise irrelevant file. \
When you find it, give the analyst a precise pointer: document name and page \
or section.

4. Cross-check documents against the transaction metadata and the issuer \
narrative. Mismatched addresses, missing signatures, AVS/CVV failures, or a \
narrative the evidence does not answer all matter.

5. Surface uncertainty honestly. If a call is genuinely marginal, mark the \
requirement partial, lower your confidence, and put the judgment call in \
analyst_flags rather than forcing a clean answer. The analyst decides; you \
prepare.

6. Write the representment rationale in plain professional English, 3 to 5 \
sentences, ready for the analyst to lightly edit and file. British English. \
Do not use em dashes anywhere.

Respond with a single JSON object only. No markdown fences, no preamble, no \
commentary outside the JSON."""

OUTPUT_SCHEMA_DESCRIPTION = """Return JSON with exactly this shape:
{
  "reason_code_summary": "Plain-English restatement of what the issuer alleges and what compelling evidence the scheme requires to defend it. 2-4 sentences.",
  "evidence_assessment": [
    {
      "requirement": "The requirement text, abbreviated is fine",
      "status": "satisfied" | "partial" | "missing",
      "document": "filename the assessment points to, or null if no document addresses it",
      "location": "page number, section, or field within the document, or null",
      "notes": "One or two sentences: what the evidence shows or fails to show",
      "confidence": "high" | "medium" | "low"
    }
  ],
  "representment_rationale": "3-5 sentences, analyst-ready, plain professional English",
  "recommended_action": "represent" | "accept_liability" | "request_more_evidence",
  "action_justification": "One line",
  "evidence_requests": ["Specific items to ask the merchant for. Empty list unless recommended_action is request_more_evidence"],
  "analyst_flags": ["Anything the analyst should eyeball before filing: judgment calls, metadata anomalies, mismatches between narrative and evidence. Empty list if nothing."]
}

Include one evidence_assessment entry per requirement in the rules provided, \
in the same order. For a reason code with no requirements (not representable), \
return an empty evidence_assessment list."""


def load_cases() -> list[dict]:
    with open(DATA_DIR / "cases.json") as f:
        return json.load(f)


def get_case(case_id: str) -> dict:
    for case in load_cases():
        if case["case_id"] == case_id:
            return case
    raise KeyError(f"Case {case_id} not found in cases.json")


def _document_block(filename: str) -> dict:
    """Build an API content block for one evidence file. PDFs go in as native
    document blocks, PNG/JPG as image blocks, so the model sees layout and
    imagery rather than lossy extracted text."""
    path = DOCS_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"Evidence file missing: {path}")
    data = base64.standard_b64encode(path.read_bytes()).decode()
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return {
            "type": "document",
            "source": {"type": "base64", "media_type": "application/pdf", "data": data},
            "title": filename,
        }
    if suffix in {".png", ".jpg", ".jpeg", ".webp"}:
        media = {"jpg": "image/jpeg", "jpeg": "image/jpeg"}.get(suffix[1:], f"image/{suffix[1:]}")
        return {
            "type": "image",
            "source": {"type": "base64", "media_type": media, "data": data},
        }
    raise ValueError(f"Unsupported evidence file type: {filename}")


def build_user_content(case: dict) -> list[dict]:
    """Assemble the full user turn: rules, case data, then every evidence
    document, each preceded by a text label so pointers can name the file."""
    rule_text = format_rule_for_prompt(case["reason_code"])
    case_for_prompt = {k: v for k, v in case.items() if k != "merchant_evidence_documents"}

    content: list[dict] = [
        {
            "type": "text",
            "text": (
                "COMPELLING EVIDENCE RULES FOR THIS CASE (assess only against these):\n"
                f"{rule_text}\n\n"
                "CASE DATA:\n"
                f"{json.dumps(case_for_prompt, indent=2)}\n\n"
                f"MERCHANT EVIDENCE: {len(case['merchant_evidence_documents'])} document(s) follow. "
                "Read each one in full.\n\n"
                f"{OUTPUT_SCHEMA_DESCRIPTION}"
            ),
        }
    ]
    for filename in case["merchant_evidence_documents"]:
        content.append({"type": "text", "text": f"--- Evidence document: {filename} ---"})
        content.append(_document_block(filename))
    if not case["merchant_evidence_documents"]:
        content.append({"type": "text", "text": "The merchant submitted NO evidence documents."})
    return content


def _extract_json(raw: str) -> dict:
    """Parse the model's reply as JSON, tolerating stray markdown fences."""
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip())
    return json.loads(cleaned)


def validate_workup(workup: dict, case: dict) -> list[str]:
    """Light structural validation. Returns a list of problems (empty = valid)."""
    problems = []
    for key in ("reason_code_summary", "evidence_assessment", "representment_rationale",
                "recommended_action", "action_justification", "evidence_requests",
                "analyst_flags"):
        if key not in workup:
            problems.append(f"missing key: {key}")
    if workup.get("recommended_action") not in VALID_ACTIONS:
        problems.append(f"invalid recommended_action: {workup.get('recommended_action')}")
    rule = get_rule(case["reason_code"])
    assessments = workup.get("evidence_assessment", [])
    if rule["requirements"] and len(assessments) != len(rule["requirements"]):
        problems.append(
            f"expected {len(rule['requirements'])} assessment entries, got {len(assessments)}"
        )
    for entry in assessments:
        if entry.get("status") not in VALID_STATUSES:
            problems.append(f"invalid status: {entry.get('status')}")
        if entry.get("confidence") not in VALID_CONFIDENCE:
            problems.append(f"invalid confidence: {entry.get('confidence')}")
    return problems


def run_workup(case_id: str, force: bool = False) -> dict:
    """Produce (or load from cache) the workup for one case."""
    RESULTS_DIR.mkdir(exist_ok=True)
    cache_path = RESULTS_DIR / f"{case_id}.json"
    if cache_path.exists() and not force:
        with open(cache_path) as f:
            return json.load(f)

    case = get_case(case_id)
    client = anthropic.Anthropic()
    content = build_user_content(case)

    workup = None
    last_problems: list[str] = []
    for attempt in range(2):  # one retry on malformed output
        messages = [{"role": "user", "content": content}]
        if attempt == 1:
            messages.append({
                "role": "user",
                "content": (
                    "Your previous reply failed validation: "
                    f"{'; '.join(last_problems)}. Return corrected JSON only."
                ),
            })
        response = client.messages.create(
            model=MODEL,
            max_tokens=4000,
            system=SYSTEM_PROMPT,
            messages=messages,
        )
        raw = "".join(block.text for block in response.content if block.type == "text")
        try:
            candidate = _extract_json(raw)
        except json.JSONDecodeError as exc:
            last_problems = [f"reply was not valid JSON ({exc})"]
            continue
        last_problems = validate_workup(candidate, case)
        if not last_problems:
            workup = candidate
            break
        workup = candidate  # keep best effort if retry also imperfect

    if workup is None:
        raise RuntimeError(f"Model returned unparseable output for {case_id}: {last_problems}")

    result = {
        "case_id": case_id,
        "model": MODEL,
        "validation_problems": last_problems,  # empty list when clean
        **workup,
    }
    with open(cache_path, "w") as f:
        json.dump(result, f, indent=2)
    return result


def run_all(force: bool = False) -> list[dict]:
    results = []
    for case in load_cases():
        print(f"Working up {case['case_id']} ({case['scheme']} {case['reason_code']}, "
              f"{case['transaction']['merchant_name']})...")
        results.append(run_workup(case["case_id"], force=force))
    return results
