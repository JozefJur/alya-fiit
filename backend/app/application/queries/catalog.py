"""Catalog read side: filter building and paginated search."""

from __future__ import annotations

from sqlalchemy import ColumnElement, UnaryExpression, literal, select

from app.application.commands.commands import CatalogQuery
from app.domain.errors import ValidationError
from app.infrastructure.persistence.models import Product, ProductVariant, StockLevel
from app.infrastructure.repositories.catalog import Page, ProductRepository

MAX_PAGE_SIZE = 60

_SORTS: dict[str, UnaryExpression | ColumnElement] = {}


def _sorts() -> dict[str, UnaryExpression | ColumnElement]:
    # built lazily so model columns exist when this module is imported early
    if not _SORTS:
        _SORTS.update(
            {
                "name": Product.name.asc(),
                "price_asc": Product.base_price.asc(),
                "price_desc": Product.base_price.asc(),
                "newest": Product.created_at.desc(),
            }
        )
    return _SORTS


class CatalogFilterBuilder:
    """Translates a ``CatalogQuery`` into SQLAlchemy criteria + ordering."""

    def build_criteria(self, query: CatalogQuery) -> list[ColumnElement[bool]]:
        criteria: list[ColumnElement[bool]] = []
        if not query.include_inactive:
            criteria.append(Product.is_active.is_(True))
        if query.search:
            term = f"%{query.search.strip()}%"
            criteria.append(Product.name.ilike(term) | Product.brand.ilike(term))
        if query.category_id is not None:
            criteria.append(Product.category_id == query.category_id)
        if query.brand:
            criteria.append(Product.brand == query.brand)
        if query.price_min is not None:
            criteria.append(Product.base_price >= query.price_min)
        if query.price_max is not None:
            criteria.append(Product.base_price <= query.price_max)
        if (
            query.price_min is not None
            and query.price_max is not None
            and query.price_min > query.price_max
        ):
            raise ValidationError("price_min must not exceed price_max.")
        if query.in_stock_only:
            criteria.append(self._has_available_variant())
        return criteria

    def build_order(self, query: CatalogQuery) -> ColumnElement:
        try:
            return _sorts()[query.sort]
        except KeyError:
            raise ValidationError(
                f"Unknown sort '{query.sort}'.",
                details={"allowed": sorted(_sorts())},
            ) from None

    @staticmethod
    def _has_available_variant() -> ColumnElement[bool]:
        return (
            select(literal(1))
            .select_from(ProductVariant)
            .join(StockLevel, StockLevel.variant_id == ProductVariant.id)
            .where(
                ProductVariant.product_id == Product.id,
                ProductVariant.is_active.is_(True),
                (StockLevel.on_hand - StockLevel.reserved) > 0,
            )
            .exists()
        )


class ProductSearchService:
    """Validated, paginated catalog search over the repository."""

    def __init__(
        self, products: ProductRepository, filter_builder: CatalogFilterBuilder | None = None
    ) -> None:
        self._products = products
        self._filters = filter_builder or CatalogFilterBuilder()

    def search(self, query: CatalogQuery) -> Page:
        if query.page < 1:
            raise ValidationError("page must be >= 1.", details={"page": query.page})
        if not (1 <= query.page_size <= MAX_PAGE_SIZE):
            raise ValidationError(
                f"page_size must be within 1..{MAX_PAGE_SIZE}.",
                details={"page_size": query.page_size},
            )
        criteria = self._filters.build_criteria(query)
        order = self._filters.build_order(query)
        return self._products.search(
            criteria, order_by=order, page=query.page, page_size=query.page_size
        )
