import os
import json
import requests
import pandas as pd
from dotenv import load_dotenv
from utils import parse_datetime, calculate_hours_difference, format_evidence_id

load_dotenv()

class LLMClient:
    def __init__(self):
        self.together_key = os.getenv("TOGETHER_API_KEY")
        self.openai_key = os.getenv("OPENAI_API_KEY")
        self.gemini_key = os.getenv("GEMINI_API_KEY")
        
        self.custom_key = os.getenv("LLM_API_KEY")
        self.custom_base = os.getenv("LLM_API_BASE")
        self.custom_model = os.getenv("LLM_MODEL")

    def call_llm(self, system_prompt, user_prompt, temperature=0.1, response_format=None):
        if self.custom_key:
            url = self.custom_base or "https://api.openai.com/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {self.custom_key}",
                "Content-Type": "application/json"
            }
            model = self.custom_model or "gpt-4o-mini"
            payload = {
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                "temperature": temperature
            }
            if response_format:
                payload["response_format"] = response_format
            try:
                res = requests.post(url, headers=headers, json=payload, timeout=30)
                res.raise_for_status()
                return res.json()["choices"][0]["message"]["content"]
            except Exception as e:
                print(f"Custom LLM API error: {e}")
                
        if self.together_key:
            url = "https://api.together.xyz/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {self.together_key}",
                "Content-Type": "application/json"
            }
            model = "Qwen/Qwen2.5-7B-Instruct"
            payload = {
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                "temperature": temperature
            }
            if response_format:
                payload["response_format"] = response_format
            try:
                res = requests.post(url, headers=headers, json=payload, timeout=30)
                res.raise_for_status()
                return res.json()["choices"][0]["message"]["content"]
            except Exception as e:
                print(f"Together LLM API error: {e}")

        if self.openai_key:
            url = "https://api.openai.com/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {self.openai_key}",
                "Content-Type": "application/json"
            }
            model = "gpt-4o-mini"
            payload = {
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                "temperature": temperature
            }
            if response_format:
                payload["response_format"] = response_format
            try:
                res = requests.post(url, headers=headers, json=payload, timeout=30)
                res.raise_for_status()
                return res.json()["choices"][0]["message"]["content"]
            except Exception as e:
                print(f"OpenAI LLM API error: {e}")

        if self.gemini_key:
            model = "gemini-1.5-flash"
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={self.gemini_key}"
            headers = {
                "Content-Type": "application/json"
            }
            payload = {
                "contents": [
                    {
                        "parts": [
                            {"text": f"System Instruction: {system_prompt}\n\nUser Input: {user_prompt}"}
                        ]
                    }
                ],
                "generationConfig": {
                    "temperature": temperature
                }
            }
            if response_format and response_format.get("type") == "json_object":
                payload["generationConfig"]["responseMimeType"] = "application/json"
            try:
                res = requests.post(url, headers=headers, json=payload, timeout=30)
                res.raise_for_status()
                return res.json()["candidates"][0]["content"]["parts"][0]["text"]
            except Exception as e:
                print(f"Gemini LLM API error: {e}")

        print("Warning: No LLM API Key is configured. LLM-based reasoning might be mocked.")
        return None

class BaseAgent:
    def __init__(self, client: LLMClient):
        self.client = client
        
    def _generate_handoff(self, agent_name, case_id, facts):
        system_prompt = f"You are the {agent_name} in an e-commerce dispute resolution multi-agent system. Output ONLY a brief, professional handoff message summarizing your findings for the Coordinator Agent."
        user_prompt = f"Ticket ID: {case_id}\nFacts found: {json.dumps(facts, default=str)}\nWrite the handoff message."
        
        try:
            text = self.client.call_llm(system_prompt, user_prompt, temperature=0.3)
            if text:
                return text.strip()
        except Exception:
            pass
        return f"Ticket ID: {case_id}. {agent_name} findings: {json.dumps(facts, default=str)}"

