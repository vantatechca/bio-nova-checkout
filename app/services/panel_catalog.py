"""The fixed catalog of content panels and their sections.

This is code, not data: the admin must know about a section (and show its "coming soon" card) before anyone
has pushed anything to it. A panel's API key comes from the environment variable named in ``key_setting``.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Section:
    id: str
    title: str
    icon: str
    subtitle: str
    tier: str | None = None  # "included" | "addon" on panels that need it


@dataclass(frozen=True)
class Panel:
    slug: str
    title: str
    key_setting: str  # attribute of ``Settings`` (env var ADS_DATA_KEY -> ads_data_key)
    sections: tuple[Section, ...]


PANELS: dict[str, Panel] = {
    "ads": Panel(
        slug="ads",
        title="Ads Data",
        key_setting="ads_data_key",
        sections=(
            Section("canva", "Canva", "image", "ROAS and ad spend analysis screenshots."),
            Section("excel", "Excel", "table", "Ad performance and reporting sheets."),
            Section(
                "card_info", "Credit Card Info", "card", "Ad spend per card. Only the last 4 digits are ever shown."
            ),
        ),
    ),
    "sites": Panel(
        slug="sites",
        title="Sites",
        key_setting="sites_key",
        sections=(
            Section("live_sites", "Live Sites", "globe", "Every live site with its status and uptime.", "included"),
            Section("gmb", "Live GMB Profiles", "pin", "Google Business Profiles for each location.", "addon"),
            Section("trustpilot", "Live Trustpilot Profiles", "star", "Trustpilot profiles and ratings.", "addon"),
            Section("seo_city", "SEO per City", "search", "Search visibility for each city.", "addon"),
            Section("reddit_city", "Reddit per City", "chat", "Reddit presence for each city.", "addon"),
        ),
    ),
}

# Content that only makes sense in one section.
SITES_SECTION = ("sites", "live_sites")
CARDS_SECTION = ("ads", "card_info")


def get_panel(slug: str) -> Panel | None:
    return PANELS.get(slug)


def get_section(panel: str, section: str) -> Section | None:
    found = PANELS.get(panel)
    return next((s for s in found.sections if s.id == section), None) if found else None
