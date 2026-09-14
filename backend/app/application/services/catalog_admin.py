"""Administrator-side catalog management: products, variants, coupons, imports."""

from __future__ import annotations

import csv
import io
import re
import unicodedata
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from app.application.commands.commands import ProductImportRow
from app.application.services.audit import AuditLogService
from app.config import Settings
from app.domain.entities.enums import DiscountType
from app.domain.errors import ConflictError, CsvImportError, ValidationError
from app.infrastructure.persistence.models import (
    Coupon,
    Product,
    ProductVariant,
    StockLevel,
)
from app.infrastructure.repositories.catalog import (
    CategoryRepository,
    ProductRepository,
    VariantRepository,
)
from app.infrastructure.repositories.coupons import CouponRepository
from app.infrastructure.repositories.inventory import StockLevelRepository

_SLUG_STRIP = re.compile(r"[^a-z0-9]+")


def slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    slug = _SLUG_STRIP.sub("-", normalized.lower()).strip("-")
    return slug or "item"


@dataclass(frozen=True)
class ProductImportIssue:
    line: int
    field: str
    message: str


@dataclass
class ProductImportReport:
    created: int = 0
    issues: list[ProductImportIssue] = field(default_factory=list)


class ProductImportValidator:
    """Validates rows of an admin product-import CSV.

    Columns: ``category_slug,name,brand,base_price[,vat_rate][,description]``.
    """

    def __init__(self, categories: CategoryRepository, settings: Settings) -> None:
        self._categories = categories
        self._settings = settings

    def validate(
        self, rows: list[ProductImportRow], existing_slugs: set[str]
    ) -> tuple[list[dict], list[ProductImportIssue]]:
        issues: list[ProductImportIssue] = []
        prepared: list[dict] = []
        seen: set[str] = set()
        for row in rows:
            row_issues = []
            if not row.name.strip():
                row_issues.append(ProductImportIssue(row.line_number, "name", "Name is required."))
            if not row.brand.strip():
                row_issues.append(
                    ProductImportIssue(row.line_number, "brand", "Brand is required.")
                )

            category = self._categories.get_by_slug(row.category_slug.strip())
            if category is None or not category.is_active:
                row_issues.append(
                    ProductImportIssue(
                        row.line_number,
                        "category_slug",
                        f"Unknown or inactive category '{row.category_slug}'.",
                    )
                )

            price: Decimal | None = None
            try:
                price = Decimal(row.base_price)
                if not price.is_finite():
                    raise InvalidOperation
                if price <= 0:
                    row_issues.append(
                        ProductImportIssue(row.line_number, "base_price", "Price must be positive.")
                    )
                elif price != price.quantize(Decimal("0.01")):
                    row_issues.append(
                        ProductImportIssue(
                            row.line_number, "base_price", "Use at most 2 decimal places."
                        )
                    )
            except InvalidOperation:
                row_issues.append(
                    ProductImportIssue(
                        row.line_number, "base_price", f"'{row.base_price}' is not a number."
                    )
                )

            vat_rate = self._settings.vat_rate
            if row.vat_rate.strip():
                try:
                    vat_rate = Decimal(row.vat_rate)
                    if not (Decimal("0") <= vat_rate < Decimal("1")):
                        row_issues.append(
                            ProductImportIssue(
                                row.line_number, "vat_rate", "VAT rate must be within <0, 1)."
                            )
                        )
                except InvalidOperation:
                    row_issues.append(
                        ProductImportIssue(
                            row.line_number, "vat_rate", f"'{row.vat_rate}' is not a number."
                        )
                    )

            slug = slugify(f"{row.brand}-{row.name}")
            if slug in existing_slugs or slug in seen:
                row_issues.append(
                    ProductImportIssue(
                        row.line_number,
                        "name",
                        f"A product with slug '{slug}' already exists.",
                    )
                )

            # category/price are None exactly when the checks above recorded an
            # issue for them; the combined condition keeps mypy happy too.
            if row_issues or category is None or price is None:
                issues.extend(row_issues)
                continue
            seen.add(slug)
            prepared.append(
                {
                    "line": row.line_number,
                    "category_id": category.id,
                    "name": row.name.strip(),
                    "brand": row.brand.strip(),
                    "slug": slug,
                    "base_price": price,
                    "vat_rate": vat_rate,
                    "description": row.description.strip(),
                }
            )
        return prepared, issues


