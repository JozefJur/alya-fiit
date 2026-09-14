"""seed-small: the deterministic development and test dataset.

An electronics catalog, the fixed local accounts, coupons covering every
validity rule, and a handful of orders in different lifecycle states. Orders
are created through the real checkout and fulfillment services, so the seeded
data satisfies the same invariants as data created through the application.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from app.application.commands.commands import CheckoutCommand, ShippingAddress
from app.config import get_settings
from app.domain.entities.enums import DiscountType, UserRole
from app.infrastructure.adapters.payment_gateway import TOKEN_DECLINED, TOKEN_SUCCESS
from app.infrastructure.persistence.models import (
    Category,
    Coupon,
    Product,
    ProductVariant,
    StockLevel,
    User,
    utcnow,
)
from app.infrastructure.seed.accounts import ensure_seed_accounts

# ---------------------------------------------------------------------------
# Catalog data (fictional brands, EUR net prices)
# ---------------------------------------------------------------------------

#: (sku, variant name, net price delta, initial on_hand, low-stock threshold)
VariantSpec = tuple[str, str, str, int, int | None]
#: (product name, brand, net base price, description, variants)
ProductSpec = tuple[str, str, str, str, list[VariantSpec]]
#: (category name, products)
CategorySpec = tuple[str, list[ProductSpec]]

CATALOG: list[CategorySpec] = [
    (
        "Laptops",
        [
            (
                "Voltex ProBook 14",
                "Voltex",
                "899.00",
                "14-inch business laptop with an aluminium body and USB-C charging.",
                [
                    ("VPB14-16-512", "16 GB / 512 GB", "0.00", 12, None),
                    ("VPB14-32-1TB", "32 GB / 1 TB", "250.00", 5, 3),
                ],
            ),
            (
                "Voltex AirLite 13",
                "Voltex",
                "749.00",
                "Ultralight 13-inch laptop for work and travel.",
                [
                    ("VAL13-8-256", "8 GB / 256 GB", "0.00", 8, None),
                    ("VAL13-16-512", "16 GB / 512 GB", "150.00", 2, None),
                ],
            ),
            (
                "Nordica WorkStation 17",
                "Nordica",
                "1650.00",
                "17-inch workstation with a dedicated GPU for CAD and rendering.",
                [("NWS17-64-2TB", "64 GB / 2 TB", "0.00", 3, 2)],
            ),
        ],
    ),
    (
        "Monitors",
        [
            (
                "Nordica View 27",
                "Nordica",
                "289.00",
                "27-inch QHD IPS monitor with thin bezels.",
                [
                    ("NV27-QHD", "QHD 144 Hz", "0.00", 15, None),
                    ("NV27-4K", "4K 60 Hz", "90.00", 7, None),
                ],
            ),
            (
                "PixelForge 32 Curved",
                "PixelForge",
                "449.00",
                "32-inch curved VA panel for immersive work and play.",
                [("PF32-CURVE", "Standard", "0.00", 6, None)],
            ),
            (
                "PixelForge Studio 24",
                "PixelForge",
                "199.00",
                "Color-accurate 24-inch monitor for photo editing.",
                [("PF24-SRGB", "sRGB edition", "0.00", 0, None)],
            ),
        ],
    ),
    (
        "Keyboards",
        [
            (
                "ClickPro Mech TKL",
                "ClickPro",
                "89.00",
                "Tenkeyless mechanical keyboard with hot-swap switches.",
                [
                    ("CPM-TKL-RED", "Red switches", "0.00", 20, None),
                    ("CPM-TKL-BLUE", "Blue switches", "0.00", 14, None),
                ],
            ),
            (
                "ClickPro Slim Wireless",
                "ClickPro",
                "49.00",
                "Low-profile wireless keyboard with 3-device pairing.",
                [("CPS-WL-GRY", "Grey", "0.00", 25, None)],
            ),
            (
                "Nordica ErgoSplit",
                "Nordica",
                "129.00",
                "Split ergonomic keyboard with tenting kit.",
                [("NES-ERGO", "Standard", "0.00", 4, 5)],
            ),
        ],
    ),
    (
        "Mice",
        [
            (
                "ClickPro Precision X",
                "ClickPro",
                "59.00",
                "Lightweight gaming mouse with a 26k DPI sensor.",
                [
                    ("CPX-BLACK", "Black", "0.00", 30, None),
                    ("CPX-WHITE", "White", "0.00", 11, None),
                ],
            ),
            (
                "Voltex Ergo Trackball",
                "Voltex",
                "74.00",
                "Thumb-operated trackball for RSI-friendly navigation.",
                [("VET-TB", "Standard", "0.00", 9, None)],
            ),
        ],
    ),
    (
        "Headphones",
        [
            (
                "AeroSound Quiet 700",
                "AeroSound",
                "279.00",
                "Over-ear ANC headphones with 30h battery life.",
                [
                    ("ASQ700-BLK", "Black", "0.00", 10, None),
                    ("ASQ700-SND", "Sand", "0.00", 3, 4),
                ],
            ),
            (
                "AeroSound Buds Mini",
                "AeroSound",
                "99.00",
                "Compact true-wireless earbuds with wireless charging.",
                [("ASB-MINI", "Standard", "0.00", 18, None)],
            ),
        ],
    ),
    (
        "Cables & Adapters",
        [
            (
                "LinkUp USB-C Hub 8-in-1",
                "LinkUp",
                "45.00",
                "USB-C hub with HDMI 4K, card reader and 100W passthrough.",
                [("LU-HUB8", "Standard", "0.00", 40, None)],
            ),
            (
                "LinkUp HDMI 2.1 Cable 2m",
                "LinkUp",
                "15.00",
                "Certified 8K HDMI cable with braided jacket.",
                [("LU-HDMI21-2M", "2 m", "0.00", 60, None)],
            ),
            (
                "LinkUp USB-C Charge Cable 1m",
                "LinkUp",
                "9.00",
                "100W USB-C to USB-C cable, 1 meter.",
                [("LU-USBC-1M", "1 m", "0.00", 80, None)],
            ),
        ],
    ),
    (
        "Storage",
        [
            (
                "DataVault NVMe 1TB",
                "DataVault",
                "89.00",
                "PCIe 4.0 NVMe SSD, 7000 MB/s reads.",
                [
                    ("DV-NVME-1TB", "1 TB", "0.00", 22, None),
                    ("DV-NVME-2TB", "2 TB", "70.00", 8, None),
                ],
            ),
            (
                "DataVault Portable X5",
                "DataVault",
                "119.00",
                "Rugged portable USB-C SSD with IP55 rating.",
                [("DV-PORT-X5", "1 TB", "0.00", 13, None)],
            ),
        ],
    ),
    (
        "Smartphones",
        [
            (
                "Astra Nova 8",
                "Astra",
                "649.00",
                "6.4-inch OLED smartphone with a 50 MP camera.",
                [
                    ("AN8-128-BLK", "128 GB Black", "0.00", 9, None),
                    ("AN8-256-BLU", "256 GB Blue", "80.00", 6, None),
                ],
            ),
            (
                "Astra Nova 8 Lite",
                "Astra",
                "429.00",
                "Budget-friendly variant with the same display.",
                [("AN8L-128", "128 GB", "0.00", 16, None)],
            ),
        ],
    ),
]


def _seed_catalog(session: Session) -> dict[str, ProductVariant]:
    settings = get_settings()
    variants_by_sku: dict[str, ProductVariant] = {}
    for category_name, products in CATALOG:
        slug = category_name.lower().replace(" & ", "-").replace(" ", "-")
        category = Category(
            name=category_name,
            slug=slug,
            description=f"{category_name} for the Alya-FIIT shop",
        )
        session.add(category)
        session.flush()
        for name, brand, price, description, variants in products:
            product = Product(
                category_id=category.id,
                name=name,
                slug=f"{brand}-{name}".lower().replace(" ", "-"),
                brand=brand,
                base_price=Decimal(price),
                vat_rate=settings.vat_rate,
                description=description,
            )
            session.add(product)
            session.flush()
            for sku, variant_name, delta, on_hand, threshold in variants:
                variant = ProductVariant(
                    product_id=product.id,
                    sku=sku,
                    name=variant_name,
                    price_delta=Decimal(delta),
                    attributes_json={"variant": variant_name},
                )
                session.add(variant)
                session.flush()
                session.add(
                    StockLevel(
                        variant_id=variant.id,
                        on_hand=on_hand,
                        low_stock_threshold=threshold,
                    )
                )
                variants_by_sku[sku] = variant
    return variants_by_sku


def _seed_coupons(session: Session) -> int:
    now = utcnow()
    coupons = [
        Coupon(
            code="WELCOME10",
            discount_type=DiscountType.PERCENT,
            value=Decimal("10"),
            valid_from=now - timedelta(days=30),
            valid_until=now + timedelta(days=365),
            min_cart_total=None,
            max_uses=None,
        ),
        Coupon(
            code="FIIT5",
            discount_type=DiscountType.FIXED,
            value=Decimal("5.00"),
            valid_from=now - timedelta(days=30),
            valid_until=now + timedelta(days=365),
            min_cart_total=Decimal("50.00"),
            max_uses=None,
        ),
        Coupon(
            code="LAPTOP50",
            discount_type=DiscountType.FIXED,
            value=Decimal("50.00"),
            valid_from=now - timedelta(days=30),
            valid_until=now + timedelta(days=365),
            min_cart_total=Decimal("500.00"),
            max_uses=None,
            category_id=1,  # Laptops is seeded first
        ),
        Coupon(
            code="EXPIRED10",
            discount_type=DiscountType.PERCENT,
            value=Decimal("10"),
            valid_from=now - timedelta(days=90),
            valid_until=now - timedelta(days=30),
        ),
        Coupon(
            code="EXHAUSTED",
            discount_type=DiscountType.PERCENT,
            value=Decimal("15"),
            valid_from=now - timedelta(days=30),
            valid_until=now + timedelta(days=365),
            max_uses=1,
            used_count=1,
        ),
    ]
    session.add_all(coupons)
    session.flush()
    return len(coupons)


# ---------------------------------------------------------------------------
# Demo orders through the real services
# ---------------------------------------------------------------------------


def _services(session: Session):
    from app.api.dependencies.container import Services

    return Services(session, get_settings())


def _checkout(
    session: Session,
    customer: User,
    items: list[tuple[str, int]],
    *,
    payment_token: str,
    coupon: str | None = None,
):
    services = _services(session)
    variants = {sku: services.variants.get_by_sku(sku) for sku, _ in items}
    for sku, quantity in items:
        variant = variants[sku]
        if variant is None:
            raise ValueError(f"seed error: unknown SKU {sku}")
        services.cart_service.add_item(customer.id, variant.id, quantity)
    if coupon:
        services.cart_service.apply_coupon(customer.id, coupon)
    return services.checkout.checkout(
        CheckoutCommand(
            customer_id=customer.id,
            payment_token=payment_token,
            coupon_code=coupon,
            address=ShippingAddress(
                name=customer.full_name,
                street="Ilkovičova 2",
                city="Bratislava",
                zip_code="84216",
                country="SK",
            ),
        )
    )


def _seed_demo_orders(session: Session, users: dict[str, User]) -> int:
    customer1 = users["customer1@alya.test"]
    customer2 = users["customer2@alya.test"]
    warehouse = users["warehouse@alya.test"]
    services = _services(session)

    # 1) PAID order waiting for the warehouse (with a coupon).
    _checkout(
        session,
        customer1,
        [("CPM-TKL-RED", 1), ("LU-HDMI21-2M", 2)],
        payment_token=TOKEN_SUCCESS,
        coupon="WELCOME10",
    )

    # 2) PAID order from the second customer.
    _checkout(session, customer2, [("ASQ700-BLK", 1)], payment_token=TOKEN_SUCCESS)

    # 3) SHIPPED order (goes through the whole warehouse flow).
    shipped = _checkout(session, customer1, [("DV-NVME-1TB", 2)], payment_token=TOKEN_SUCCESS)
    services.picking.start_picking(shipped.id, actor=warehouse)
    services.picking.mark_ready(shipped.id, actor=warehouse)
    services.shipment.ship(shipped.id, actor=warehouse)

    # 4) DELIVERED order (return flow can start here).
    delivered = _checkout(session, customer2, [("CPX-BLACK", 1)], payment_token=TOKEN_SUCCESS)
    services.picking.start_picking(delivered.id, actor=warehouse)
    services.picking.mark_ready(delivered.id, actor=warehouse)
    services.shipment.ship(delivered.id, actor=warehouse)
    services.shipment.mark_delivered(delivered.id, actor=warehouse)

    # 5) PAYMENT_FAILED order (declined card, reservation released).
    _checkout(session, customer1, [("AN8-128-BLK", 1)], payment_token=TOKEN_DECLINED)

    # A declined payment keeps the customer's cart so they can retry. The
    # seeded environment starts from empty carts, so clear them afterwards.
    for customer in (customer1, customer2):
        services.cart_service.clear(customer.id)

    return 5


def seed_small(session: Session) -> dict[str, int]:
    """Populate an empty database; returns summary counts."""
    users = ensure_seed_accounts(session)
    variants = _seed_catalog(session)
    coupons = _seed_coupons(session)
    session.flush()
    orders = _seed_demo_orders(session, users)
    session.flush()
    customers = sum(1 for u in users.values() if u.role == UserRole.CUSTOMER)
    return {
        "users": len(users),
        "customers": customers,
        "categories": len(CATALOG),
        "products": sum(len(products) for _, products in CATALOG),
        "variants": len(variants),
        "coupons": coupons,
        "demo_orders": orders,
    }
