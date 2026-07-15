"""Place gazetteer for the demo + real backfills. CLAUDE.md sections 8 and 9.

Maps known place names to approximate coordinates so the mock extractor can attach grounded
locations to events. This is what lets the graph connect Event -> Place -> H3Zone, which in turn
feeds the numeric graph features in Phase 05 (a graph with no path to features would be decoration,
which section 9 forbids).

The Jersey City / Hoboken block backs the deterministic golden-path demo. The New York City block
covers the Citi Bike core service area (Manhattan / Brooklyn / Queens / Bronx) so a **real** GDELT
news backfill over an NYC trip window can geocode its events onto zones that actually carry trip
demand — the prerequisite for measuring a real LLM-feature lift on the NYC network. Coordinates are
landmark centroids (H3 res 9 ~ 174 m edge, so a few metres of imprecision stays in the right zone).
Phrases are lowercase substrings as they appear in news text; broad bare borough names are omitted
on purpose to avoid concentrating unrelated news onto one centroid.
"""

from __future__ import annotations

# name (lowercase, as it appears in text) -> (canonical name, latitude, longitude)
PLACE_GAZETTEER: dict[str, tuple[str, float, float]] = {
    # --- Jersey City / Hoboken (golden-path demo) ---
    "hoboken terminal": ("Hoboken Terminal", 40.7360, -74.0301),
    "grove st": ("Grove St PATH", 40.7196, -74.0431),
    "grove street": ("Grove St PATH", 40.7196, -74.0431),
    "city hall": ("City Hall", 40.7377, -74.0324),
    "newport": ("Newport", 40.7272, -74.0337),
    "waterfront": ("Newport Waterfront", 40.7272, -74.0337),
    "washington st": ("Washington St", 40.7450, -74.0280),
    "journal square": ("Journal Square", 40.7328, -74.0632),
    "exchange place": ("Exchange Place", 40.7166, -74.0329),
    # --- Manhattan ---
    "times square": ("Times Square", 40.7580, -73.9855),
    "union square": ("Union Square", 40.7359, -73.9911),
    "grand central": ("Grand Central", 40.7527, -73.9772),
    "penn station": ("Penn Station", 40.7506, -73.9935),
    "madison square garden": ("Madison Square Garden", 40.7505, -73.9934),
    "herald square": ("Herald Square", 40.7484, -73.9878),
    "bryant park": ("Bryant Park", 40.7536, -73.9832),
    "columbus circle": ("Columbus Circle", 40.7680, -73.9819),
    "central park": ("Central Park", 40.7812, -73.9665),
    "wall street": ("Wall Street", 40.7069, -74.0090),
    "financial district": ("Financial District", 40.7075, -74.0110),
    "world trade center": ("World Trade Center", 40.7127, -74.0134),
    "battery park": ("Battery Park", 40.7033, -74.0170),
    "chelsea": ("Chelsea", 40.7465, -74.0014),
    "soho": ("SoHo", 40.7233, -74.0030),
    "greenwich village": ("Greenwich Village", 40.7336, -74.0027),
    "east village": ("East Village", 40.7265, -73.9815),
    "west village": ("West Village", 40.7358, -74.0036),
    "lower east side": ("Lower East Side", 40.7150, -73.9843),
    "midtown": ("Midtown", 40.7549, -73.9840),
    "harlem": ("Harlem", 40.8116, -73.9465),
    "upper east side": ("Upper East Side", 40.7736, -73.9566),
    "upper west side": ("Upper West Side", 40.7870, -73.9754),
    "washington heights": ("Washington Heights", 40.8417, -73.9393),
    "chinatown": ("Chinatown", 40.7158, -73.9970),
    # --- Brooklyn ---
    "brooklyn bridge": ("Brooklyn Bridge", 40.7061, -73.9969),
    "dumbo": ("DUMBO", 40.7033, -73.9881),
    "downtown brooklyn": ("Downtown Brooklyn", 40.6923, -73.9875),
    "barclays center": ("Barclays Center", 40.6826, -73.9754),
    "williamsburg": ("Williamsburg", 40.7081, -73.9571),
    "prospect park": ("Prospect Park", 40.6602, -73.9690),
    "park slope": ("Park Slope", 40.6710, -73.9814),
    "bushwick": ("Bushwick", 40.6944, -73.9213),
    "bedford-stuyvesant": ("Bedford-Stuyvesant", 40.6872, -73.9418),
    # --- Queens / Bronx (Citi Bike expansion area) ---
    "long island city": ("Long Island City", 40.7447, -73.9485),
    "astoria": ("Astoria", 40.7644, -73.9235),
    "yankee stadium": ("Yankee Stadium", 40.8296, -73.9262),
}
