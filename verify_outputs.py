import os
import json
import glob

def verify():
    output_dir = "./output"
    files = sorted(glob.glob(os.path.join(output_dir, "EC_*.json")))
    
    print(f"Verifying outputs in {output_dir}...")
    print(f"Found {len(files)} output files.")
    
    if len(files) != 50:
        print(f"WARNING: Expected 50 files, but found {len(files)} files.")
        
    errors = 0
    stats = {}
    
    for filepath in files:
        filename = os.path.basename(filepath)
        case_id = filename.split('.')[0]
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception as e:
            print(f"[{case_id}] FAILED to load JSON: {e}")
            errors += 1
            continue
            
        # Check basic schema fields
        required_fields = [
            "case_id", "case_assessment", "affected_entities", "customer_context",
            "product_context", "delivery_analysis", "payment_reconciliation",
            "root_cause_analysis", "evidence_ids", "financial_resolution", "resolution_actions"
        ]
        for field in required_fields:
            if field not in data:
                print(f"[{case_id}] Missing field: {field}")
                errors += 1
                
        # Verify Case Assessment
        ca = data.get("case_assessment", {})
        p_issue = ca.get("primary_issue")
        stats[p_issue] = stats.get(p_issue, 0) + 1
        
        # Verify limits
        ae = data.get("affected_entities", {})
        if len(ae.get("order_ids", [])) > 5:
            print(f"[{case_id}] affected_entities.order_ids length {len(ae.get('order_ids'))} exceeds limit 5")
            errors += 1
        if len(ae.get("item_ids", [])) > 5:
            print(f"[{case_id}] affected_entities.item_ids length {len(ae.get('item_ids'))} exceeds limit 5")
            errors += 1
        if len(ae.get("seller_ids", [])) > 3:
            print(f"[{case_id}] affected_entities.seller_ids length {len(ae.get('seller_ids'))} exceeds limit 3")
            errors += 1
        if len(ae.get("payment_ids", [])) > 5:
            print(f"[{case_id}] affected_entities.payment_ids length {len(ae.get('payment_ids'))} exceeds limit 5")
            errors += 1
            
        cc = data.get("customer_context", {})
        if len(cc.get("related_order_ids", [])) > 5:
            print(f"[{case_id}] customer_context.related_order_ids length {len(cc.get('related_order_ids'))} exceeds limit 5")
            errors += 1
            
        pc = data.get("product_context", {})
        if len(pc.get("product_ids", [])) > 5:
            print(f"[{case_id}] product_context.product_ids length {len(pc.get('product_ids'))} exceeds limit 5")
            errors += 1
        if len(pc.get("category_names", [])) > 5:
            print(f"[{case_id}] product_context.category_names length {len(pc.get('category_names'))} exceeds limit 5")
            errors += 1
            
        rc = data.get("root_cause_analysis", {})
        if len(rc.get("ranked_causes", [])) > 3:
            print(f"[{case_id}] root_cause_analysis.ranked_causes length {len(rc.get('ranked_causes'))} exceeds limit 3")
            errors += 1
        if len(rc.get("responsible_parties", [])) > 3:
            print(f"[{case_id}] root_cause_analysis.responsible_parties length {len(rc.get('responsible_parties'))} exceeds limit 3")
            errors += 1
            
        if len(data.get("evidence_ids", [])) > 20:
            print(f"[{case_id}] evidence_ids length {len(data.get('evidence_ids'))} exceeds limit 20")
            errors += 1
            
        if len(data.get("resolution_actions", [])) > 5:
            print(f"[{case_id}] resolution_actions length {len(data.get('resolution_actions'))} exceeds limit 5")
            errors += 1
            
        # Verify values for empty items
        has_items = len(pc.get("product_ids", [])) > 0
        pr = data.get("payment_reconciliation", {})
        if not has_items:
            for field in ["expected_total_brl", "difference_brl", "reconciled"]:
                if pr.get(field) is not None:
                    print(f"[{case_id}] Order has no items, but payment_reconciliation.{field} is not null: {pr.get(field)}")
                    errors += 1
                    
        # Verify evidence ID format
        for ev_id in data.get("evidence_ids", []):
            parts = ev_id.split(':')
            if parts[0] not in ["order", "item", "payment", "seller", "policy"]:
                print(f"[{case_id}] Invalid evidence prefix in: {ev_id}")
                errors += 1
            if parts[0] == "order" and len(parts) != 2:
                print(f"[{case_id}] Invalid order evidence format: {ev_id}")
                errors += 1
            if parts[0] == "item" and len(parts) != 3:
                print(f"[{case_id}] Invalid item evidence format: {ev_id}")
                errors += 1
            if parts[0] == "payment" and len(parts) != 3:
                print(f"[{case_id}] Invalid payment evidence format: {ev_id}")
                errors += 1
            if parts[0] == "seller" and len(parts) != 2:
                print(f"[{case_id}] Invalid seller evidence format: {ev_id}")
                errors += 1
            if parts[0] == "policy" and len(parts) != 2:
                print(f"[{case_id}] Invalid policy evidence format: {ev_id}")
                errors += 1

    print("\nSummary of Verification:")
    print(f"Total files checked: {len(files)}")
    print(f"Total errors found: {errors}")
    print("Primary Issue Statistics:")
    for k, v in stats.items():
        print(f"  - {k}: {v} cases")
        
    if errors == 0:
        print("\nAll output files verified successfully! NO errors found.")
    else:
        print(f"\nVerification FAILED with {errors} errors.")

if __name__ == "__main__":
    verify()
