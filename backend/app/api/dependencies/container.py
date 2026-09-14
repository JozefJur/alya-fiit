"""Per-request service container (simple constructor wiring, no framework).

Object construction is cheap (no I/O); everything shares the request's session
so a use case commits or rolls back as one unit.
"""

from __future__ import annotations

from fastapi import Depends
from sqlalchemy.orm import Session

from app.api.dependencies.db import get_session
from app.application.queries.catalog import CatalogFilterBuilder, ProductSearchService
from app.application.services.audit import AuditLogService
from app.application.services.auth import AuthService
from app.application.services.cart import (
    CartMergeService,
    CartService,
    CartValidator,
)
from app.application.services.catalog_admin import (
    CatalogAdminService,
    ProductImportValidator,
)
from app.application.services.csv_io import CsvExportService
from app.application.services.fulfillment import (
    DeliveryEstimateService,
    PickingService,
    ShipmentService,
)
from app.application.services.inventory import InventoryService
from app.application.services.notifications import NotificationService
from app.application.services.order_transitions import OrderTransitionExecutor
from app.application.services.orders import OrderService
from app.application.services.payments import PaymentService, RefundService
from app.application.services.pricing import (
    CartPriceCalculator,
    DiscountCalculator,
    PricingService,
    TaxCalculator,
)
from app.application.services.reports import InventoryReportService, SalesReportService
from app.application.use_cases.cancel_order import OrderCancellationService
from app.application.use_cases.checkout import CheckoutService
from app.application.use_cases.import_inventory import InventoryImportService
from app.application.use_cases.process_payment_result import PaymentResultProcessor
from app.config import Settings, get_settings
from app.domain.policies.authorization import AuthorizationPolicy
from app.domain.policies.cart import CartItemPolicy, QuantityValidator
from app.domain.policies.coupons import CouponValidator
from app.domain.policies.inventory import LowStockPolicy
from app.domain.policies.orders import OrderAccessPolicy, ReturnEligibilityPolicy
from app.domain.state_machines.order_state_machine import OrderStateMachine
from app.infrastructure.adapters.clock import SystemClock
from app.infrastructure.adapters.notification_gateway import OutboxNotificationGateway
from app.infrastructure.adapters.payment_gateway import SimulatedPaymentGateway
from app.infrastructure.repositories.carts import CartRepository
from app.infrastructure.repositories.catalog import (
    CategoryRepository,
    ProductRepository,
    VariantRepository,
)
from app.infrastructure.repositories.coupons import CouponRepository
from app.infrastructure.repositories.inventory import (
    ReservationRepository,
    StockLevelRepository,
    StockMovementRepository,
)
from app.infrastructure.repositories.orders import OrderRepository, OrderRequestRepository
from app.infrastructure.repositories.payments import PaymentRepository, RefundRepository
from app.infrastructure.repositories.platform import (
    AuditLogRepository,
    NotificationRepository,
)
from app.infrastructure.repositories.users import AddressRepository, UserRepository


