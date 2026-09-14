"""Administrator endpoints: catalog, coupons, users, imports, reports, audit."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import PlainTextResponse

from app.api.dependencies.auth import require_admin
from app.api.dependencies.container import Services, get_services
from app.api.mappers import (
    audit_out,
    coupon_out,
    notification_out,
    product_out,
)
from app.api.schemas.admin import (
    AdminUserOut,
    AdminUserUpdateIn,
    AuditEntryOut,
    CouponActiveIn,
    CouponCreateIn,
    CouponOut,
    NotificationOut,
    ProductCreateIn,
    ProductImportReportOut,
    ProductUpdateIn,
    VariantCreateIn,
    VariantUpdateIn,
)
from app.api.schemas.catalog import CategoryOut, ProductOut, ProductPageOut
from app.api.schemas.warehouse import ImportResultOut
from app.application.commands.commands import CatalogQuery, ReportQuery
from app.application.use_cases.inventory_sales_report import InventorySalesReport
from app.domain.errors import ValidationError
from app.infrastructure.persistence.models import User

router = APIRouter(prefix="/api/admin", tags=["admin"])

MAX_UPLOAD_BYTES = 5 * 1024 * 1024


async def _read_csv_upload(file: UploadFile) -> str:
    raw = await file.read()
    if len(raw) > MAX_UPLOAD_BYTES:
        raise ValidationError("The uploaded file is too large (max 5 MB).")
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ValidationError("The file must be UTF-8 encoded CSV.") from None


# ---------------------------------------------------------------------------
# Catalog management
# ---------------------------------------------------------------------------


@router.get("/categories", response_model=list[CategoryOut])
def all_categories(
    _user: User = Depends(require_admin), services: Services = Depends(get_services)
) -> list[CategoryOut]:
    return [CategoryOut.model_validate(c) for c in services.categories.list_all()]


@router.get("/products", response_model=ProductPageOut)
def all_products(
    _user: User = Depends(require_admin),
    services: Services = Depends(get_services),
    search: str | None = Query(default=None, max_length=100),
    category_id: int | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=60),
) -> ProductPageOut:
    result = services.product_search.search(
        CatalogQuery(
            search=search,
            category_id=category_id,
            include_inactive=True,
            page=page,
            page_size=page_size,
        )
    )
    return ProductPageOut(
        items=[product_out(p) for p in result.items],
        total=result.total,
        page=result.page,
        page_size=result.page_size,
    )


@router.post("/products", response_model=ProductOut, status_code=201)
def create_product(
    payload: ProductCreateIn,
    user: User = Depends(require_admin),
    services: Services = Depends(get_services),
) -> ProductOut:
    product = services.catalog_admin.create_product(
        actor_user_id=user.id,
        category_id=payload.category_id,
        name=payload.name,
        brand=payload.brand,
        base_price=payload.base_price,
        vat_rate=payload.vat_rate if payload.vat_rate is not None else services.settings.vat_rate,
        description=payload.description,
    )
    return product_out(services.products.get(product.id))


@router.patch("/products/{product_id}", response_model=ProductOut)
def update_product(
    product_id: int,
    payload: ProductUpdateIn,
    user: User = Depends(require_admin),
    services: Services = Depends(get_services),
) -> ProductOut:
    services.catalog_admin.update_product(
        product_id,
        actor_user_id=user.id,
        name=payload.name,
        brand=payload.brand,
        description=payload.description,
        base_price=payload.base_price,
        vat_rate=payload.vat_rate,
        category_id=payload.category_id,
        is_active=payload.is_active,
    )
    return product_out(services.products.get(product_id))


@router.post("/products/{product_id}/variants", response_model=ProductOut, status_code=201)
def create_variant(
    product_id: int,
    payload: VariantCreateIn,
    user: User = Depends(require_admin),
    services: Services = Depends(get_services),
) -> ProductOut:
    services.catalog_admin.create_variant(
        product_id,
        actor_user_id=user.id,
        sku=payload.sku,
        name=payload.name,
        price_delta=payload.price_delta,
        attributes=payload.attributes,
        initial_on_hand=payload.initial_on_hand,
        low_stock_threshold=payload.low_stock_threshold,
    )
    return product_out(services.products.get(product_id))


@router.patch("/variants/{variant_id}", response_model=ProductOut)
def update_variant(
    variant_id: int,
    payload: VariantUpdateIn,
    user: User = Depends(require_admin),
    services: Services = Depends(get_services),
) -> ProductOut:
    variant = services.catalog_admin.update_variant(
        variant_id,
        actor_user_id=user.id,
        name=payload.name,
        price_delta=payload.price_delta,
        is_active=payload.is_active,
    )
    return product_out(services.products.get(variant.product_id))


@router.post("/products/import", response_model=ProductImportReportOut)
async def import_products(
    file: UploadFile = File(...),
    user: User = Depends(require_admin),
    services: Services = Depends(get_services),
) -> ProductImportReportOut:
    csv_text = await _read_csv_upload(file)
    report = services.catalog_admin.import_products_csv(csv_text, actor_user_id=user.id)
    return ProductImportReportOut(created=report.created)


# ---------------------------------------------------------------------------
# Coupons
# ---------------------------------------------------------------------------


@router.get("/coupons", response_model=list[CouponOut])
def list_coupons(
    _user: User = Depends(require_admin), services: Services = Depends(get_services)
) -> list[CouponOut]:
    return [coupon_out(c) for c in services.coupons.list_all()]


@router.post("/coupons", response_model=CouponOut, status_code=201)
def create_coupon(
    payload: CouponCreateIn,
    user: User = Depends(require_admin),
    services: Services = Depends(get_services),
) -> CouponOut:
    coupon = services.catalog_admin.create_coupon(
        actor_user_id=user.id,
        code=payload.code,
        discount_type=payload.discount_type,
        value=payload.value,
        valid_from=payload.valid_from,
        valid_until=payload.valid_until,
        min_cart_total=payload.min_cart_total,
        max_uses=payload.max_uses,
        category_id=payload.category_id,
    )
    return coupon_out(coupon)


@router.patch("/coupons/{coupon_id}", response_model=CouponOut)
def set_coupon_active(
    coupon_id: int,
    payload: CouponActiveIn,
    user: User = Depends(require_admin),
    services: Services = Depends(get_services),
) -> CouponOut:
    return coupon_out(
        services.catalog_admin.set_coupon_active(
            coupon_id, actor_user_id=user.id, is_active=payload.is_active
        )
    )


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------


@router.get("/users", response_model=list[AdminUserOut])
def list_users(
    _user: User = Depends(require_admin), services: Services = Depends(get_services)
) -> list[AdminUserOut]:
    return [AdminUserOut.model_validate(u) for u in services.users.list_all()]


@router.patch("/users/{user_id}", response_model=AdminUserOut)
def update_user(
    user_id: int,
    payload: AdminUserUpdateIn,
    admin: User = Depends(require_admin),
    services: Services = Depends(get_services),
) -> AdminUserOut:
    target = services.users.get(user_id)
    if target.id == admin.id and payload.is_active is False:
        raise ValidationError("You cannot deactivate your own account.")
    changes: dict[str, object] = {}
    if payload.role is not None:
        target.role, changes["role"] = payload.role, payload.role.value
    if payload.is_active is not None:
        target.is_active, changes["is_active"] = payload.is_active, payload.is_active
    if not changes:
        raise ValidationError("Nothing to update.")
    services.audit.record(
        actor_user_id=admin.id,
        action="user.updated",
        entity_type="user",
        entity_id=target.id,
        details=changes,
    )
    return AdminUserOut.model_validate(target)


# ---------------------------------------------------------------------------
# Inventory import/export
# ---------------------------------------------------------------------------


@router.post("/inventory/import", response_model=ImportResultOut)
async def import_inventory(
    file: UploadFile = File(...),
    user: User = Depends(require_admin),
    services: Services = Depends(get_services),
) -> ImportResultOut:
    csv_text = await _read_csv_upload(file)
    result = services.inventory_import.import_csv(csv_text, actor_user_id=user.id)
    return ImportResultOut(
        applied=result.applied, unchanged=result.unchanged, movements=result.movements
    )


@router.get("/inventory/export.csv", response_class=PlainTextResponse)
def export_inventory(
    _user: User = Depends(require_admin), services: Services = Depends(get_services)
) -> PlainTextResponse:
    levels = services.stock_levels.list_all()
    headers = ["sku", "on_hand", "reserved", "available", "low_stock_threshold"]
    rows = [
        [
            level.variant.sku if level.variant else level.variant_id,
            level.on_hand,
            level.reserved,
            level.available,
            services.low_stock_policy.threshold_for(level),
        ]
        for level in levels
    ]
    csv_text = services.csv_export.export(headers, rows)
    return PlainTextResponse(
        csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=inventory.csv"},
    )


# ---------------------------------------------------------------------------
# Reports, audit, notifications
# ---------------------------------------------------------------------------


def _report_query(
    date_from: str, date_to: str, category_id: int | None, top_limit: int
) -> ReportQuery:
    return ReportQuery(
        date_from=date_from, date_to=date_to, category_id=category_id, top_limit=top_limit
    )


@router.get("/reports/inventory-sales")
def inventory_sales_report(
    _user: User = Depends(require_admin),
    services: Services = Depends(get_services),
    date_from: str = Query(alias="from"),
    date_to: str = Query(alias="to"),
    category_id: int | None = None,
    top_limit: int = Query(default=10, ge=1, le=50),
) -> dict:
    report = InventorySalesReport(services.sales_report, services.inventory_report)
    return report.build(_report_query(date_from, date_to, category_id, top_limit))


@router.get("/reports/inventory-sales.csv", response_class=PlainTextResponse)
def inventory_sales_report_csv(
    _user: User = Depends(require_admin),
    services: Services = Depends(get_services),
    date_from: str = Query(alias="from"),
    date_to: str = Query(alias="to"),
    category_id: int | None = None,
) -> PlainTextResponse:
    use_case = InventorySalesReport(services.sales_report, services.inventory_report)
    report = use_case.build(_report_query(date_from, date_to, category_id, 10))
    headers, rows = use_case.csv_rows(report)
    csv_text = services.csv_export.export(headers, rows)
    return PlainTextResponse(
        csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=inventory-sales.csv"},
    )


@router.get("/audit-log", response_model=list[AuditEntryOut])
def audit_log(
    _user: User = Depends(require_admin),
    services: Services = Depends(get_services),
    entity_type: str | None = None,
    entity_id: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[AuditEntryOut]:
    if entity_type and entity_id:
        entries = services.audit_repo.list_for_entity(entity_type, entity_id)
    else:
        entries = services.audit_repo.list_recent(limit)
    return [audit_out(entry) for entry in entries]


@router.get("/notifications", response_model=list[NotificationOut])
def notifications_outbox(
    _user: User = Depends(require_admin),
    services: Services = Depends(get_services),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[NotificationOut]:
    return [notification_out(n) for n in services.notifications_repo.list_recent(limit)]
