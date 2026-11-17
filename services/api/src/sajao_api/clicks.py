"""Buy and rent taps, logged with a click id before the phone opens the retailer.

The destination is the route of the product as the caller's design showed it,
so the link, the price and the shopping list never disagree. Where the
retailer's affiliate network takes a sub-id, the click id rides along in it.
"""

from dataclasses import dataclass
from typing import Any, Literal, Protocol
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from psycopg_pool import AsyncConnectionPool

RouteKind = Literal["buy", "rent"]

# The query parameter each retailer's affiliate network reports back with a sale.
# A retailer missing here still gets the click logged; the sale is matched by time.
CLICK_PARAM: dict[str, str] = {
    "flipkart": "affExtParam1",
    "amazon": "ascsubtag",
}


@dataclass(frozen=True)
class Click:
    click_id: str
    user_id: str
    design_request_id: str
    design_id: str
    product_id: str
    position: int
    kind: RouteKind
    retailer: str
    url: str
    price_minor: int

    def same_tap(self, other: "Click") -> bool:
        """Whether a repeat with this click id is the same tap (the link may differ only)."""
        return (
            self.user_id,
            self.design_request_id,
            self.design_id,
            self.product_id,
            self.position,
            self.kind,
        ) == (
            other.user_id,
            other.design_request_id,
            other.design_id,
            other.product_id,
            other.position,
            other.kind,
        )


def click_url(url: str, retailer: str, click_id: str) -> str:
    """The retailer link with the click id in the network's sub-id parameter, if it has one."""
    param = CLICK_PARAM.get(retailer.lower())
    if param is None:
        return url
    parts = urlsplit(url)
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k != param]
    return urlunsplit(parts._replace(query=urlencode([*query, (param, click_id)])))


def find_route(
    designs: list[dict[str, Any]], design_id: str, product_id: str, kind: RouteKind
) -> tuple[dict[str, Any] | None, dict[str, Any] | None, dict[str, Any] | None]:
    """The design, the product as that design showed it, and its route of this kind."""
    design = next((d for d in designs if d.get("id") == design_id), None)
    if design is None:
        return None, None, None
    product = next(
        (i["product"] for i in design.get("items", []) if i["product"].get("id") == product_id),
        None,
    )
    if product is None:
        return design, None, None
    route = next((r for r in product.get("routes", []) if r.get("kind") == kind), None)
    return design, product, route


class ClickStore(Protocol):
    async def record(self, click: Click) -> tuple[Click, bool]:
        """The click under this id and whether this call logged it."""
        ...

    async def get(self, click_id: str) -> Click | None: ...

    async def for_user(self, user_id: str) -> list[Click]: ...


class InMemoryClickStore:
    """For local development and tests only: state lives in one process."""

    def __init__(self) -> None:
        self._clicks: dict[str, Click] = {}

    async def record(self, click: Click) -> tuple[Click, bool]:
        held = self._clicks.get(click.click_id)
        if held is not None:
            return held, False
        self._clicks[click.click_id] = click
        return click, True

    async def get(self, click_id: str) -> Click | None:
        return self._clicks.get(click_id)

    async def for_user(self, user_id: str) -> list[Click]:
        return [c for c in self._clicks.values() if c.user_id == user_id]


_INSERT = """
insert into public.clicks (id, user_id, design_request_id, design_id, product_id,
    position, kind, retailer, url, price_minor)
values (%(click_id)s, %(user_id)s, %(design_request_id)s, %(design_id)s, %(product_id)s,
    %(position)s, %(kind)s, %(retailer)s, %(url)s, %(price_minor)s)
on conflict (id) do nothing
returning id
"""
_READ = """
select id::text, user_id::text, design_request_id::text, design_id::text,
    product_id::text, position, kind, retailer, url, price_minor
from public.clicks
where id = %(id)s
"""
_FOR_USER = """
select id::text, user_id::text, design_request_id::text, design_id::text,
    product_id::text, position, kind, retailer, url, price_minor
from public.clicks
where user_id = %(user_id)s
order by created_at desc
limit 500
"""


class PostgresClickStore:
    """Shared across API instances, so the service stays stateless."""

    def __init__(self, pool: AsyncConnectionPool) -> None:
        self._pool = pool

    async def record(self, click: Click) -> tuple[Click, bool]:
        async with self._pool.connection() as connection:
            created = await (await connection.execute(_INSERT, vars(click))).fetchone()
        held = await self.get(click.click_id)
        if held is None:
            raise RuntimeError("click not readable after it was logged")
        return held, created is not None

    async def get(self, click_id: str) -> Click | None:
        async with self._pool.connection() as connection:
            row = await (await connection.execute(_READ, {"id": click_id})).fetchone()
        return Click(*row) if row is not None else None

    async def for_user(self, user_id: str) -> list[Click]:
        async with self._pool.connection() as connection:
            rows = await (await connection.execute(_FOR_USER, {"user_id": user_id})).fetchall()
        return [Click(*row) for row in rows]
