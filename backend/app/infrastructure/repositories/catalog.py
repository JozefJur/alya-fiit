"""Catalog persistence: categories, products, variants."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.orm import Session, selectinload

from app.domain.errors import NotFoundError
from app.infrastructure.persistence.models import Category, Product, ProductVariant


@dataclass(frozen=True)
class Page:
    items: list[Product]
    total: int
    page: int
    page_size: int


class CategoryRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, category_id: int) -> Category:
        category = self.session.get(Category, category_id)
        if category is None:
            raise NotFoundError("Category not found.", details={"category_id": category_id})
        return category

    def get_by_slug(self, slug: str) -> Category | None:
        return self.session.scalars(select(Category).where(Category.slug == slug)).first()

    def list_active(self) -> list[Category]:
        stmt = select(Category).where(Category.is_active.is_(True)).order_by(Category.name)
        return list(self.session.scalars(stmt))

    def list_all(self) -> list[Category]:
        return list(self.session.scalars(select(Category).order_by(Category.name)))

    def add(self, category: Category) -> Category:
        self.session.add(category)
        self.session.flush()
        return category


class ProductRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, product_id: int, *, with_variants: bool = True) -> Product:
        stmt = select(Product).where(Product.id == product_id)
        if with_variants:
            stmt = stmt.options(
                selectinload(Product.variants).selectinload(ProductVariant.stock_level),
                selectinload(Product.category),
            )
        product = self.session.scalars(stmt).first()
        if product is None:
            raise NotFoundError("Product not found.", details={"product_id": product_id})
        return product

    def get_by_slug(self, slug: str) -> Product | None:
        return self.session.scalars(select(Product).where(Product.slug == slug)).first()

    def search(
        self,
        criteria: Sequence[ColumnElement[bool]],
        *,
        order_by: ColumnElement | None,
        page: int,
        page_size: int,
    ) -> Page:
        """Run a filtered, paginated catalog query (criteria built by CatalogFilterBuilder)."""
        base = select(Product).where(*criteria)
        total = self.session.scalar(select(func.count()).select_from(base.subquery())) or 0
        stmt = (
            base.options(
                selectinload(Product.variants).selectinload(ProductVariant.stock_level),
                selectinload(Product.category),
            )
            .order_by(order_by if order_by is not None else Product.name)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        items = list(self.session.scalars(stmt))
        return Page(items=items, total=total, page=page, page_size=page_size)

    def list_all(self) -> list[Product]:
        stmt = select(Product).options(selectinload(Product.variants)).order_by(Product.id)
        return list(self.session.scalars(stmt))

    def list_brands(self) -> list[str]:
        stmt = select(Product.brand).distinct().order_by(Product.brand)
        return list(self.session.scalars(stmt))

    def add(self, product: Product) -> Product:
        self.session.add(product)
        self.session.flush()
        return product


class VariantRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, variant_id: int) -> ProductVariant:
        stmt = (
            select(ProductVariant)
            .where(ProductVariant.id == variant_id)
            .options(
                selectinload(ProductVariant.product).selectinload(Product.category),
                selectinload(ProductVariant.stock_level),
            )
        )
        variant = self.session.scalars(stmt).first()
        if variant is None:
            raise NotFoundError("Product variant not found.", details={"variant_id": variant_id})
        return variant

    def get_by_sku(self, sku: str) -> ProductVariant | None:
        stmt = select(ProductVariant).where(ProductVariant.sku == sku)
        return self.session.scalars(stmt).first()

    def list_for_product(self, product_id: int) -> list[ProductVariant]:
        stmt = (
            select(ProductVariant)
            .where(ProductVariant.product_id == product_id)
            .order_by(ProductVariant.id)
        )
        return list(self.session.scalars(stmt))

    def add(self, variant: ProductVariant) -> ProductVariant:
        self.session.add(variant)
        self.session.flush()
        return variant
