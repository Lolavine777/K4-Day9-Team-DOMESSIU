import csv
import os
from collections import defaultdict
from typing import Dict, List, Optional, Any


class DataRepository:
    """In-memory indexing and lookup for Olist Brazilian E-Commerce dataset."""

    def __init__(self, data_dir: str = "data"):
        self.data_dir = data_dir
        self.orders_by_id: Dict[str, Dict[str, str]] = {}
        self.orders_by_customer_id: Dict[str, List[Dict[str, str]]] = defaultdict(list)
        self.items_by_order_id: Dict[str, List[Dict[str, str]]] = defaultdict(list)
        self.payments_by_order_id: Dict[str, List[Dict[str, str]]] = defaultdict(list)
        self.customers_by_id: Dict[str, Dict[str, str]] = {}
        self.customer_ids_by_unique_id: Dict[str, List[str]] = defaultdict(list)
        self.products_by_id: Dict[str, Dict[str, str]] = {}
        self.sellers_by_id: Dict[str, Dict[str, str]] = {}
        self.category_translation: Dict[str, str] = {}

        self._load_all()

    def _load_csv(self, filename: str) -> List[Dict[str, str]]:
        path = os.path.join(self.data_dir, filename)
        if not os.path.exists(path):
            return []
        with open(path, mode="r", encoding="utf-8-sig") as f:
            return list(csv.DictReader(f))

    def _load_all(self) -> None:
        # Load orders
        for row in self._load_csv("olist_orders_dataset.csv"):
            oid = row["order_id"]
            cid = row["customer_id"]
            self.orders_by_id[oid] = row
            self.orders_by_customer_id[cid].append(row)

        # Load items
        for row in self._load_csv("olist_order_items_dataset.csv"):
            self.items_by_order_id[row["order_id"]].append(row)

        # Load payments
        for row in self._load_csv("olist_order_payments_dataset.csv"):
            self.payments_by_order_id[row["order_id"]].append(row)

        # Load customers
        for row in self._load_csv("olist_customers_dataset.csv"):
            cid = row["customer_id"]
            cuid = row["customer_unique_id"]
            self.customers_by_id[cid] = row
            self.customer_ids_by_unique_id[cuid].append(cid)

        # Load products
        for row in self._load_csv("olist_products_dataset.csv"):
            self.products_by_id[row["product_id"]] = row

        # Load sellers
        for row in self._load_csv("olist_sellers_dataset.csv"):
            self.sellers_by_id[row["seller_id"]] = row

        # Load category translation
        for row in self._load_csv("product_category_name_translation.csv"):
            p_name = row.get("product_category_name")
            p_eng = row.get("product_category_name_english")
            if p_name and p_eng:
                self.category_translation[p_name] = p_eng

    def get_order(self, order_id: str) -> Optional[Dict[str, str]]:
        return self.orders_by_id.get(order_id)

    def get_items(self, order_id: str) -> List[Dict[str, str]]:
        return self.items_by_order_id.get(order_id, [])

    def get_payments(self, order_id: str) -> List[Dict[str, str]]:
        return self.payments_by_order_id.get(order_id, [])

    def get_customer(self, customer_id: str) -> Optional[Dict[str, str]]:
        return self.customers_by_id.get(customer_id)

    def get_customer_unique_id(self, customer_id: str) -> Optional[str]:
        cust = self.get_customer(customer_id)
        return cust.get("customer_unique_id") if cust else None

    def get_related_order_ids(self, customer_unique_id: str, claimed_order_id: str) -> List[str]:
        all_cids = self.customer_ids_by_unique_id.get(customer_unique_id, [])
        related_orders = []
        for cid in all_cids:
            for o in self.orders_by_customer_id.get(cid, []):
                oid = o["order_id"]
                if oid != claimed_order_id and oid not in related_orders:
                    related_orders.append(oid)
        return related_orders

    def get_product(self, product_id: str) -> Optional[Dict[str, str]]:
        return self.products_by_id.get(product_id)

    def get_translated_category(self, raw_category: str) -> str:
        if not raw_category:
            return ""
        return self.category_translation.get(raw_category, raw_category)

    def get_seller(self, seller_id: str) -> Optional[Dict[str, str]]:
        return self.sellers_by_id.get(seller_id)

    # Verification / Grounding helper methods
    def order_exists(self, order_id: str) -> bool:
        return order_id in self.orders_by_id

    def item_exists(self, order_id: str, item_id: int) -> bool:
        items = self.get_items(order_id)
        return any(int(it["order_item_id"]) == item_id for it in items)

    def payment_exists(self, order_id: str, payment_seq: int) -> bool:
        payments = self.get_payments(order_id)
        return any(int(p["payment_sequential"]) == payment_seq for p in payments)

    def seller_exists(self, seller_id: str) -> bool:
        return seller_id in self.sellers_by_id
