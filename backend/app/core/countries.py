"""Countries discovery can search, grouped by how graduate study is usually funded there.

The system drives funding defaults (programs.DEFAULTS), the PhD entry-degree check
(eligibility.PHD_ENTRY) and next-step advice (tracker). These are only defaults:
a verified program page always overrides them.
"""

from typing import Literal

# code: (name, region, system). Codes are ISO 3166-1 alpha-2, as OpenAlex uses.
COUNTRIES: dict[str, tuple[str, str, str]] = {
    "US": ("USA", "North America", "us"),
    "CA": ("Canada", "North America", "ca"),
    "GB": ("United Kingdom", "Europe", "studentship"),
    "IE": ("Ireland", "Europe", "studentship"),
    "DE": ("Germany", "Europe", "position"),
    "NL": ("Netherlands", "Europe", "position"),
    "CH": ("Switzerland", "Europe", "position"),
    "AT": ("Austria", "Europe", "position"),
    "BE": ("Belgium", "Europe", "position"),
    "DK": ("Denmark", "Europe", "position"),
    "FI": ("Finland", "Europe", "position"),
    "NO": ("Norway", "Europe", "position"),
    "SE": ("Sweden", "Europe", "position"),
    "FR": ("France", "Europe", "contract"),
    "ES": ("Spain", "Europe", "contract"),
    "IT": ("Italy", "Europe", "contract"),
    "PT": ("Portugal", "Europe", "contract"),
    "AU": ("Australia", "Asia-Pacific", "anz"),
    "NZ": ("New Zealand", "Asia-Pacific", "anz"),
    "JP": ("Japan", "Asia-Pacific", "jp"),
    "KR": ("South Korea", "Asia-Pacific", "kr"),
}

CountryCode = Literal[tuple(COUNTRIES)]  # type: ignore[valid-type]


def system(country: str | None) -> str | None:
    return COUNTRIES[country][2] if country in COUNTRIES else None