class CustomerAgent(BaseAgent):
    def analyze(self, data_loader, case_id, claimed_order_id):
        customer_unique_id = data_loader.get_customer_unique_id(claimed_order_id)
        if not customer_unique_id:
            res = {
                "customer_unique_id": None,
                "related_order_ids": [],
                "repeat_customer": False,
                "summary": "Customer not found."
            }
            res["handoff"] = self._generate_handoff("CustomerAgent", case_id, res)
            return res
        
        history = data_loader.get_customer_orders_history(customer_unique_id, exclude_order_id=claimed_order_id)
        related_order_ids = [o['order_id'] for o in history]
        repeat_customer = len(related_order_ids) > 0
        summary = f"Customer Unique ID: {customer_unique_id}. Historical orders (excluding current): {len(related_order_ids)}."
        
        res = {
            "customer_unique_id": customer_unique_id,
            "related_order_ids": related_order_ids,
            "repeat_customer": repeat_customer,
            "summary": summary
        }
        res["handoff"] = self._generate_handoff("CustomerAgent", case_id, {"summary": summary, "repeat_customer": repeat_customer})
        return res

class OrderProductAgent(BaseAgent):
    def analyze(self, data_loader, case_id, claimed_order_id):
        items = data_loader.get_order_items(claimed_order_id)
        raw_product_ids = []
        category_names = []
        raw_seller_ids = []
        
        for item in items:
            p_id = item['product_id']
            s_id = item['seller_id']
            raw_product_ids.append(p_id)
            raw_seller_ids.append(s_id)
            prod = data_loader.get_product_by_id(p_id)
            if prod:
                cat_orig = prod.get('product_category_name')
                if pd.notna(cat_orig) and cat_orig:
                    category_names.append(cat_orig)
                
        product_ids = []
        for pid in raw_product_ids:
            if pid not in product_ids:
                product_ids.append(pid)

        seller_ids = []
        for sid in raw_seller_ids:
            if sid not in seller_ids:
                seller_ids.append(sid)

        unique_categories = []
        for cat in category_names:
            if cat not in unique_categories:
                unique_categories.append(cat)

        multi_item_order = len(items) >= 2
        multi_seller_order = len(seller_ids) >= 2
        multiple_categories = len(unique_categories) >= 2
        
        summary = f"Order has {len(items)} item(s) and {len(seller_ids)} seller(s). Product categories: {unique_categories}."
        
        res = {
            "product_ids": product_ids,
            "category_names": unique_categories,
            "seller_ids": seller_ids,
            "multi_item_order": multi_item_order,
            "multi_seller_order": multi_seller_order,
            "multiple_categories": multiple_categories,
            "summary": summary
        }
        res["handoff"] = self._generate_handoff("OrderProductAgent", case_id, {"summary": summary})
        return res

class PaymentAgent(BaseAgent):
    def analyze(self, data_loader, case_id, claimed_order_id, has_items):
        payments = data_loader.get_order_payments(claimed_order_id)
        items = data_loader.get_order_items(claimed_order_id)
        
        payment_types = list(set([p['payment_type'] for p in payments]))
        payment_total_brl = round(sum([p['payment_value'] for p in payments]), 2)
        split_payment = len(payments) >= 2
        
        if not has_items:
            item_total_brl = 0.0
            freight_total_brl = 0.0
            expected_total_brl = None
            difference_brl = None
            reconciled = None
        else:
            item_total_brl = round(sum([item['price'] for item in items]), 2)
            freight_total_brl = round(sum([item['freight_value'] for item in items]), 2)
            expected_total_brl = round(item_total_brl + freight_total_brl, 2)
            difference_brl = round(payment_total_brl - expected_total_brl, 2)
            reconciled = abs(difference_brl) <= 0.10

        payment_ids = [f"{claimed_order_id}:{p['payment_sequential']}" for p in payments]
        
        res = {
            "payment_ids": payment_ids,
            "item_total_brl": item_total_brl if has_items else 0.0,
            "freight_total_brl": freight_total_brl if has_items else 0.0,
            "expected_total_brl": expected_total_brl,
            "payment_total_brl": payment_total_brl,
            "difference_brl": difference_brl,
            "reconciled": reconciled,
            "payment_types": payment_types,
            "split_payment": split_payment
        }
        res["handoff"] = self._generate_handoff("PaymentAgent", case_id, {
            "expected_total_brl": expected_total_brl,
            "payment_total_brl": payment_total_brl,
            "reconciled": reconciled,
            "split_payment": split_payment
        })
        return res

