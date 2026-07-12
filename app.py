from __future__ import annotations

# Analyst UI. Design brief: an analyst working 80 cases a day.
#
# Layout: the sidebar is the queue, the main page is the work.
# A dropdown selects the case (each option carries its recommendation,
# so navigation itself is informative), and a compact table underneath
# gives the at-a-glance scan of the whole queue: recommendation,
# confidence and flag count per case. The detail view fills the main
# page: issuer allegation next to evidence verdicts, each verdict
# pointing at the exact document and location, an editable rationale
# ready to file, and an override control. Overrides require a typed
# reason and are logged with a timestamp to results/overrides.jsonl.
# The tool prepares the decision; the analyst owns it.
#
# Run:  streamlit run app.py

import json
from datetime import datetime, timezone
from typing import Optional

import streamlit as st

from workup import RESULTS_DIR, get_case, load_cases, run_workup

st.set_page_config(page_title="Representment Workup", layout="wide")

OVERRIDES_PATH = RESULTS_DIR / "overrides.jsonl"

ACTION_LABELS = {
    "represent": "Represent",
    "accept_liability": "Accept liability",
    "request_more_evidence": "Request more evidence",
}
ACTION_COLOURS = {
    "represent": "green",
    "accept_liability": "red",
    "request_more_evidence": "orange",
}
STATUS_ICONS = {"satisfied": "✅", "partial": "🟡", "missing": "❌"}


def cached_result(case_id: str) -> Optional[dict]:
    path = RESULTS_DIR / (case_id + ".json")
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return None


def log_override(case_id: str, original: str, chosen: str, reason: str) -> None:
    RESULTS_DIR.mkdir(exist_ok=True)
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "case_id": case_id,
        "model_recommendation": original,
        "analyst_decision": chosen,
        "analyst_reason": reason,
    }
    with open(OVERRIDES_PATH, "a") as f:
        f.write(json.dumps(entry) + "\n")


def confidence_summary(workup: dict) -> str:
    levels = [e.get("confidence") for e in workup.get("evidence_assessment", [])]
    if not levels:
        return "n/a"
    if "low" in levels:
        return "low"
    if "medium" in levels:
        return "medium"
    return "high"


# ------------------------------------------------------------------- sidebar
cases = load_cases()
case_ids = [c["case_id"] for c in cases]

with st.sidebar:
    st.header("Queue")

    if st.button("Run all unworked cases"):
        progress = st.progress(0.0, text="Working up cases...")
        for i, cid in enumerate(case_ids):
            if cached_result(cid) is None:
                progress.progress((i + 1) / len(case_ids), text="Working up " + cid + "...")
                run_workup(cid)
        progress.progress(1.0, text="Done")
        st.rerun()

    def case_option_label(cid: str) -> str:
        r = cached_result(cid)
        merchant = get_case(cid)["transaction"]["merchant_name"]
        if r is None:
            return cid + " · " + merchant + " · not run"
        return cid + " · " + merchant + " · " + ACTION_LABELS[r["recommended_action"]]

    selected = st.selectbox(
        "Open case",
        case_ids,
        format_func=case_option_label,
    )

    st.markdown("**Queue at a glance**")
    rows = []
    for c in cases:
        r = cached_result(c["case_id"])
        rows.append({
            "Case": c["case_id"].replace("CB-2025-", "#"),
            "Recommendation": ACTION_LABELS.get(r["recommended_action"], "?") if r else "Not run",
            "Conf": confidence_summary(r) if r else "-",
            "Flags": len(r.get("analyst_flags", [])) if r else 0,
        })
    st.dataframe(rows, hide_index=True, width="stretch")

    st.caption(
        "Workups are cached to results/ after the first run. "
        "Overrides are logged to results/overrides.jsonl."
    )

# --------------------------------------------------------------- detail view
st.title("Chargeback Representment Workup")

case = get_case(selected)
txn = case["transaction"]
result = cached_result(selected)

