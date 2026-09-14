"""Locust scenario for the shop: browse, cart, checkout.

    backend/.venv/bin/python -m pip install ".[loadtest]"
    backend/.venv/bin/python -m locust -f backend/locustfile.py --host http://localhost:8000

SQLite serialises writes, so the results show contention rather than the
throughput a server database would give.
"""

from __future__ import annotations

import random

from locust import HttpUser, between, task

CUSTOMERS = [("customer1@alya.test", "Customer123!"), ("customer2@alya.test", "Customer123!")]

ADDRESS = {
    "name": "Load Test",
    "street": "Ilkovičova 2",
    "city": "Bratislava",
    "zip_code": "84216",
    "country": "SK",
}


class ShopUser(HttpUser):
    wait_time = between(0.5, 2.0)

    def on_start(self) -> None:
        email, password = random.choice(CUSTOMERS)
        response = self.client.post(
            "/api/auth/login", json={"email": email, "password": password}, name="login"
        )
        self.headers = {"Authorization": f"Bearer {response.json()['access_token']}"}
        self.variant_ids: list[int] = []
        page = self.client.get(
            "/api/catalog/products", params={"page_size": 30}, name="catalog"
        ).json()
        for product in page["items"]:
            for variant in product["variants"]:
                if variant["is_active"] and variant["available"] > 0:
                    self.variant_ids.append(variant["id"])

    @task(6)
    def browse(self) -> None:
        self.client.get(
            "/api/catalog/products",
            params={"page": random.randint(1, 3), "page_size": 12},
            name="catalog",
        )

    @task(3)
    def view_cart(self) -> None:
        self.client.get("/api/cart", headers=self.headers, name="cart")

    @task(2)
    def add_to_cart(self) -> None:
        if not self.variant_ids:
            return
        self.client.post(
            "/api/cart/items",
            json={"variant_id": random.choice(self.variant_ids), "quantity": 1},
            headers=self.headers,
            name="cart:add",
        )

    @task(1)
    def checkout(self) -> None:
        if not self.variant_ids:
            return
        self.client.post(
            "/api/cart/items",
            json={"variant_id": random.choice(self.variant_ids), "quantity": 1},
            headers=self.headers,
            name="cart:add",
        )
        self.client.post(
            "/api/orders/checkout",
            json={"payment_token": "tok-success", "address": ADDRESS},
            headers=self.headers,
            name="checkout",
        )

    @task(1)
    def my_orders(self) -> None:
        self.client.get("/api/orders", headers=self.headers, name="orders")