class DeliveryAgent(BaseAgent):
    def analyze(self, data_loader, case_id, claimed_order_id):
        order = data_loader.get_order_by_id(claimed_order_id)
        if not order:
            res = {}
            res["handoff"] = self._generate_handoff("DeliveryAgent", case_id, res)
            return res
            
        items = data_loader.get_order_items(claimed_order_id)
        
        delivered_at = order.get('order_delivered_customer_date')
        estimated_delivery_at = order.get('order_estimated_delivery_date')
        carrier_handoff_at = order.get('order_delivered_carrier_date')
        
        if pd.isna(delivered_at): delivered_at = None
        if pd.isna(estimated_delivery_at): estimated_delivery_at = None
        if pd.isna(carrier_handoff_at): carrier_handoff_at = None
        
        delivery_variance_hours = calculate_hours_difference(delivered_at, estimated_delivery_at)
        
        seller_limit_map = {}
        for item in items:
            s_id = item['seller_id']
            s_limit = item['shipping_limit_date']
            if pd.isna(s_limit): s_limit = None
            
            if s_id not in seller_limit_map:
                seller_limit_map[s_id] = s_limit
            else:
                t_curr = parse_datetime(s_limit)
                t_earliest = parse_datetime(seller_limit_map[s_id])
                if t_curr and t_earliest and t_curr < t_earliest:
                    seller_limit_map[s_id] = s_limit
                elif t_curr and not t_earliest:
                    seller_limit_map[s_id] = s_limit

        seller_handoff_analysis = []
        late_handoff_seller_ids = []
        
        for seller_id, shipping_limit_at in seller_limit_map.items():
            handoff_variance_hours = calculate_hours_difference(carrier_handoff_at, shipping_limit_at)
            late_handoff = False
            if handoff_variance_hours is not None and handoff_variance_hours > 0:
                late_handoff = True
                if seller_id not in late_handoff_seller_ids:
                    late_handoff_seller_ids.append(seller_id)
                    
            seller_handoff_analysis.append({
                "seller_id": seller_id,
                "shipping_limit_at": shipping_limit_at,
                "handoff_variance_hours": handoff_variance_hours,
                "late_handoff": late_handoff
            })
            
        res = {
            "delivered_at": delivered_at,
            "estimated_delivery_at": estimated_delivery_at,
            "carrier_handoff_at": carrier_handoff_at,
            "delivery_variance_hours": delivery_variance_hours,
            "seller_handoff_analysis": seller_handoff_analysis,
            "late_handoff_seller_ids": late_handoff_seller_ids,
            "order_status": order.get('order_status')
        }
        res["handoff"] = self._generate_handoff("DeliveryAgent", case_id, {
            "order_status": order.get('order_status'),
            "delivery_variance_hours": delivery_variance_hours,
            "late_handoff_seller_ids": late_handoff_seller_ids
        })
        return res

