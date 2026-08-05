import json
import os
import sys
from src.repository import DataRepository

VALID_PRIMARY_ISSUES = {
    "canceled_order_paid",
    "unavailable_order_paid",
    "late_delivery_seller",
    "late_delivery_logistics",
    "valid_split_payment",
    "unsupported_late_claim",
}

VALID_CASE_STATUS = {"action_required", "no_action"}

VALID_ROOT_CAUSES = {
    "SELLER_HANDOFF_AFTER_LIMIT",
    "CARRIER_DELIVERED_AFTER_ESTIMATE",
    "ORDER_CANCELED_AFTER_PAYMENT",
    "ORDER_UNAVAILABLE_AFTER_PAYMENT",
    "MULTIPLE_PAYMENTS_RECONCILED",
    "DELIVERY_WITHIN_ESTIMATE",
}


def validate_all_outputs(output_dir: str = "output", data_dir: str = "data") -> bool:
    print("=" * 60)
    print("STARTING COMPREHENSIVE OUTPUT VALIDATION")
    print("=" * 60)

    repo = DataRepository(data_dir=data_dir)

    expected_files = [f"EC_{i:03d}.json" for i in range(1, 51)]
    existing_files = sorted([f for f in os.listdir(output_dir) if f.startswith("EC_") and f.endswith(".json")])

    print(f"Checking output count: found {len(existing_files)} / 50 files")
    if len(existing_files) != 50:
        print(f"ERROR: Expected 50 files, but found {len(existing_files)}")
        return False

    errors_count = 0

    for fname in expected_files:
        fpath = os.path.join(output_dir, fname)
        if not os.path.exists(fpath):
            print(f"ERROR: File missing: {fname}")
            errors_count += 1
            continue

        try:
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            print(f"ERROR: File {fname} invalid JSON: {e}")
            errors_count += 1
            continue

        case_id = data.get("case_id")
        if case_id != fname.replace(".json", ""):
            print(f"ERROR: {fname} case_id mismatch: got '{case_id}'")
            errors_count += 1

        # Check required sections
        required_keys = [
            "case_id",
            "case_assessment",
            "affected_entities",
            "customer_context",
            "product_context",
            "delivery_analysis",
            "payment_reconciliation",
            "root_cause_analysis",
            "evidence_ids",
            "financial_resolution",
            "resolution_actions",
        ]
        for key in required_keys:
            if key not in data:
                print(f"ERROR: {fname} missing top-level key '{key}'")
                errors_count += 1

        # Check primary issue
        case_ass = data.get("case_assessment", {})
        primary = case_ass.get("primary_issue")
        if primary not in VALID_PRIMARY_ISSUES:
            print(f"ERROR: {fname} invalid primary_issue '{primary}'")
            errors_count += 1

        status = case_ass.get("case_status")
        if status not in VALID_CASE_STATUS:
            print(f"ERROR: {fname} invalid case_status '{status}'")
            errors_count += 1

        # Check array limits
        aff = data.get("affected_entities", {})
        if len(aff.get("order_ids", [])) > 5:
            errors_count += 1
            print(f"ERROR: {fname} order_ids > 5")
        if len(aff.get("item_ids", [])) > 5:
            errors_count += 1
            print(f"ERROR: {fname} item_ids > 5")
        if len(aff.get("seller_ids", [])) > 3:
            errors_count += 1
            print(f"ERROR: {fname} seller_ids > 3")
        if len(aff.get("payment_ids", [])) > 5:
            errors_count += 1
            print(f"ERROR: {fname} payment_ids > 5")

        ev_ids = data.get("evidence_ids", [])
        if len(ev_ids) > 20:
            errors_count += 1
            print(f"ERROR: {fname} evidence_ids > 20")

        # Grounding check for evidence_ids
        for eid in ev_ids:
            if eid.startswith("order:"):
                oid = eid.split(":", 1)[1]
                if not repo.order_exists(oid):
                    print(f"ERROR: {fname} ungrounded evidence '{eid}'")
                    errors_count += 1
            elif eid.startswith("item:"):
                parts = eid.split(":")
                if not repo.item_exists(parts[1], int(parts[2])):
                    print(f"ERROR: {fname} ungrounded evidence '{eid}'")
                    errors_count += 1
            elif eid.startswith("payment:"):
                parts = eid.split(":")
                if not repo.payment_exists(parts[1], int(parts[2])):
                    print(f"ERROR: {fname} ungrounded evidence '{eid}'")
                    errors_count += 1
            elif eid.startswith("seller:"):
                sid = eid.split(":", 1)[1]
                if not repo.seller_exists(sid):
                    print(f"ERROR: {fname} ungrounded evidence '{eid}'")
                    errors_count += 1
            elif eid.startswith("policy:"):
                code = eid.split(":", 1)[1]
                if code not in VALID_ROOT_CAUSES:
                    print(f"ERROR: {fname} invalid policy code '{eid}'")
                    errors_count += 1
            else:
                print(f"ERROR: {fname} malformed evidence_id format '{eid}'")
                errors_count += 1

    print("=" * 60)
    if errors_count == 0:
        print("ALL 50 CASES PASSED VALIDATION PERFECTLY! 100% SCHEMA & GROUNDING COMPLIANCE.")
        print("=" * 60)
        return True
    else:
        print(f"VALIDATION FAILED WITH {errors_count} TOTAL ERRORS.")
        print("=" * 60)
        return False


if __name__ == "__main__":
    success = validate_all_outputs()
    sys.exit(0 if success else 1)
