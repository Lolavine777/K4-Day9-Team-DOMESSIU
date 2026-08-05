import os
import pandas as pd

class DataLoader:
    def __init__(self, data_dir="./data"):
        self.data_dir = data_dir
        print("Loading datasets...")
        
        # Load datasets
        self.orders = pd.read_csv(os.path.join(data_dir, "olist_orders_dataset.csv"))
        self.customers = pd.read_csv(os.path.join(data_dir, "olist_customers_dataset.csv"))
        self.order_items = pd.read_csv(os.path.join(data_dir, "olist_order_items_dataset.csv"))
        self.order_payments = pd.read_csv(os.path.join(data_dir, "olist_order_payments_dataset.csv"))
        self.order_reviews = pd.read_csv(os.path.join(data_dir, "olist_order_reviews_dataset.csv"))
        self.products = pd.read_csv(os.path.join(data_dir, "olist_products_dataset.csv"))
        self.sellers = pd.read_csv(os.path.join(data_dir, "olist_sellers_dataset.csv"))
        self.translation = pd.read_csv(os.path.join(data_dir, "product_category_name_translation.csv"))
        
        # Build category translation dictionary
        self.cat_translation = dict(zip(self.translation['product_category_name'], self.translation['product_category_name_english']))
        
        # Create indexes for fast lookup
        self.orders_indexed = self.orders.set_index('order_id')
        self.customers_indexed = self.customers.set_index('customer_id')
        
        print("Datasets loaded successfully.")

    def get_order_by_id(self, order_id):
        if order_id in self.orders_indexed.index:
            return self.orders_indexed.loc[order_id].to_dict()
        return None

    def get_customer_by_id(self, customer_id):
        if customer_id in self.customers_indexed.index:
            return self.customers_indexed.loc[customer_id].to_dict()
        return None

    def get_customer_unique_id(self, order_id):
        order = self.get_order_by_id(order_id)
        if order:
            customer_id = order['customer_id']
            customer = self.get_customer_by_id(customer_id)
            if customer:
                return customer['customer_unique_id']
        return None

    def get_customer_orders_history(self, customer_unique_id, exclude_order_id=None):
        # Find all customer_ids for this unique customer
        cust_ids = self.customers[self.customers['customer_unique_id'] == customer_unique_id]['customer_id'].tolist()
        # Find all orders for these customer_ids
        cust_orders = self.orders[self.orders['customer_id'].isin(cust_ids)]
        # Get order list
        order_list = []
        for _, row in cust_orders.iterrows():
            o_id = row['order_id']
            if exclude_order_id and o_id == exclude_order_id:
                continue
            order_list.append(row.to_dict())
        return order_list

    def get_order_items(self, order_id):
        items = self.order_items[self.order_items['order_id'] == order_id]
        return items.to_dict(orient='records')

    def get_order_payments(self, order_id):
        payments = self.order_payments[self.order_payments['order_id'] == order_id]
        return payments.to_dict(orient='records')

    def get_product_by_id(self, product_id):
        prod = self.products[self.products['product_id'] == product_id]
        if not prod.empty:
            p_dict = prod.iloc[0].to_dict()
            # Add translation
            cat_name = p_dict.get('product_category_name')
            p_dict['product_category_name_english'] = self.cat_translation.get(cat_name, cat_name)
            return p_dict
        return None

    def get_seller_by_id(self, seller_id):
        sel = self.sellers[self.sellers['seller_id'] == seller_id]
        if not sel.empty:
            return sel.iloc[0].to_dict()
        return None
