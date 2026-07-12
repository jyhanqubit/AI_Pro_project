"""Place gazetteer for the demo. CLAUDE.md sections 8 and 9.

Maps known Jersey City / Hoboken place names to approximate coordinates so the mock
extractor can attach grounded locations to events. This is what lets the graph connect
Event -> Place -> H3Zone, which in turn feeds the numeric graph features in Phase 05
(a graph with no path to features would be decoration, which section 9 forbids).
"""

from __future__ import annotations

# name (lowercase, as it appears in text) -> (canonical name, latitude, longitude)
PLACE_GAZETTEER: dict[str, tuple[str, float, float]] = {
    "hoboken terminal": ("Hoboken Terminal", 40.7360, -74.0301),
    "grove st": ("Grove St PATH", 40.7196, -74.0431),
    "grove street": ("Grove St PATH", 40.7196, -74.0431),
    "city hall": ("City Hall", 40.7377, -74.0324),
    "newport": ("Newport", 40.7272, -74.0337),
    "waterfront": ("Newport Waterfront", 40.7272, -74.0337),
    "washington st": ("Washington St", 40.7450, -74.0280),
    "journal square": ("Journal Square", 40.7328, -74.0632),
    "exchange place": ("Exchange Place", 40.7166, -74.0329),
}
