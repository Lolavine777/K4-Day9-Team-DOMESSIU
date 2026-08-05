from __future__ import annotations

from pathlib import Path

import pandas as pd


CSV_FILES = {
    "customers": "olist_customers_dataset.csv",
    "geolocation": "olist_geolocation_dataset.csv",
    "items": "olist_order_items_dataset.csv",
    "orders": "olist_orders_dataset.csv",
    "payments": "olist_order_payments_dataset.csv",
    "products": "olist_products_dataset.csv",
    "reviews": "olist_order_reviews_dataset.csv",
    "sellers": "olist_sellers_dataset.csv",
    "translations": "product_category_name_translation.csv",
}


class OlistRepository:
    """Read-only indexes over the lab CSV files, retaining their source order."""

    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        frames: dict[str, pd.DataFrame] = {}
        for name, filename in CSV_FILES.items():
            path = data_dir / filename
            if not path.exists():
                raise FileNotFoundError(f"Required data file is missing: {path}")
            frames[name] = pd.read_csv(path, dtype=str, keep_default_na=False)
        self.frames = frames
        self.orders = frames["orders"].set_index("order_id", drop=False)
        self.customers = frames["customers"].set_index("customer_id", drop=False)
        self.products = frames["products"].set_index("product_id", drop=False)
        self.category_translations = dict(zip(
            frames["translations"]["product_category_name"],
            frames["translations"]["product_category_name_english"],
        ))
        self._unique_to_orders = self._build_customer_history()

    def _build_customer_history(self) -> dict[str, list[str]]:
        merged = self.frames["orders"].merge(
            self.frames["customers"][["customer_id", "customer_unique_id"]],
            on="customer_id",
            how="left",
            sort=False,
        )
        result: dict[str, list[str]] = {}
        for row in merged.itertuples(index=False):
            result.setdefault(row.customer_unique_id, []).append(row.order_id)
        return result

    def order(self, order_id: str) -> dict[str, str]:
        if order_id not in self.orders.index:
            raise KeyError(f"Order not found: {order_id}")
        return self.orders.loc[order_id].to_dict()

    def customer_for_order(self, order: dict[str, str]) -> dict[str, str]:
        customer_id = order["customer_id"]
        if customer_id not in self.customers.index:
            raise KeyError(f"Customer not found: {customer_id}")
        return self.customers.loc[customer_id].to_dict()

    def related_orders(self, customer_unique_id: str, claimed_order_id: str) -> list[str]:
        return [order_id for order_id in self._unique_to_orders.get(customer_unique_id, []) if order_id != claimed_order_id]

    def order_items(self, order_id: str) -> list[dict[str, str]]:
        frame = self.frames["items"]
        return frame.loc[frame["order_id"].eq(order_id)].to_dict("records")

    def order_payments(self, order_id: str) -> list[dict[str, str]]:
        frame = self.frames["payments"]
        return frame.loc[frame["order_id"].eq(order_id)].to_dict("records")

    def product(self, product_id: str) -> dict[str, str] | None:
        if product_id not in self.products.index:
            return None
        return self.products.loc[product_id].to_dict()

    def translated_category(self, category_name: str) -> str:
        return self.category_translations.get(category_name, category_name)
