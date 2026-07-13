# Chargeback Representment Workup Tool

Takes a chargeback case, reads the merchant's evidence against the scheme's
compelling evidence requirements, and produces an analyst-ready workup: what
the issuer alleges, whether each requirement is satisfied and where the proof
sits, a rationale ready to file, and a recommended action the analyst can
accept or override.

The senior analyst's framing shaped the design: the decision is usually clear
in 90 seconds, the other 18 minutes is rule lookup, PDF re-reading and
write-up. This tool collapses those 18 minutes into one screen. It prepares
the decision. The analyst owns it.

## Quickstart (under 10 minutes)

```bash
git clone https://github.com/Libra-Geek/chargeback-workup.git
cd chargeback-workup
pip install -r requirements.txt
cp .env.example .env        # add your ANTHROPIC_API_KEY
python cli.py --all          # works up all 10 cases, ~2-3 minutes
streamlit run app.py         # opens the analyst UI
```

Workups are cached to `results/<case_id>.json` after the first run, so the UI
never re-spends tokens on a case already worked up. Use `--force` to re-run.

Useful extras:

```bash
python cli.py --case CB-2025-0004              # one case
python cli.py --case CB-2025-0001 --dry-run    # inspect the exact prompt, no API call
```

## How it works

```
cases.json ──┐
             ├─► build prompt ──► Claude (PDFs and images attached natively)
rules.py ────┘         │
                       ▼
             strict JSON workup ──► validate (retry once) ──► cache ──► UI / CLI
```

One LLM call per case. The prompt contains the reason code's compelling
evidence requirements injected verbatim, the full case metadata and issuer
narrative, and every evidence document attached in full.

## Design decisions and tradeoffs

**Documents go to the model natively, no OCR pipeline.** I considered
Tesseract-style OCR plus text extraction. It is cheaper per page but loses
document layout, handles photos badly (one case's evidence is a delivery
photograph), and adds a dependency chain. Claude reads PDFs and images
natively, so every document goes in whole, untruncated. The deciding factor
was one provided case that buries its decisive proof of delivery on page 8
of a 10-page repetitive manifest. Cutting documents short or flattening them
to plain text risks throwing away exactly the evidence that wins the case.
At 10 cases with small files, full document processing costs pennies. The
honest limitation is that at real volume, 80 cases per analyst per day with
larger files, you would add a cheaper first-pass triage model, per-document
caching, and page-level chunking with a retrieval step.

**Scheme rules are grounded data, not model memory.** The model is never
asked to recall Visa or Mastercard rules. `rules.py` holds the simplified
requirements transcribed from the provided reason_codes file, and each case's
prompt carries its reason code's checklist verbatim with an instruction to
assess only against it. This matters twice over: it prevents hallucinated
scheme rules, and it makes rule behaviour a data change rather than a prompt
rewrite. It is also what handles Visa 10.5 correctly: the rule text stating
the code is generally not representable travels with the case and overrides
evidence quality, so strong evidence does not tempt the model into a
representment that scheme rules do not permit.

**Merchant assertions are not evidence.** The system prompt states plainly
that a merchant's own risk scores and confident language prove nothing. One
provided case consists entirely of a merchant's internal report concluding
"we are confident this transaction is legitimate" while the transaction
metadata shows failed AVS, failed CVV and no 3DS. The tool's job is to say
that out loud, not be persuaded by tone.

**Uncertainty is surfaced, not smoothed over.** Every requirement verdict
carries a confidence level, and genuinely marginal calls go into
`analyst_flags` rather than being forced into a clean answer. Some of the
provided cases are judgment calls by design. The workup's job on those is to
lay out the gap and point at the evidence, and let the analyst decide.

**Structured output with validation.** The model returns strict JSON matching
the workup schema. Output is validated (action and status enums, one
assessment entry per requirement) with one corrective retry. Any residual
validation problems are stored on the result rather than silently dropped.

**UI: Streamlit, queue-first.** For 80 cases a day, the analyst needs two
things: a queue where recommendation, confidence and flag count are visible
at a glance so the clean represents can be batched fast, and a detail view
where every requirement verdict points at the exact document and location so
checking a date does not mean opening four PDFs. The rationale is an editable
text box, ready to file. 
Overrides require a reason and are logged to
`results/overrides.jsonl` with a timestamp. In production, that log is the
feedback loop: recurring overrides on a reason code tell you where the
prompt, the rules data, or the model is falling short.

## Output schema

Each workup in `results/<case_id>.json`:

| Field | Contents |
|---|---|
| `reason_code_summary` | Plain-English restatement of the allegation and what defends it |
| `evidence_assessment[]` | Per requirement: status (satisfied / partial / missing), document pointer, location, notes, confidence |
| `representment_rationale` | 3-5 sentences, analyst-ready |
| `recommended_action` | represent / accept_liability / request_more_evidence, with one-line justification |
| `evidence_requests[]` | Specific asks for the merchant, when more evidence is the recommendation |
| `analyst_flags[]` | Judgment calls and anomalies the analyst should eyeball before filing |

## Repo layout

```
data/cases.json            10 provided cases
data/documents/            19 provided evidence files
data/reason_codes_source.pdf   provided rules source
rules.py                   transcribed requirements + prompt rendering
workup.py                  pipeline: prompt assembly, API call, validation, cache
cli.py                     batch runner and dry-run prompt inspector
app.py                     Streamlit analyst UI
results/                   cached workups and override log (gitignored)
```

## What I would build next

A production queue doing 80 cases per analyst
per day would need cost controls before anything else, starting with a
cheaper model doing a first pass triage and per-document caching so the same
evidence file is never processed twice. After that, the obvious extensions
are generating the representment letter directly from the approved rationale,
versioning the scheme rules with effective dates so a past workup can always
be checked against the rule that was actually in force when it was made, and
mining the override log to find where the tool and the analysts disagree,
because that is where the next round of prompt and rules improvements comes
from.

## Sample outputs

sample_outputs/ contains the workups for all 10 cases as produced on the first
full run. These are unedited model output, occasional imperfections included,
which is why the UI puts an editable rationale and a logged analyst decision
in front of anything being filed. Committed so the tool's output quality can
be reviewed without spending API tokens; a live run will regenerate fresh
results into results/.
