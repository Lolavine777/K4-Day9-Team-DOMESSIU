import os
import json
import glob
from datetime import datetime
from dotenv import load_dotenv
from data_loader import DataLoader
from agents import LLMClient, CustomerAgent, OrderProductAgent, PaymentAgent, DeliveryAgent, PolicyAgent, VerifierAgent

load_dotenv()

def main():
    workspace_dir = "."
    input_dir = os.path.join(workspace_dir, "input")
    output_dir = os.path.join(workspace_dir, "output")
    logging_dir = os.path.join(workspace_dir, "logging")
    
    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(logging_dir, exist_ok=True)
    
    data_loader = DataLoader(os.path.join(workspace_dir, "data"))
    llm_client = LLMClient()
    
    customer_agent = CustomerAgent(llm_client)
    order_product_agent = OrderProductAgent(llm_client)
    payment_agent = PaymentAgent(llm_client)
    delivery_agent = DeliveryAgent(llm_client)
    policy_agent = PolicyAgent(llm_client)
    verifier_agent = VerifierAgent(llm_client)
    
    input_files = sorted(glob.glob(os.path.join(input_dir, "EC_*.json")))
    print(f"Found {len(input_files)} input files.")
    
    trace_records = []
    stats = {}
    
    for idx, filepath in enumerate(input_files):
        filename = os.path.basename(filepath)
        print(f"[{idx+1}/{len(input_files)}] Processing {filename}...")
        
        with open(filepath, 'r', encoding='utf-8') as f:
            case_input = json.load(f)
            
        case_id = case_input["case_id"]
        claimed_order_id = case_input["customer_request"]["claimed_order_id"]
        
        # 1. Customer Agent
        customer_res = customer_agent.analyze(data_loader, case_id, claimed_order_id)
        
        # 2. Order & Product Agent
        order_res = order_product_agent.analyze(data_loader, case_id, claimed_order_id)
        has_items = len(order_res["product_ids"]) > 0
        
        # 3. Payment Agent
        payment_res = payment_agent.analyze(data_loader, case_id, claimed_order_id, has_items)
        
        # 4. Delivery Agent
        delivery_res = delivery_agent.analyze(data_loader, case_id, claimed_order_id)
        
        # 5. Policy Agent (Applies business policy EC_POLICY_V2)
        policy_res = policy_agent.apply_policy(
            data_loader, case_id, claimed_order_id, customer_res, order_res, payment_res, delivery_res
        )
        
        # 6. Build final structured output dictionary
        final_output = {
            "case_id": case_id,
            "case_assessment": {
                "primary_issue": policy_res["primary_issue"],
                "secondary_issues": policy_res["secondary_issues"],
                "case_status": policy_res["case_status"],
                "confidence": policy_res["confidence"]
            },
            "affected_entities": {
                "order_ids": [claimed_order_id],
                "item_ids": [f"{claimed_order_id}:{item['order_item_id']}" for item in data_loader.get_order_items(claimed_order_id)],
                "seller_ids": delivery_res.get("late_handoff_seller_ids", []) if policy_res["primary_issue"] == "late_delivery_seller" and delivery_res.get("late_handoff_seller_ids") else order_res["seller_ids"],
                "payment_ids": payment_res["payment_ids"]
            },
            "customer_context": {
                "customer_unique_id": customer_res["customer_unique_id"],
                "related_order_ids": customer_res["related_order_ids"]
            },
            "product_context": {
                "product_ids": order_res["product_ids"],
                "category_names": order_res["category_names"]
            },
            "delivery_analysis": {
                "delivered_at": delivery_res.get("delivered_at"),
                "estimated_delivery_at": delivery_res.get("estimated_delivery_at"),
                "carrier_handoff_at": delivery_res.get("carrier_handoff_at"),
                "delivery_variance_hours": delivery_res.get("delivery_variance_hours"),
                "seller_handoff_analysis": delivery_res.get("seller_handoff_analysis", []),
                "late_handoff_seller_ids": delivery_res.get("late_handoff_seller_ids", [])
            },
            "payment_reconciliation": {
                "currency": "BRL",
                "item_total_brl": payment_res["item_total_brl"],
                "freight_total_brl": payment_res["freight_total_brl"],
                "expected_total_brl": payment_res["expected_total_brl"],
                "payment_total_brl": payment_res["payment_total_brl"],
                "difference_brl": payment_res["difference_brl"],
                "reconciled": payment_res["reconciled"],
                "payment_types": payment_res["payment_types"]
            },
            "root_cause_analysis": {
                "ranked_causes": policy_res["ranked_causes"],
                "responsible_parties": policy_res["responsible_parties"]
            },
            "evidence_ids": policy_res["evidence_ids"],
            "financial_resolution": {
                "currency": "BRL",
                "recommended_refund_brl": policy_res["recommended_refund_brl"]
            },
            "resolution_actions": policy_res["resolution_actions"]
        }
        
        # 7. Verify and fix limits / formats
        final_output = verifier_agent.verify(final_output)
        
        # Save case output
        output_filepath = os.path.join(output_dir, filename)
        with open(output_filepath, 'w', encoding='utf-8') as out_f:
            json.dump(final_output, out_f, indent=2, ensure_ascii=False)
            
        # Write Trace Record using LLM Handoffs!
        trace_record = {
            "case_id": case_id,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "input": case_input,
            "coordinator_handoff_trace": {
                "customer_agent_report": customer_res.get("handoff"),
                "order_agent_report": order_res.get("handoff"),
                "payment_agent_report": payment_res.get("handoff"),
                "delivery_agent_report": delivery_res.get("handoff"),
                "policy_agent_llm_prompt": policy_res.get("llm_prompt"),
                "policy_agent_llm_decision": policy_res.get("llm_response")
            },
            "output": final_output
        }
        trace_records.append(trace_record)
        
        # Log stats
        p_issue = policy_res["primary_issue"]
        stats[p_issue] = stats.get(p_issue, 0) + 1
        
    # Write trace.jsonl file
    trace_filepath = os.path.join(logging_dir, "trace.jsonl")
    with open(trace_filepath, 'w', encoding='utf-8') as trace_f:
        for record in trace_records:
            trace_f.write(json.dumps(record, ensure_ascii=False) + "\n")
            
    print("\nProcessing complete!")
    print("Primary Issue Statistics:")
    for k, v in stats.items():
        print(f"  - {k}: {v} cases")
        
if __name__ == "__main__":
    main()