class CatalogAdminService:
    """Create/update operations for the admin UI (audited)."""

    def __init__(
        self,
        categories: CategoryRepository,
        products: ProductRepository,
        variants: VariantRepository,
        stock_levels: StockLevelRepository,
        coupons: CouponRepository,
        import_validator: ProductImportValidator,
        audit: AuditLogService,
    ) -> None:
        self._categories = categories
        self._products = products
        self._variants = variants
        self._stock_levels = stock_levels
        self._coupons = coupons
        self._import_validator = import_validator
        self._audit = audit

    # -- products ------------------------------------------------------

    def create_product(
        self,
        *,
        actor_user_id: int,
        category_id: int,
        name: str,
        brand: str,
        base_price: Decimal,
        vat_rate: Decimal,
        description: str = "",
    ) -> Product:
        category = self._categories.get(category_id)
        if base_price <= 0:
            raise ValidationError("Base price must be positive.")
        slug = slugify(f"{brand}-{name}")
        if self._products.get_by_slug(slug) is not None:
            raise ConflictError(f"A product with slug '{slug}' already exists.")
        product = Product(
            category_id=category.id,
            name=name.strip(),
            slug=slug,
            brand=brand.strip(),
            base_price=base_price,
            vat_rate=vat_rate,
            description=description,
        )
        self._products.add(product)
        self._audit.record(
            actor_user_id=actor_user_id,
            action="product.created",
            entity_type="product",
            entity_id=product.id,
            details={"name": product.name, "slug": slug},
        )
        return product

    def update_product(
        self,
        product_id: int,
        *,
        actor_user_id: int,
        name: str | None = None,
        brand: str | None = None,
        description: str | None = None,
        base_price: Decimal | None = None,
        vat_rate: Decimal | None = None,
        category_id: int | None = None,
        is_active: bool | None = None,
    ) -> Product:
        product = self._products.get(product_id)
        changes: dict[str, object] = {}
        if name is not None and name.strip():
            product.name, changes["name"] = name.strip(), name.strip()
        if brand is not None and brand.strip():
            product.brand, changes["brand"] = brand.strip(), brand.strip()
        if description is not None:
            product.description, changes["description"] = description, "updated"
        if base_price is not None:
            if base_price <= 0:
                raise ValidationError("Base price must be positive.")
            product.base_price, changes["base_price"] = base_price, str(base_price)
        if vat_rate is not None:
            if not (Decimal("0") <= vat_rate < Decimal("1")):
                raise ValidationError("VAT rate must be within <0, 1).")
            product.vat_rate, changes["vat_rate"] = vat_rate, str(vat_rate)
        if category_id is not None:
            product.category_id = self._categories.get(category_id).id
            changes["category_id"] = category_id
        if is_active is not None:
            product.is_active, changes["is_active"] = is_active, is_active
        if not changes:
            raise ValidationError("Nothing to update.")
        self._audit.record(
            actor_user_id=actor_user_id,
            action="product.updated",
            entity_type="product",
            entity_id=product.id,
            details=changes,
        )
        return product

    # -- variants ------------------------------------------------------

    def create_variant(
        self,
        product_id: int,
        *,
        actor_user_id: int,
        sku: str,
        name: str,
        price_delta: Decimal,
        attributes: dict | None = None,
        initial_on_hand: int = 0,
        low_stock_threshold: int | None = None,
    ) -> ProductVariant:
        product = self._products.get(product_id)
        sku = sku.strip().upper()
        if not sku:
            raise ValidationError("SKU is required.")
        if self._variants.get_by_sku(sku) is not None:
            raise ConflictError(f"SKU '{sku}' already exists.")
        if initial_on_hand < 0:
            raise ValidationError("Initial stock must be >= 0.")
        if product.base_price + price_delta <= 0:
            raise ValidationError("Effective price (base + delta) must be positive.")
        variant = ProductVariant(
            product_id=product.id,
            sku=sku,
            name=name.strip() or sku,
            price_delta=price_delta,
            attributes_json=attributes or {},
        )
        self._variants.add(variant)
        self._stock_levels.add(
            StockLevel(
                variant_id=variant.id,
                on_hand=initial_on_hand,
                low_stock_threshold=low_stock_threshold,
            )
        )
        self._audit.record(
            actor_user_id=actor_user_id,
            action="variant.created",
            entity_type="variant",
            entity_id=variant.id,
            details={"sku": sku, "product_id": product.id},
        )
        return variant

    def update_variant(
        self,
        variant_id: int,
        *,
        actor_user_id: int,
        name: str | None = None,
        price_delta: Decimal | None = None,
        is_active: bool | None = None,
    ) -> ProductVariant:
        variant = self._variants.get(variant_id)
        changes: dict[str, object] = {}
        if name is not None and name.strip():
            variant.name, changes["name"] = name.strip(), name.strip()
        if price_delta is not None:
            if variant.product.base_price + price_delta <= 0:
                raise ValidationError("Effective price (base + delta) must be positive.")
            variant.price_delta, changes["price_delta"] = price_delta, str(price_delta)
        if is_active is not None:
            variant.is_active, changes["is_active"] = is_active, is_active
        if not changes:
            raise ValidationError("Nothing to update.")
        self._audit.record(
            actor_user_id=actor_user_id,
            action="variant.updated",
            entity_type="variant",
            entity_id=variant.id,
            details=changes,
        )
        return variant

    # -- coupons -------------------------------------------------------

    def create_coupon(
        self,
        *,
        actor_user_id: int,
        code: str,
        discount_type: DiscountType,
        value: Decimal,
        valid_from,
        valid_until,
        min_cart_total: Decimal | None,
        max_uses: int | None,
        category_id: int | None,
    ) -> Coupon:
        code = code.strip().upper()
        if not code:
            raise ValidationError("Coupon code is required.")
        if self._coupons.get_by_code(code) is not None:
            raise ConflictError(f"Coupon '{code}' already exists.")
        if discount_type == DiscountType.PERCENT and not (0 < value <= 100):
            raise ValidationError("Percent value must be within (0, 100>.")
        if discount_type == DiscountType.FIXED and value <= 0:
            raise ValidationError("Fixed discount must be positive.")
        if valid_until < valid_from:
            raise ValidationError("valid_until must not be before valid_from.")
        if max_uses is not None and max_uses < 1:
            raise ValidationError("max_uses must be >= 1 (or empty).")
        if category_id is not None:
            self._categories.get(category_id)
        coupon = Coupon(
            code=code,
            discount_type=discount_type,
            value=value,
            valid_from=valid_from,
            valid_until=valid_until,
            min_cart_total=min_cart_total,
            max_uses=max_uses,
            category_id=category_id,
        )
        self._coupons.add(coupon)
        self._audit.record(
            actor_user_id=actor_user_id,
            action="coupon.created",
            entity_type="coupon",
            entity_id=coupon.id,
            details={"code": code, "type": discount_type.value, "value": str(value)},
        )
        return coupon

    def set_coupon_active(self, coupon_id: int, *, actor_user_id: int, is_active: bool) -> Coupon:
        coupon = self._coupons.get(coupon_id)
        coupon.is_active = is_active
        self._audit.record(
            actor_user_id=actor_user_id,
            action="coupon.updated",
            entity_type="coupon",
            entity_id=coupon.id,
            details={"is_active": is_active},
        )
        return coupon

    # -- product CSV import -------------------------------------------

    def import_products_csv(self, csv_text: str, *, actor_user_id: int) -> ProductImportReport:
        reader = csv.DictReader(io.StringIO(csv_text))
        if reader.fieldnames is None:
            raise ValidationError("The CSV file is empty.")
        required = {"category_slug", "name", "brand", "base_price"}
        normalized = {(name or "").strip().lower() for name in reader.fieldnames}
        missing = required - normalized
        if missing:
            raise ValidationError(f"Missing required CSV columns: {', '.join(sorted(missing))}.")
        rows = [
            ProductImportRow(
                line_number=index + 2,
                category_slug=(raw.get("category_slug") or "").strip(),
                name=(raw.get("name") or "").strip(),
                brand=(raw.get("brand") or "").strip(),
                base_price=(raw.get("base_price") or "").strip(),
                vat_rate=(raw.get("vat_rate") or "").strip(),
                description=(raw.get("description") or "").strip(),
            )
            for index, raw in enumerate(reader)
        ]
        existing_slugs = {product.slug for product in self._products.list_all()}
        prepared, issues = self._import_validator.validate(rows, existing_slugs)
        if issues:
            raise CsvImportError(
                "Product import rejected: the file contains invalid rows.",
                details={
                    "row_errors": [
                        {"line": issue.line, "field": issue.field, "message": issue.message}
                        for issue in issues
                    ]
                },
            )
        report = ProductImportReport()
        for row in prepared:
            self._products.add(
                Product(
                    category_id=row["category_id"],
                    name=row["name"],
                    slug=row["slug"],
                    brand=row["brand"],
                    base_price=row["base_price"],
                    vat_rate=row["vat_rate"],
                    description=row["description"],
                )
            )
            report.created += 1
        self._audit.record(
            actor_user_id=actor_user_id,
            action="product.imported",
            entity_type="product",
            entity_id="csv",
            details={"created": report.created},
        )
        return report
