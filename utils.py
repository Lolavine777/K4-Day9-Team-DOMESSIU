from datetime import datetime
import math
import pandas as pd

def parse_datetime(dt_str):
    if pd.isna(dt_str) or not dt_str or str(dt_str).strip() == "" or str(dt_str).strip().lower() == "nan":
        return None
    try:
        return datetime.strptime(str(dt_str).strip(), "%Y-%m-%d %H:%M:%S")
    except Exception:
        try:
            return datetime.strptime(str(dt_str).strip(), "%Y-%m-%d %H:%M:%S.%f")
        except Exception:
            return None

def calculate_hours_difference(dt_str_target, dt_str_base):
    t_target = parse_datetime(dt_str_target)
    t_base = parse_datetime(dt_str_base)
    if t_target is None or t_base is None:
        return None
    delta = t_target - t_base
    hours = delta.total_seconds() / 3600.0
    return round(hours, 2)

def check_nan(val):
    if pd.isna(val):
        return None
    return val

def format_evidence_id(evidence_type, *args):
    """
    order:<order_id>
    item:<order_id>:<order_item_id>
    payment:<order_id>:<payment_sequential>
    seller:<seller_id>
    policy:<root_cause_code>
    """
    if evidence_type == "order":
        return f"order:{args[0]}"
    elif evidence_type == "item":
        return f"item:{args[0]}:{args[1]}"
    elif evidence_type == "payment":
        return f"payment:{args[0]}:{args[1]}"
    elif evidence_type == "seller":
        return f"seller:{args[0]}"
    elif evidence_type == "policy":
        return f"policy:{args[0]}"
    return ""