left, right = st.columns([3, 2])
with left:
    st.subheader(selected + " - " + txn["merchant_name"])
    st.markdown(
        "**" + case["scheme"].title() + " " + case["reason_code"] + "** - "
        + case["reason_code_label"] + "  \n"
        + "Amount: " + str(case["chargeback_amount"]["value"]) + " "
        + case["chargeback_amount"]["currency"]
        + " | Transaction date: " + txn["transaction_date"][:10]
        + " | Chargeback date: " + case["chargeback_date"]
    )
    st.info("**Issuer narrative:** " + case["issuer_narrative"])
with right:
    st.markdown("**Transaction signals**")
    st.markdown(
        "AVS: `" + str(txn["avs_result"]) + "` | CVV: `" + str(txn["cvv_result"])
        + "` | 3DS: `" + str(txn["three_ds_status"]) + "`  \n"
        + "Billing: `" + str(txn["billing_address_postcode"])
        + "` | Shipping: `" + str(txn["shipping_address_postcode"]) + "`  \n"
        + "IP: `" + str(txn["ip_address"]) + "` | Device: `"
        + str(txn["device_fingerprint"]) + "`"
    )
    st.markdown("**Merchant evidence**")
    if case["merchant_evidence_documents"]:
        for doc in case["merchant_evidence_documents"]:
            st.markdown("- " + doc)
    else:
        st.markdown("- None submitted")

st.divider()

if result is None:
    if st.button("Run workup for " + selected, type="primary"):
        with st.spinner("Reading rules and evidence..."):
            run_workup(selected)
        st.rerun()
    st.stop()

# Recommendation banner
action = result["recommended_action"]
st.markdown(
    "### :" + ACTION_COLOURS[action] + "[" + ACTION_LABELS[action].upper() + "]  "
    + "<small>" + result["action_justification"] + "</small>",
    unsafe_allow_html=True,
)

if result.get("analyst_flags"):
    for flag in result["analyst_flags"]:
        st.warning(flag, icon="⚠️")

st.markdown(
    "**What the issuer alleges and what defends it:** "
    + result["reason_code_summary"]
)

# Evidence assessment
st.markdown("#### Evidence against requirements")
if result["evidence_assessment"]:
    for entry in result["evidence_assessment"]:
        icon = STATUS_ICONS.get(entry["status"], "❔")
        pointer = ""
        if entry.get("document"):
            pointer = " → `" + entry["document"] + "`"
            if entry.get("location"):
                pointer += " (" + entry["location"] + ")"
        with st.container(border=True):
            st.markdown(
                icon + " **" + entry["status"].upper() + "** "
                + "(confidence: " + entry["confidence"] + ")" + pointer + "  \n"
                + "*Requirement:* " + entry["requirement"] + "  \n"
                + entry["notes"]
            )
else:
    st.markdown(
        "*No evidence checklist applies to this reason code. "
        "See recommendation above.*"
    )

if result.get("evidence_requests"):
    st.markdown("#### Ask the merchant for")
    for item in result["evidence_requests"]:
        st.markdown("- " + item)

# Editable rationale + analyst decision
st.markdown("#### Representment rationale (edit and file)")
rationale = st.text_area(
    "Rationale", value=result["representment_rationale"],
    height=140, label_visibility="collapsed",
)

st.markdown("#### Analyst decision")
decision = st.radio(
    "Final action",
    list(ACTION_LABELS.keys()),
    index=list(ACTION_LABELS.keys()).index(action),
    format_func=lambda a: ACTION_LABELS[a],
    horizontal=True,
)
if decision != action:
    reason = st.text_input("Reason for overriding the recommendation (required)")
    if st.button("Confirm override", type="primary", disabled=not reason.strip()):
        log_override(selected, action, decision, reason.strip())
        st.success(
            "Override logged: " + ACTION_LABELS[decision]
            + ". Saved to results/overrides.jsonl"
        )
else:
    if st.button("Confirm and file", type="primary"):
        log_override(selected, action, decision, "accepted model recommendation")
        st.success("Decision confirmed and logged.")
