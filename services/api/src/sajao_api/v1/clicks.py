"""Buy and rent taps from a design's shopping list.

The phone sends the tap with a click id it chose; the API checks the product
is in the caller's design and in stock, logs the tap, and returns the link to
open in a controlled browser tab. A repeated tap returns the same link.
"""

from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from sajao_api.auth import Principal, current_user
from sajao_api.clicks import Click, ClickStore, click_url, find_route
from sajao_api.errors import ApiError
from sajao_api.rooms import RoomStore
from sajao_api.v1.rooms import get_rooms

router = APIRouter(prefix="/clicks", tags=["clicks"])


class Tap(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    """The click id, chosen by the phone; tapping again with it returns the same link."""
    design_request_id: UUID
    design_id: UUID
    product_id: UUID
    position: int = Field(ge=0)
    """Position of the tapped item in its list."""
    kind: Literal["buy", "rent"] = "buy"


class Price(BaseModel):
    currency: Literal["INR"]
    amount_minor: int


class Opened(BaseModel):
    id: str
    url: str
    """Open this in a controlled browser tab; the retailer's app takes it where installed."""
    retailer: str
    kind: str
    price: Price


def get_clicks(request: Request) -> ClickStore:
    store: ClickStore = request.app.state.clicks
    return store


User = Annotated[Principal, Depends(current_user)]
Rooms = Annotated[RoomStore, Depends(get_rooms)]
Clicks = Annotated[ClickStore, Depends(get_clicks)]


def _opened(click: Click) -> Opened:
    return Opened(
        id=click.click_id,
        url=click.url,
        retailer=click.retailer,
        kind=click.kind,
        price=Price(currency="INR", amount_minor=click.price_minor),
    )


@router.post("", operation_id="openProduct", status_code=201)
async def open_product(
    body: Tap, user: User, rooms: Rooms, clicks: Clicks, response: Response
) -> Opened:
    """Log a buy or rent tap and return the retailer link for it. Safe to repeat."""
    request = await rooms.get_design_request(str(body.design_request_id), user.user_id)
    designs: list[dict[str, Any]] = (request.designs or []) if request is not None else []
    design, product, route = find_route(
        designs, str(body.design_id), str(body.product_id), body.kind
    )
    if design is None:
        raise ApiError(404, "design_not_found", "This design does not exist.")
    if product is None:
        raise ApiError(404, "product_not_in_design", "This product is not in the design.")
    if route is None:
        raise ApiError(404, "route_not_found", f"This product has no {body.kind} link.")
    if not product.get("in_stock", False):
        raise ApiError(409, "product_unavailable", "This product is out of stock.")

    click_id = str(body.id)
    click = Click(
        click_id=click_id,
        user_id=user.user_id,
        design_request_id=str(body.design_request_id),
        design_id=str(body.design_id),
        product_id=str(body.product_id),
        position=body.position,
        kind=body.kind,
        retailer=route["retailer"],
        url=click_url(route["url"], route["retailer"], click_id),
        price_minor=int(route["price"]["amount_minor"]),
    )
    held, created = await clicks.record(click)
    if not held.same_tap(click):
        raise ApiError(409, "click_id_taken", "Please tap again.")
    if not created:
        response.status_code = 200
    return _opened(held)
