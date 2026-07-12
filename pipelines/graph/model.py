"""Graph node/edge model and event -> graph translation. CLAUDE.md section 9.

A backend-neutral representation: nodes are (label, key, props) and edges are typed
relationships between node keys. ``build_graph_ops`` turns extracted events plus their
source articles into the node/relationship set from section 9, wiring Event -> Place ->
H3Zone (and Event -> AFFECTS -> H3Zone) so the graph can feed numeric features downstream.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from config.features import H3_RESOLUTION
from contracts.article import ArticleRecord
from contracts.event import EventExtraction
from pipelines.features.zones import zone_for

# Node labels and their key property (uniqueness key). Section 9 core nodes.
NODE_KEYS: dict[str, str] = {
    "Source": "name",
    "Article": "article_id",
    "Event": "event_id",
    "EventType": "name",
    "Place": "name",
    "H3Zone": "zone_id",
    "Station": "station_id",
}

# Relationship types (section 9 core relationships).
REL_TYPES = frozenset(
    {
        "REPORTS",  # Article -> Event
        "FROM_SOURCE",  # Article -> Source
        "INSTANCE_OF",  # Event -> EventType
        "OCCURS_AT",  # Event -> Place
        "IN_ZONE",  # Place -> H3Zone
        "AFFECTS",  # Event -> H3Zone
        "CONTAINS",  # H3Zone -> Station
        "SAME_EVENT_AS",  # Event -> Event (reserved; dedup happens upstream in Phase 03)
    }
)


@dataclass(frozen=True)
class Node:
    label: str
    key: str
    props: tuple[tuple[str, str], ...] = ()  # sorted (k, str(v)) pairs; hashable


@dataclass
class GraphOps:
    nodes: list[Node] = field(default_factory=list)
    edges: list[tuple[str, str, str, str, str]] = field(default_factory=list)
    # edge = (from_label, from_key, rel_type, to_label, to_key)


def _node(label: str, key: str, props: dict[str, object]) -> Node:
    clean = tuple(sorted((k, str(v)) for k, v in props.items() if v is not None))
    return Node(label=label, key=str(key), props=clean)


def build_graph_ops(
    events: list[EventExtraction],
    articles_by_id: dict[str, ArticleRecord],
    *,
    resolution: int = H3_RESOLUTION,
) -> GraphOps:
    """Translate events (+ their source articles) into graph nodes and relationships."""
    ops = GraphOps()
    seen_nodes: set[tuple[str, str]] = set()

    def add_node(label: str, key: str, props: dict[str, object]) -> None:
        n = _node(label, key, props)
        if (n.label, n.key) not in seen_nodes:
            seen_nodes.add((n.label, n.key))
            ops.nodes.append(n)

    for event in events:
        add_node(
            "Event",
            event.event_id,
            {
                "event_type": event.event_type.value,
                "title": event.event_title,
                "severity": event.severity,
                "confidence": event.confidence,
                "demand_effect": event.demand_effect.value,
                "capacity_effect": event.capacity_effect.value,
                "status": event.status.value,
                "available_at": event.available_at.isoformat() if event.available_at else None,
                "extraction_model": event.extraction_model,
                "prompt_version": event.extraction_prompt_version,
            },
        )
        add_node("EventType", event.event_type.value, {"name": event.event_type.value})
        ops.edges.append(
            ("Event", event.event_id, "INSTANCE_OF", "EventType", event.event_type.value)
        )

        # Provenance: Article -> REPORTS -> Event, Article -> FROM_SOURCE -> Source.
        for article_id in event.source_article_ids:
            article = articles_by_id.get(article_id)
            if article is None:
                continue
            add_node(
                "Article",
                article.article_id,
                {
                    "title": article.title,
                    "url_hash": article.url_hash,
                    "published_at": article.published_at.isoformat(),
                    "available_at": article.available_at.isoformat()
                    if article.available_at
                    else None,
                    "raw_payload_path": article.raw_payload_path,
                    "mode": article.mode.value,
                },
            )
            add_node("Source", article.source, {"name": article.source})
            ops.edges.append(("Article", article.article_id, "REPORTS", "Event", event.event_id))
            ops.edges.append(
                ("Article", article.article_id, "FROM_SOURCE", "Source", article.source)
            )

        # Spatial: Event -> Place -> H3Zone, and Event -> AFFECTS -> H3Zone.
        for loc in event.locations:
            add_node("Place", loc.name, {"name": loc.name})
            ops.edges.append(("Event", event.event_id, "OCCURS_AT", "Place", loc.name))
            if loc.lat is not None and loc.lng is not None:
                zone = zone_for(loc.lat, loc.lng, resolution)
                add_node("H3Zone", zone, {"zone_id": zone})
                ops.edges.append(("Place", loc.name, "IN_ZONE", "H3Zone", zone))
                ops.edges.append(("Event", event.event_id, "AFFECTS", "H3Zone", zone))

    return ops