class Services:
    def __init__(self, session: Session, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        clock = SystemClock()
        self.clock = clock

        # Repositories
        self.users = UserRepository(session)
        self.addresses = AddressRepository(session)
        self.categories = CategoryRepository(session)
        self.products = ProductRepository(session)
        self.variants = VariantRepository(session)
        self.stock_levels = StockLevelRepository(session)
        self.stock_movements = StockMovementRepository(session)
        self.reservations = ReservationRepository(session)
        self.carts = CartRepository(session)
        self.coupons = CouponRepository(session)
        self.orders = OrderRepository(session)
        self.order_requests = OrderRequestRepository(session)
        self.payments_repo = PaymentRepository(session)
        self.refunds_repo = RefundRepository(session)
        self.notifications_repo = NotificationRepository(session)
        self.audit_repo = AuditLogRepository(session)

        # Adapters
        self.payment_gateway = SimulatedPaymentGateway()
        self.notification_gateway = OutboxNotificationGateway(session)

        # Domain policies / machines
        self.authorization = AuthorizationPolicy()
        self.order_state_machine = OrderStateMachine(self.authorization)
        self.access_policy = OrderAccessPolicy()
        self.return_policy = ReturnEligibilityPolicy(settings.return_window_days)
        self.low_stock_policy = LowStockPolicy(settings.default_low_stock_threshold)
        self.quantity_validator = QuantityValidator(settings.max_quantity_per_line)
        self.cart_item_policy = CartItemPolicy(self.quantity_validator)
        self.coupon_validator = CouponValidator()

        # Platform services
        self.audit = AuditLogService(self.audit_repo)
        self.notifications = NotificationService(self.notification_gateway)
        self.auth = AuthService(self.users, settings, clock)
        self.transitions = OrderTransitionExecutor(self.order_state_machine, self.audit, clock)

        # Pricing
        self.tax_calculator = TaxCalculator()
        self.discount_calculator = DiscountCalculator()
        self.pricing = PricingService()
        self.calculator = CartPriceCalculator(self.tax_calculator, self.discount_calculator)

        # Catalog
        self.filter_builder = CatalogFilterBuilder()
        self.product_search = ProductSearchService(self.products, self.filter_builder)

        # Inventory
        self.inventory = InventoryService(
            self.stock_levels,
            self.stock_movements,
            self.reservations,
            self.audit,
            self.notifications,
            self.users,
            self.low_stock_policy,
            clock=clock,
        )
        self.inventory_import = InventoryImportService(
            self.variants, self.stock_levels, self.stock_movements, self.audit
        )

        # Cart
        self.cart_merge = CartMergeService(settings.max_quantity_per_line)
        self.cart_service = CartService(
            self.carts,
            self.variants,
            self.coupons,
            self.cart_item_policy,
            self.pricing,
            self.calculator,
            self.cart_merge,
            self.coupon_validator,
            clock=clock,
        )
        self.cart_validator = CartValidator(self.cart_service)

        # Payments
        self.payment_service = PaymentService(self.payments_repo, self.audit)
        self.refund_service = RefundService(
            self.payments_repo, self.refunds_repo, self.payment_gateway, self.audit, clock
        )
        self.payment_processor = PaymentResultProcessor(
            self.payments_repo,
            self.orders,
            self.coupons,
            self.inventory,
            self.notifications,
            self.transitions,
            self.audit,
        )

        # Orders & fulfillment
        self.order_service = OrderService(
            self.orders,
            self.order_requests,
            self.access_policy,
            self.return_policy,
            self.transitions,
            self.refund_service,
            self.notifications,
            self.audit,
            clock,
        )
        self.cancellation = OrderCancellationService(
            self.order_requests,
            self.inventory,
            self.payment_service,
            self.refund_service,
            self.notifications,
            self.transitions,
            self.audit,
            clock,
        )
        self.delivery_estimate = DeliveryEstimateService(settings.delivery_estimate_days)
        self.picking = PickingService(self.orders, self.transitions)
        self.shipment = ShipmentService(
            self.orders,
            self.inventory,
            self.notifications,
            self.transitions,
            self.delivery_estimate,
            clock,
        )

        # Checkout
        self.checkout = CheckoutService(
            self.cart_service,
            self.cart_validator,
            self.coupons,
            self.coupon_validator,
            self.calculator,
            self.orders,
            self.inventory,
            self.payment_service,
            self.payment_processor,
            self.payment_gateway,
            self.notifications,
            self.audit,
            self.transitions,
            settings,
            clock,
        )

        # Reporting & admin
        self.sales_report = SalesReportService(self.orders, self.variants)
        self.inventory_report = InventoryReportService(
            self.products, self.stock_levels, self.low_stock_policy
        )
        self.csv_export = CsvExportService()
        self.product_import_validator = ProductImportValidator(self.categories, settings)
        self.catalog_admin = CatalogAdminService(
            self.categories,
            self.products,
            self.variants,
            self.stock_levels,
            self.coupons,
            self.product_import_validator,
            self.audit,
        )


def get_services(
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> Services:
    return Services(session, settings)
