"""
Reason code rules, transcribed from the provided reason_codes file.

Design decision: the LLM is never asked to recall scheme rules from memory.
The requirements below are injected into every prompt verbatim, and the model
is instructed to assess evidence ONLY against the injected checklist. This
prevents hallucinated scheme rules and makes rule updates a data change, not
a prompt change.

logic values:
  "all"        every requirement must be covered for a defensible representment
  "any_2"      any two requirements are sufficient
  "any_1"      any one requirement is sufficient
  "no_represent"  this code is generally not representable; see special_note
"""

REASON_CODES = {
    "10.4": {
        "scheme": "visa",
        "label": "Other Fraud, Card Absent Environment",
        "issuer_claim": "Cardholder denies authorising a card-not-present transaction.",
        "logic": "any_2",
        "requirements": [
            "Evidence the cardholder used the same card and same shipping address in two prior undisputed transactions with this merchant, completed more than 120 days but less than 365 days before the disputed transaction",
            "Evidence the cardholder is in possession of and using the merchandise (e.g. signed-in account activity post-delivery, social media post tagging the merchant)",
            "For digital goods: device fingerprint, IP address, geolocation, and customer account login matching prior undisputed transactions",
            "Proof of delivery to the cardholder's verified billing address (not just shipping address) with signature confirmation",
        ],
    },
    "10.5": {
        "scheme": "visa",
        "label": "Visa Fraud Monitoring Program",
        "issuer_claim": "Transaction flagged under Visa's fraud monitoring program.",
        "logic": "no_represent",
        "requirements": [],
        "special_note": (
            "This reason code generally cannot be represented, regardless of how "
            "strong the merchant's evidence is. Recommend accept_liability unless "
            "the merchant can prove the transaction was miscoded by the issuer."
        ),
    },
    "12.5": {
        "scheme": "visa",
        "label": "Incorrect Amount",
        "issuer_claim": "The amount charged does not match the amount the cardholder authorised.",
        "logic": "all",
        "requirements": [
            "The signed receipt, terms of service, or order confirmation showing the amount the cardholder agreed to",
            "Documentation showing the amount charged matches that agreed amount",
            "If a tip, gratuity, or adjustment was added, evidence the cardholder authorised it",
        ],
    },
    "12.6.1": {
        "scheme": "visa",
        "label": "Duplicate Processing",
        "issuer_claim": "The same transaction was processed more than once.",
        "logic": "all",
        "requirements": [
            "Evidence the two transactions are for two separate purchases (e.g. different order IDs, different items, different services rendered)",
            "Documentation of each purchase event (separate invoices, separate delivery confirmations, separate service dates)",
            "Transaction timestamps and authorisation codes for each charge",
        ],
    },
    "13.1": {
        "scheme": "visa",
        "label": "Merchandise / Services Not Received",
        "issuer_claim": "Cardholder paid but never received the goods or services.",
        "logic": "all",
        "requirements": [
            "Proof of delivery: tracking number, carrier name, and confirmation of delivery to the cardholder's address",
            "For services: evidence the service was rendered on or before the expected date (booking confirmation, attendance log, access logs)",
            "Date of delivery / service rendered is on or before the chargeback date",
            "The delivery address materially matches the address provided by the cardholder at purchase",
        ],
    },
    "13.2": {
        "scheme": "visa",
        "label": "Cancelled Recurring Transaction",
        "issuer_claim": "Cardholder cancelled a recurring subscription but was still charged.",
        "logic": "all",
        "requirements": [
            "Terms of service disclosing the recurring billing arrangement and the cancellation method",
            "Evidence the cardholder was notified of the upcoming charge (typically 7+ days in advance) for transactions over a defined threshold",
            "No record of the cardholder having submitted a cancellation request prior to the billing date",
            "Evidence of the cardholder's original opt-in to the recurring arrangement",
        ],
    },
    "13.3": {
        "scheme": "visa",
        "label": "Not as Described or Defective Merchandise",
        "issuer_claim": "Cardholder received the goods but they are materially not as described or defective.",
        "logic": "all",
        "requirements": [
            "The merchant's published description of the item the cardholder purchased",
            "Evidence the item delivered matches that description (photos, specs, serial number match)",
            "Evidence the merchant offered a return/refund route and the cardholder did not use it, OR evidence the cardholder used and retained the merchandise after raising the complaint",
        ],
    },
    "13.6": {
        "scheme": "visa",
        "label": "Credit Not Processed",
        "issuer_claim": "The merchant agreed to a refund but never processed it.",
        "logic": "any_1",
        "requirements": [
            "Evidence that a refund was processed (refund transaction ID, date, amount)",
            "Evidence that no refund was ever agreed (merchant's refund policy and absence of any refund commitment in cardholder communications)",
        ],
    },
    "13.7": {
        "scheme": "visa",
        "label": "Cancelled Merchandise / Services",
        "issuer_claim": "Cardholder cancelled the purchase per the merchant's policy but was charged.",
        "logic": "all",
        "requirements": [
            "The merchant's cancellation policy as displayed at point of sale",
            "Evidence the cardholder agreed to that policy (e.g. checkbox click record, signed terms)",
            "Evidence the cardholder either did not cancel within the policy window, or cancelled outside the refundable period",
        ],
    },
    "4837": {
        "scheme": "mastercard",
        "label": "No Cardholder Authorisation",
        "issuer_claim": "Cardholder denies authorising the transaction (card-not-present fraud equivalent).",
        "logic": "any_2",
        "requirements": [
            "AVS match (full address) AND CVV match on the disputed transaction",
            "3D Secure authentication completed successfully (Mastercard SecureCode / Identity Check)",
            "Two prior undisputed transactions from the same cardholder with this merchant in the past 12 months, with matching billing details",
            "Proof of delivery to the cardholder's billing address with signature",
        ],
    },
    "4853": {
        "scheme": "mastercard",
        "label": "Cardholder Dispute (Goods / Services Not Provided)",
        "issuer_claim": "Goods or services were not provided as agreed.",
        "logic": "all",
        "requirements": [
            "Proof of delivery or service provision (tracking, confirmation, access log)",
            "Evidence the goods or services materially match what was advertised",
            "Either: no contact from the cardholder attempting to resolve the issue before the chargeback, OR documentation showing the merchant attempted resolution and the cardholder refused",
        ],
    },
    "4855": {
        "scheme": "mastercard",
        "label": "Goods / Services Not Provided",
        "issuer_claim": "Paid for goods or services that were never delivered or rendered.",
        "logic": "all",
        "requirements": [
            "Proof of delivery (tracking + carrier confirmation) or proof of service rendered (access logs, attendance, completed booking)",
            "Date of delivery / service is before the chargeback date",
            "Delivery address matches the cardholder's records",
        ],
    },
    "4859": {
        "scheme": "mastercard",
        "label": "No-Show / Addendum",
        "issuer_claim": "Cardholder was charged a no-show fee, late cancellation fee, or addendum charge that they dispute.",
        "logic": "all",
        "requirements": [
            "Evidence of the cardholder's original reservation or booking",
            "The merchant's no-show / cancellation policy as disclosed at booking",
            "Evidence the cardholder either failed to show or cancelled outside the policy window",
            "Evidence the fee charged matches the policy disclosed",
        ],
    },
    "4863": {
        "scheme": "mastercard",
        "label": "Cardholder Does Not Recognise - Potential Fraud",
        "issuer_claim": "Cardholder does not recognise the transaction (may be a confusing descriptor rather than fraud).",
        "logic": "any_1",
        "requirements": [
            "Evidence the merchant's billing descriptor matches the merchant name the cardholder would recognise",
            "AVS + CVV match on the disputed transaction",
            "Prior undisputed transactions from the same cardholder with this merchant",
            "Cardholder's IP / device / account login matching prior undisputed sessions",
        ],
    },
    "4870": {
        "scheme": "mastercard",
        "label": "Chip Liability Shift",
        "issuer_claim": "Counterfeit card used at a non-chip-enabled terminal (card-present only).",
        "logic": "no_represent",
        "requirements": [],
        "special_note": (
            "Card-present reason code. For a CNP-focused acquiring flow, recommend "
            "accept_liability and flag the merchant for terminal upgrade."
        ),
    },
}