class PolicyAgent(BaseAgent):
    def apply_policy(self, data_loader, case_id, claimed_order_id, customer_res, order_res, payment_res, delivery_res):
        order_status = delivery_res.get("order_status")
        payment_total = payment_res.get("payment_total_brl", 0.0)
        reconciled = payment_res.get("reconciled")
        delivery_variance = delivery_res.get("delivery_variance_hours")
        late_sellers = delivery_res.get("late_handoff_seller_ids", [])
        split_payment = payment_res.get("split_payment", False)
        
        primary_issue = None
        responsible_party_type = None
        responsible_party_id = None
        recommended_refund = 0.0
        action_main = None
        root_cause_code = None
        
        if order_status == "canceled" and payment_total > 0:
            primary_issue = "canceled_order_paid"
            responsible_party_type = "platform"
            responsible_party_id = "OLIST_PLATFORM"
            recommended_refund = payment_total
            action_main = "issue_full_refund"
            root_cause_code = "ORDER_CANCELED_AFTER_PAYMENT"
        elif order_status == "unavailable" and payment_total > 0:
            primary_issue = "unavailable_order_paid"
            responsible_party_type = "platform"
            responsible_party_id = "OLIST_PLATFORM"
            recommended_refund = payment_total
            action_main = "issue_full_refund"
            root_cause_code = "ORDER_UNAVAILABLE_AFTER_PAYMENT"
        elif delivery_variance is not None and delivery_variance > 0 and len(late_sellers) > 0:
            primary_issue = "late_delivery_seller"
            responsible_party_type = "seller"
            responsible_party_id = late_sellers[0] if len(late_sellers) > 0 else None
            recommended_refund = payment_res.get("freight_total_brl", 0.0)
            action_main = "refund_freight"
            root_cause_code = "SELLER_HANDOFF_AFTER_LIMIT"
        elif delivery_variance is not None and delivery_variance > 0 and len(late_sellers) == 0:
            primary_issue = "late_delivery_logistics"
            responsible_party_type = "logistics_provider"
            responsible_party_id = "LOGISTICS_PROVIDER"
            recommended_refund = payment_res.get("freight_total_brl", 0.0)
            action_main = "refund_freight"
            root_cause_code = "CARRIER_DELIVERED_AFTER_ESTIMATE"
        elif split_payment and reconciled:
            primary_issue = "valid_split_payment"
            responsible_party_type = None
            responsible_party_id = None
            recommended_refund = 0.0
            action_main = "explain_valid_split_payment"
            root_cause_code = "MULTIPLE_PAYMENTS_RECONCILED"
        else:
            primary_issue = "unsupported_late_claim"
            responsible_party_type = None
            responsible_party_id = None
            recommended_refund = 0.0
            action_main = "reject_late_refund"
            root_cause_code = "DELIVERY_WITHIN_ESTIMATE"

        secondary_issues = []
        if order_res.get("multi_item_order"):
            secondary_issues.append("multi_item_order")
        if order_res.get("multi_seller_order"):
            secondary_issues.append("multi_seller_order")
        if payment_res.get("split_payment"):
            secondary_issues.append("split_payment")
        if customer_res.get("repeat_customer"):
            secondary_issues.append("repeat_customer")
        if order_res.get("multiple_categories"):
            secondary_issues.append("multiple_categories")

        case_status = "action_required" if recommended_refund > 0 else "no_action"

        ranked_causes = [{"cause_code": root_cause_code, "rank": 1}]
        if primary_issue == "late_delivery_seller" and delivery_variance is not None and delivery_variance > 0:
            ranked_causes.append({"cause_code": "CARRIER_DELIVERED_AFTER_ESTIMATE", "rank": 2})

        responsible_parties = []
        if responsible_party_type:
            if primary_issue == "late_delivery_seller":
                for idx, seller in enumerate(late_sellers):
                    responsible_parties.append({
                        "party_type": "seller",
                        "party_id": seller
                    })
            else:
                responsible_parties.append({
                    "party_type": responsible_party_type,
                    "party_id": responsible_party_id
                })

        evidence_ids = []
        evidence_ids.append(format_evidence_id("order", claimed_order_id))
        items = data_loader.get_order_items(claimed_order_id)
        for item in items:
            evidence_ids.append(format_evidence_id("item", claimed_order_id, item['order_item_id']))
        payments = data_loader.get_order_payments(claimed_order_id)
        for p in payments:
            evidence_ids.append(format_evidence_id("payment", claimed_order_id, p['payment_sequential']))
        if primary_issue == "late_delivery_seller":
            for seller in late_sellers:
                evidence_ids.append(format_evidence_id("seller", seller))
        evidence_ids.append(format_evidence_id("policy", root_cause_code))

        resolution_actions = [action_main]
        if primary_issue == "late_delivery_seller":
            resolution_actions.append("review_seller_handoff")
        elif primary_issue == "late_delivery_logistics":
            resolution_actions.append("review_carrier_delay")
            
        if recommended_refund > 0:
            resolution_actions.append("verify_refund_completion")
            
        if order_res.get("multi_seller_order"):
            resolution_actions.append("coordinate_multi_seller_case")
            
        if split_payment and primary_issue != "valid_split_payment":
            resolution_actions.append("verify_payment_allocation")

        system_prompt = (
            "You are the Policy Agent for Olist operating under EC_POLICY_V2.\n"
            "Review the handoff messages from the investigation agents and output a JSON object with your final decision.\n"
            "Your output must EXACTLY contain these fields:\n"
            "- primary_issue (string)\n"
            "- secondary_issues (list of strings)\n"
            "- case_status (string: action_required or no_action)\n"
            "- confidence (float between 0.0 and 1.0)\n"
            "- root_cause_code (string)\n"
            "- resolution_actions (list of strings)"
        )
        user_prompt = f"""
Dispute Case Handoff Messages:
- Case ID: {case_id}
- Customer Agent: {customer_res.get("handoff")}
- Order Agent: {order_res.get("handoff")}
- Payment Agent: {payment_res.get("handoff")}
- Delivery Agent: {delivery_res.get("handoff")}

Evaluate the facts above and return the JSON decision.
"""
        confidence = 0.95
        llm_decision = None
        try:
            llm_res = self.client.call_llm(system_prompt, user_prompt, temperature=0.1, response_format={"type": "json_object"})
            if llm_res:
                clean_res = llm_res.strip()
                if "```" in clean_res:
                    clean_res = clean_res.split("```")[1]
                    if clean_res.startswith("json"):
                        clean_res = clean_res[4:]
                clean_res = clean_res.strip()
                llm_decision = json.loads(clean_res)
                if "confidence" in llm_decision and llm_decision["confidence"] is not None:
                    c_val = float(llm_decision["confidence"])
                    if 0.0 <= c_val <= 1.0:
                        confidence = round(c_val, 2)
        except Exception:
            pass

        return {
            "primary_issue": primary_issue,
            "secondary_issues": secondary_issues,
            "case_status": case_status,
            "confidence": confidence,
            "ranked_causes": ranked_causes,
            "responsible_parties": responsible_parties,
            "evidence_ids": evidence_ids,
            "recommended_refund_brl": round(recommended_refund, 2),
            "resolution_actions": resolution_actions,
            "llm_prompt": user_prompt,
            "llm_response": llm_decision
        }

