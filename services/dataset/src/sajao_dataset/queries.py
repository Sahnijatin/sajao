"""Pinned search queries. Changing the list means a new query set version."""

from sajao_dataset.manifest import Category

QUERY_SET = "youtube-v4"

# Priority category: empty or newly handed-over homes. They show bare walls, floors,
# windows and doors, which is what the twin's room shell and the new-home buyer need.
PRIORITY_QUERIES: tuple[str, ...] = (
    "empty flat tour india",
    "empty 2bhk flat tour india",
    "empty 3bhk flat tour india",
    "unfurnished flat tour india",
    "new flat tour before interior india",
    "bare flat tour india",
    "possession day flat tour india",
    "flat handover tour india",
    "new home tour empty india",
    "empty house tour india",
    "khali flat tour india",
    "खाली फ्लैट टूर",
    "नया फ्लैट टूर",
)

QUERIES: tuple[str, ...] = (
    # Whole-home tours by city and size.
    "indian home tour",
    "1bhk flat tour india",
    "2bhk flat tour mumbai",
    "2bhk apartment tour bangalore",
    "3bhk flat tour delhi",
    "3bhk apartment tour hyderabad",
    "home tour pune flat",
    "home tour chennai apartment",
    "home tour kolkata flat",
    "home tour ahmedabad",
    "home tour gurgaon noida flat",
    "home tour jaipur house",
    "kerala house tour interior",
    "independent house tour india",
    "rented flat tour india",
    "small apartment tour india",
    "mumbai chawl room tour",
    # Rooms and styles.
    "indian living room tour",
    "indian bedroom tour",
    "indian kitchen tour",
    "pooja room tour home",
    "balcony tour india apartment",
    "kids room tour india",
    "minimalist indian home tour",
    "traditional indian home tour",
    "budget home decor india home tour",
    "before after room makeover india",
    "interior designer home tour india",
    # Hindi.
    "home tour in hindi",
    "ghar ka tour",
    "मेरा घर टूर",
    "होम टूर",
    "2 बीएचके फ्लैट टूर",
    "किचन टूर",
    "बेडरूम टूर",
    "घर की सजावट टूर",
)

ALL_QUERIES: tuple[str, ...] = PRIORITY_QUERIES + QUERIES


def category_of(query: str) -> Category:
    return "empty_new_build" if query in PRIORITY_QUERIES else "general"
