"""ORM → response-schema mapping (kept out of routers and services)."""

from __future__ import annotations

from app.api.schemas.admin import AuditEntryOut, CouponOut, NotificationOut
from app.api.schemas.cart import CartLineOut, CartOut, CartProblemOut
from app.api.schemas.catalog import ProductOut, VariantOut
from app.api.schemas.orders import (
    OrderDetailOut,
    OrderHistoryOut,
    OrderItemOut,
    OrderSummaryOut,
    PaymentOut,
    RequestOut,
)
from app.api.schemas.warehouse import StockLevelOut, StockMovementOut
from app.application.services.cart import PricedCart
from app.domain.policies.inventory import LowStockPolicy
from app.domain.value_objects.money import Money
from app.infrastructure.persistence.models import (
    AuditLogEntry,
    Coupon,
    Notification,
    Order,
    OrderRequest,
    Product,
    StockLevel,
    StockMovement,
)


def product_out(product: Product) -> ProductOut:
    variants = []
    for variant in product.variants:
        price = Money(product.base_price + variant.price_delta)
        gross = price + price.percentage(product.vat_rate)
        level = variant.stock_level
        variants.append(
            VariantOut(
                id=variant.id,
                sku=variant.sku,
                name=variant.name,
                attributes=variant.attributes_json or {},
                price=price.amount,
                price_with_vat=gross.amount,
                is_active=variant.is_active,
                available=max(level.available, 0) if level else 0,
            )
        )
    return ProductOut(
        id=product.id,
        name=product.name,
        slug=product.slug,
        description=product.description,
        brand=product.brand,
        category_id=product.category_id,
        category_name=product.category.name if product.category else "",
        base_price=product.base_price,
        vat_rate=product.vat_rate,
        is_active=product.is_active,
        variants=variants,
    )


def cart_out(priced: PricedCart) -> CartOut:
    breakdown = priced.breakdown
    return CartOut(
        id=priced.cart.id,
        items=[
            CartLineOut(
                variant_id=line.source.variant_id,
                product_id=line.source.product_id,
                product_name=line.source.product_name,
                sku=line.source.sku,
                quantity=line.source.quantity,
                unit_price=line.source.unit_price.amount,
                line_net=line.line_net.amount,
                discount=line.discount.amount,
                vat=line.vat.amount,
                line_total=line.line_total.amount,
            )
            for line in breakdown.lines
        ],
        subtotal=breakdown.subtotal.amount,
        discount_total=breakdown.discount_total.amount,
        vat_total=breakdown.vat_total.amount,
        grand_total=breakdown.grand_total.amount,
        coupon_code=priced.cart.coupon_code,
        coupon_error=priced.coupon_error,
        problems=[
            CartProblemOut(variant_id=p.variant_id, code=p.code, message=p.message)
            for p in priced.problems
        ],
    )


def order_summary_out(order: Order, *, include_email: bool = False) -> OrderSummaryOut:
    return OrderSummaryOut(
        id=order.id,
        order_number=order.order_number,
        status=order.status,
        grand_total=order.grand_total,
        created_at=order.created_at,
        items_count=sum(item.quantity for item in order.items),
        customer_id=order.customer_id,
        customer_email=order.customer.email if include_email and order.customer else None,
    )


def order_detail_out(
    order: Order,
    *,
    allowed_events: list[str] | None = None,
    expected_delivery: str | None = None,
) -> OrderDetailOut:
    return OrderDetailOut(
        id=order.id,
        order_number=order.order_number,
        customer_id=order.customer_id,
        status=order.status,
        subtotal=order.subtotal,
        discount_total=order.discount_total,
        vat_total=order.vat_total,
        grand_total=order.grand_total,
        coupon_code=order.coupon_code,
        ship_to_name=order.ship_to_name,
        ship_street=order.ship_street,
        ship_city=order.ship_city,
        ship_zip=order.ship_zip,
        ship_country=order.ship_country,
        created_at=order.created_at,
        shipped_at=order.shipped_at,
        delivered_at=order.delivered_at,
        expected_delivery=expected_delivery,
        items=[OrderItemOut.model_validate(item) for item in order.items],
        status_history=[OrderHistoryOut.model_validate(entry) for entry in order.status_history],
        payments=[PaymentOut.model_validate(payment) for payment in order.payments],
        allowed_events=allowed_events or [],
    )


def request_out(request: OrderRequest) -> RequestOut:
    return RequestOut(
        id=request.id,
        order_id=request.order_id,
        order_number=request.order.order_number if request.order else "",
        request_type=request.request_type,
        reason=request.reason,
        status=request.status,
        requested_by=request.requested_by,
        created_at=request.created_at,
        decided_at=request.decided_at,
        decision_note=request.decision_note,
    )


def stock_level_out(level: StockLevel, low_stock_policy: LowStockPolicy) -> StockLevelOut:
    variant = level.variant
    return StockLevelOut(
        variant_id=level.variant_id,
        sku=variant.sku if variant else "",
        product_name=variant.product.name if variant and variant.product else "",
        variant_name=variant.name if variant else "",
        on_hand=level.on_hand,
        reserved=level.reserved,
        available=level.available,
        low_stock_threshold=low_stock_policy.threshold_for(level),
        is_low_stock=low_stock_policy.is_low(level),
    )


def movement_out(movement: StockMovement) -> StockMovementOut:
    return StockMovementOut.model_validate(movement)


def coupon_out(coupon: Coupon) -> CouponOut:
    return CouponOut.model_validate(coupon)


def audit_out(entry: AuditLogEntry) -> AuditEntryOut:
    return AuditEntryOut(
        id=entry.id,
        actor_user_id=entry.actor_user_id,
        action=entry.action,
        entity_type=entry.entity_type,
        entity_id=entry.entity_id,
        details=entry.details_json or {},
        created_at=entry.created_at,
    )


def notification_out(notification: Notification) -> NotificationOut:
    return NotificationOut(
        id=notification.id,
        recipient_user_id=notification.recipient_user_id,
        notification_type=notification.notification_type,
        subject=notification.subject,
        body=notification.body,
        status=notification.status.value,
        created_at=notification.created_at,
    )
