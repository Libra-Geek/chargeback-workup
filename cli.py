from __future__ import annotations
"""
CLI runner. Three uses:

  python cli.py --all                 work up all 10 cases (cached after first run)
  python cli.py --case CB-2025-0004   work up a single case
  python cli.py --all --force         ignore cache, re-run everything
  python cli.py --case CB-2025-0001 --dry-run
                                      print the assembled prompt (rules + case data)
                                      without calling the API. Useful for checking
                                      what the model will see before spending tokens.

Output workups land in results/<case_id>.json and print as a summary table.
"""

import argparse
import json
import sys

from rules import format_rule_for_prompt
from workup import get_case, load_cases, run_all, run_workup

ACTION_DISPLAY = {
    "represent": "REPRESENT",
    "accept_liability": "ACCEPT LIABILITY",
    "request_more_evidence": "REQUEST MORE EVIDENCE",
}


def print_summary(results: list[dict]) -> None:
    print("\n" + "=" * 96)
    print(f"{'Case':<14} {'Merchant':<26} {'Code':<8} {'Recommendation':<24} Flags")
    print("-" * 96)
    for r in results:
        case = get_case(r["case_id"])
        flags = len(r.get("analyst_flags", []))
        print(f"{r['case_id']:<14} "
              f"{case['transaction']['merchant_name'][:25]:<26} "
              f"{case['scheme'][:2].upper()}-{case['reason_code']:<5} "
              f"{ACTION_DISPLAY.get(r['recommended_action'], '?'):<24} "
              f"{flags if flags else '-'}")
    print("=" * 96)
    print("Full workups saved to results/<case_id>.json")


def print_dry_run(case_id: str) -> None:
    case = get_case(case_id)
    print("=" * 80)
    print(f"DRY RUN: {case_id} - no API call made")
    print("=" * 80)
    print("\nRULES THAT WILL BE INJECTED:\n")
    print(format_rule_for_prompt(case["reason_code"]))
    print("\nCASE DATA THAT WILL BE SENT:\n")
    print(json.dumps({k: v for k, v in case.items()
                      if k != "merchant_evidence_documents"}, indent=2))
    print(f"\nEVIDENCE DOCUMENTS THAT WILL BE ATTACHED "
          f"({len(case['merchant_evidence_documents'])}):")
    for doc in case["merchant_evidence_documents"]:
        print(f"  - {doc}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Chargeback representment workup tool")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--all", action="store_true", help="work up all cases")
    group.add_argument("--case", metavar="CASE_ID", help="work up one case")
    parser.add_argument("--force", action="store_true", help="ignore cached results")
    parser.add_argument("--dry-run", action="store_true",
                        help="print the prompt without calling the API (single case only)")
    args = parser.parse_args()

    if args.dry_run:
        if not args.case:
            sys.exit("--dry-run requires --case")
        print_dry_run(args.case)
        return

    if args.all:
        results = run_all(force=args.force)
    else:
        results = [run_workup(args.case, force=args.force)]
    print_summary(results)


if __name__ == "__main__":
    main()