LOGIC_DESCRIPTIONS = {
    "all": "ALL of the requirements below must be covered for a defensible representment.",
    "any_2": "ANY TWO of the requirements below are sufficient for a defensible representment.",
    "any_1": "ANY ONE of the requirements below is sufficient for a defensible representment.",
    "no_represent": "This reason code is generally NOT representable. See the special note.",
}


def get_rule(reason_code: str) -> dict:
    rule = REASON_CODES.get(reason_code)
    if rule is None:
        raise KeyError(
            f"Reason code {reason_code} not found in rules. "
            "Add it to rules.py before processing this case."
        )
    return rule


def format_rule_for_prompt(reason_code: str) -> str:
    """Render one reason code's rules as plain text for prompt injection."""
    rule = get_rule(reason_code)
    lines = [
        f"Reason code: {rule['scheme'].title()} {reason_code} - {rule['label']}",
        f"Issuer claim: {rule['issuer_claim']}",
        f"Decision logic: {LOGIC_DESCRIPTIONS[rule['logic']]}",
    ]
    if rule.get("special_note"):
        lines.append(f"SPECIAL NOTE (this overrides evidence quality): {rule['special_note']}")
    if rule["requirements"]:
        lines.append("Compelling evidence requirements:")
        for i, req in enumerate(rule["requirements"], 1):
            lines.append(f"  {i}. {req}")
    return "\n".join(lines)