class VerifierAgent(BaseAgent):
    def verify(self, output_dict):
        if "affected_entities" in output_dict:
            ae = output_dict["affected_entities"]
            if len(ae.get("order_ids", [])) > 5:
                ae["order_ids"] = ae["order_ids"][:5]
            if len(ae.get("item_ids", [])) > 5:
                ae["item_ids"] = ae["item_ids"][:5]
            if len(ae.get("seller_ids", [])) > 3:
                ae["seller_ids"] = ae["seller_ids"][:3]
            if len(ae.get("payment_ids", [])) > 5:
                ae["payment_ids"] = ae["payment_ids"][:5]
                
        if "customer_context" in output_dict:
            cc = output_dict["customer_context"]
            if len(cc.get("related_order_ids", [])) > 5:
                cc["related_order_ids"] = cc["related_order_ids"][:5]
                
        if "product_context" in output_dict:
            pc = output_dict["product_context"]
            if len(pc.get("product_ids", [])) > 5:
                pc["product_ids"] = pc["product_ids"][:5]
            if len(pc.get("category_names", [])) > 5:
                pc["category_names"] = pc["category_names"][:5]
                
        if "root_cause_analysis" in output_dict:
            rc = output_dict["root_cause_analysis"]
            if len(rc.get("ranked_causes", [])) > 3:
                rc["ranked_causes"] = rc["ranked_causes"][:3]
            if len(rc.get("responsible_parties", [])) > 3:
                rc["responsible_parties"] = rc["responsible_parties"][:3]
                
        if len(output_dict.get("evidence_ids", [])) > 20:
            output_dict["evidence_ids"] = output_dict["evidence_ids"][:20]
            
        if len(output_dict.get("resolution_actions", [])) > 5:
            output_dict["resolution_actions"] = output_dict["resolution_actions"][:5]
            
        conf = output_dict.get("case_assessment", {}).get("confidence", 0.95)
        if conf < 0: conf = 0.0
        elif conf > 1: conf = 1.0
        output_dict["case_assessment"]["confidence"] = round(conf, 2)
        
        return output_dict
