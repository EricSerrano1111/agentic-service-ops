"""Static lookups for generate.py: state timezones and cities, name and address parts.

Committed literals, no randomness. generate.py draws from these lists with its own
seeded stage generators, so changing a list changes the dataset: treat an edit here like
a parameter change.

Every name is generic and fictional in combination (R-08). Contact phone numbers use the
555-0100 to 555-0199 block reserved for fiction, and emails use example.com (§9).
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

#: One IANA zone per state: the zone most of the state's population is in. Split states
#: (TX, FL, KY, TN, IN, MI, ND, SD, NE, KS, ID, OR, AK) are simplified to that zone.
STATE_TIMEZONE: Mapping[str, str] = MappingProxyType(
    {
        "AK": "America/Anchorage",
        "AL": "America/Chicago",
        "AR": "America/Chicago",
        "AZ": "America/Phoenix",
        "CA": "America/Los_Angeles",
        "CO": "America/Denver",
        "CT": "America/New_York",
        "DC": "America/New_York",
        "DE": "America/New_York",
        "FL": "America/New_York",
        "GA": "America/New_York",
        "HI": "Pacific/Honolulu",
        "IA": "America/Chicago",
        "ID": "America/Boise",
        "IL": "America/Chicago",
        "IN": "America/Indiana/Indianapolis",
        "KS": "America/Chicago",
        "KY": "America/New_York",
        "LA": "America/Chicago",
        "MA": "America/New_York",
        "MD": "America/New_York",
        "ME": "America/New_York",
        "MI": "America/Detroit",
        "MN": "America/Chicago",
        "MO": "America/Chicago",
        "MS": "America/Chicago",
        "MT": "America/Denver",
        "NC": "America/New_York",
        "ND": "America/Chicago",
        "NE": "America/Chicago",
        "NH": "America/New_York",
        "NJ": "America/New_York",
        "NM": "America/Denver",
        "NV": "America/Los_Angeles",
        "NY": "America/New_York",
        "OH": "America/New_York",
        "OK": "America/Chicago",
        "OR": "America/Los_Angeles",
        "PA": "America/New_York",
        "RI": "America/New_York",
        "SC": "America/New_York",
        "SD": "America/Chicago",
        "TN": "America/Chicago",
        "TX": "America/Chicago",
        "UT": "America/Denver",
        "VA": "America/New_York",
        "VT": "America/New_York",
        "WA": "America/Los_Angeles",
        "WI": "America/Chicago",
        "WV": "America/New_York",
        "WY": "America/Denver",
    }
)

#: (city, 3-digit ZIP prefix) per state. One city each keeps the list small; the last two
#: ZIP digits are drawn.
STATE_CITY: Mapping[str, tuple[str, str]] = MappingProxyType(
    {
        "AK": ("Anchorage", "995"),
        "AL": ("Birmingham", "352"),
        "AR": ("Little Rock", "722"),
        "AZ": ("Phoenix", "850"),
        "CA": ("Los Angeles", "900"),
        "CO": ("Denver", "802"),
        "CT": ("Hartford", "061"),
        "DC": ("Washington", "200"),
        "DE": ("Wilmington", "198"),
        "FL": ("Orlando", "328"),
        "GA": ("Atlanta", "303"),
        "HI": ("Honolulu", "968"),
        "IA": ("Des Moines", "503"),
        "ID": ("Boise", "837"),
        "IL": ("Chicago", "606"),
        "IN": ("Indianapolis", "462"),
        "KS": ("Wichita", "672"),
        "KY": ("Louisville", "402"),
        "LA": ("Baton Rouge", "708"),
        "MA": ("Boston", "021"),
        "MD": ("Baltimore", "212"),
        "ME": ("Portland", "041"),
        "MI": ("Detroit", "482"),
        "MN": ("Minneapolis", "554"),
        "MO": ("St. Louis", "631"),
        "MS": ("Jackson", "392"),
        "MT": ("Billings", "591"),
        "NC": ("Charlotte", "282"),
        "ND": ("Fargo", "581"),
        "NE": ("Omaha", "681"),
        "NH": ("Manchester", "031"),
        "NJ": ("Newark", "071"),
        "NM": ("Albuquerque", "871"),
        "NV": ("Las Vegas", "891"),
        "NY": ("New York", "100"),
        "OH": ("Columbus", "432"),
        "OK": ("Oklahoma City", "731"),
        "OR": ("Portland", "972"),
        "PA": ("Philadelphia", "191"),
        "RI": ("Providence", "029"),
        "SC": ("Columbia", "292"),
        "SD": ("Sioux Falls", "571"),
        "TN": ("Nashville", "372"),
        "TX": ("Dallas", "752"),
        "UT": ("Salt Lake City", "841"),
        "VA": ("Richmond", "232"),
        "VT": ("Burlington", "054"),
        "WA": ("Seattle", "981"),
        "WI": ("Milwaukee", "532"),
        "WV": ("Charleston", "253"),
        "WY": ("Cheyenne", "820"),
    }
)

FIRST_NAMES: tuple[str, ...] = (
    "Alex", "Amara", "Ben", "Carla", "Chen", "Dana", "Diego", "Elena", "Farah", "Grace",
    "Hana", "Ian", "Imani", "Jamal", "Jin", "Jordan", "Kara", "Leo", "Lina", "Luis",
    "Maya", "Mei", "Nadia", "Noah", "Omar", "Priya", "Quinn", "Rafael", "Rosa", "Sam",
    "Sofia", "Tariq", "Tess", "Uma", "Victor", "Wen", "Yara", "Yusuf", "Zoe", "Aiden",
)  # fmt: skip

LAST_NAMES: tuple[str, ...] = (
    "Adams", "Alvarez", "Baker", "Bennett", "Brooks", "Castillo", "Chowdhury", "Cole",
    "Dias", "Ellis", "Fischer", "Foster", "Garcia", "Grant", "Hayes", "Hughes", "Ibrahim",
    "Jensen", "Kim", "Kowalski", "Larsen", "Lopez", "Martin", "Mensah", "Moreau", "Nakamura",
    "Novak", "Okafor", "Olsen", "Patel", "Price", "Reyes", "Rossi", "Sato", "Schmidt",
    "Singh", "Tran", "Varga", "Walsh", "Young",
)  # fmt: skip

#: Account names are "<prefix> <industry> <suffix>", drawn without repeats.
COMPANY_PREFIXES: tuple[str, ...] = (
    "Northfield", "Bluewater", "Cedar Ridge", "Summit", "Harbor", "Ironwood", "Lakeside",
    "Meridian", "Oakline", "Pinecrest", "Redstone", "Silver Creek", "Stonebridge",
    "Westgate", "Brightpath", "Clearview", "Fairhaven", "Granite", "Kestrel", "Riverbend",
)  # fmt: skip
COMPANY_INDUSTRIES: tuple[str, ...] = (
    "Logistics", "Health", "Manufacturing", "Retail", "Foods", "Properties", "Financial",
    "Hospitality", "Education", "Energy", "Distribution", "Labs",
)  # fmt: skip
COMPANY_SUFFIXES: tuple[str, ...] = ("Group", "Inc.", "Co.", "Partners", "Holdings", "LLC")

STREET_NAMES: tuple[str, ...] = (
    "Oak", "Maple", "Cedar", "Elm", "Pine", "Lake", "Hill", "Park", "Washington", "Main",
    "Market", "River", "Commerce", "Industrial", "Harbor", "Ridge", "Meadow", "Mill",
    "Station", "Union",
)  # fmt: skip
STREET_SUFFIXES: tuple[str, ...] = ("St", "Ave", "Blvd", "Rd", "Dr", "Way", "Pkwy", "Ct")

#: Site names by position within an account: the first site is always "HQ".
SITE_NAMES: tuple[str, ...] = (
    "HQ", "Branch 2", "Warehouse", "Data Center", "Branch 3", "Distribution Center",
    "Regional Office",
)  # fmt: skip

#: Area codes for contact phones; the local part is always 555-01xx (reserved for fiction).
PHONE_AREA_CODES: tuple[str, ...] = ("212", "312", "404", "415", "512", "617", "702", "206")

EMAIL_DOMAIN = "example.com"
