"""Public catalog endpoints (active items only)."""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, Query

from app.api.dependencies.container import Services, get_services
from app.api.mappers import product_out
from app.api.schemas.catalog import BrandsOut, CategoryOut, ProductOut, ProductPageOut
from app.application.commands.commands import CatalogQuery
from app.domain.errors import NotFoundError

router = APIRouter(prefix="/api/catalog", tags=["catalog"])


@router.get("/categories", response_model=list[CategoryOut])
def list_categories(services: Services = Depends(get_services)) -> list[CategoryOut]:
    return [CategoryOut.model_validate(c) for c in services.categories.list_active()]


@router.get("/brands", response_model=BrandsOut)
def list_brands(services: Services = Depends(get_services)) -> BrandsOut:
    return BrandsOut(brands=services.products.list_brands())


@router.get("/products", response_model=ProductPageOut)
def search_products(
    services: Services = Depends(get_services),
    search: str | None = Query(default=None, max_length=100),
    category_id: int | None = None,
    brand: str | None = Query(default=None, max_length=120),
    price_min: Decimal | None = Query(default=None, ge=0),
    price_max: Decimal | None = Query(default=None, ge=0),
    in_stock_only: bool = False,
    sort: str = "name",
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=12, ge=1, le=60),
) -> ProductPageOut:
    result = services.product_search.search(
        CatalogQuery(
            search=search,
            category_id=category_id,
            brand=brand,
            price_min=price_min,
            price_max=price_max,
            in_stock_only=in_stock_only,
            sort=sort,
            page=page,
            page_size=page_size,
        )
    )
    return ProductPageOut(
        items=[product_out(product) for product in result.items],
        total=result.total,
        page=result.page,
        page_size=result.page_size,
    )


@router.get("/products/{product_id}", response_model=ProductOut)
def product_detail(product_id: int, services: Services = Depends(get_services)) -> ProductOut:
    product = services.products.get(product_id)
    if not product.is_active or (product.category and not product.category.is_active):
        raise NotFoundError("Product not found.", details={"product_id": product_id})
    return product_out(product)
