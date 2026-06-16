"""
Map Diff Tool — Compare two OTBM maps and report differences.

Supports comparing:
  - Two MapData objects directly
  - Two .otbm files (by path or raw bytes)
  - A MapData against an .otbm file

Output formats:
  - summary()   — one-line text overview
  - detailed()  — full text report with all changes
  - to_json()   — machine-readable dict
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from ai_core.models import (
    ItemData,
    MapData,
    Position,
    TileData,
    TownData,
    WaypointData,
)
from ai_core.otbm_reader import OTBMReader


# ---------------------------------------------------------------------------
# Data classes for diff results
# ---------------------------------------------------------------------------

@dataclass
class TileDiff:
    """Describes a single tile change between two maps."""
    coord: Tuple[int, int, int]  # (x, y, z)
    change_type: str  # "added", "removed", "modified"
    ground_before: int = 0
    ground_after: int = 0
    items_before: int = 0
    items_after: int = 0
    flags_before: int = 0
    flags_after: int = 0
    house_id_before: int = 0
    house_id_after: int = 0
    item_ids_before: List[int] = field(default_factory=list)
    item_ids_after: List[int] = field(default_factory=list)

    def __repr__(self) -> str:
        return (f"TileDiff({self.coord}, {self.change_type}, "
                f"ground={self.ground_before}->{self.ground_after})")


@dataclass
class StatsDiff:
    """Describes high-level stats changes between two maps."""
    tiles_before: int = 0
    tiles_after: int = 0
    ground_tiles_before: int = 0
    ground_tiles_after: int = 0
    towns_added: List[str] = field(default_factory=list)
    towns_removed: List[str] = field(default_factory=list)
    waypoints_added: List[str] = field(default_factory=list)
    waypoints_removed: List[str] = field(default_factory=list)
    spawns_before: int = 0
    spawns_after: int = 0
    houses_before: int = 0
    houses_after: int = 0
    npc_spawns_before: int = 0
    npc_spawns_after: int = 0

    @property
    def tiles_delta(self) -> int:
        return self.tiles_after - self.tiles_before

    @property
    def spawns_delta(self) -> int:
        return self.spawns_after - self.spawns_before

    @property
    def houses_delta(self) -> int:
        return self.houses_after - self.houses_before


@dataclass
class MapDiffResult:
    """Full diff result between two maps."""
    map_a_description: str = ""
    map_b_description: str = ""
    tile_diffs: List[TileDiff] = field(default_factory=list)
    stats_diff: StatsDiff = field(default_factory=StatsDiff)

    # ---- Public API ----

    def summary(self) -> str:
        """Return a concise text summary."""
        added = sum(1 for d in self.tile_diffs if d.change_type == "added")
        removed = sum(1 for d in self.tile_diffs if d.change_type == "removed")
        modified = sum(1 for d in self.tile_diffs if d.change_type == "modified")
        td = self.stats_diff
        parts = [
            f"Map Diff: {self.map_a_description} -> {self.map_b_description}",
            f"  Tiles: +{added} -{removed} ~{modified} (total {td.tiles_before}->{td.tiles_after})",
            f"  Towns: +{len(td.towns_added)} -{len(td.towns_removed)}",
            f"  Waypoints: +{len(td.waypoints_added)} -{len(td.waypoints_removed)}",
            f"  Spawns: {td.spawns_before}->{td.spawns_after}",
            f"  Houses: {td.houses_before}->{td.houses_after}",
        ]
        return "\n".join(parts)

    def detailed(self) -> str:
        """Return a full text report with every tile change."""
        lines = [self.summary(), ""]

        if not self.tile_diffs:
            lines.append("  (no tile differences)")
        else:
            for diff in self.tile_diffs:
                c = diff.coord
                if diff.change_type == "added":
                    lines.append(f"  [+] Tile({c[0]},{c[1]},{c[2]}) ground={diff.ground_after} items={diff.items_after}")
                elif diff.change_type == "removed":
                    lines.append(f"  [-] Tile({c[0]},{c[1]},{c[2]}) ground={diff.ground_before} items={diff.items_before}")
                else:
                    lines.append(f"  [~] Tile({c[0]},{c[1]},{c[2]}) "
                                 f"ground={diff.ground_before}->{diff.ground_after} "
                                 f"items={diff.items_before}->{diff.items_after}")

        # Town changes
        if self.stats_diff.towns_added:
            lines.append("")
            lines.append(f"  Towns added: {', '.join(self.stats_diff.towns_added)}")
        if self.stats_diff.towns_removed:
            lines.append(f"  Towns removed: {', '.join(self.stats_diff.towns_removed)}")

        # Waypoint changes
        if self.stats_diff.waypoints_added:
            lines.append("")
            lines.append(f"  Waypoints added: {', '.join(self.stats_diff.waypoints_added)}")
        if self.stats_diff.waypoints_removed:
            lines.append(f"  Waypoints removed: {', '.join(self.stats_diff.waypoints_removed)}")

        return "\n".join(lines)

    def to_json(self) -> Dict[str, Any]:
        """Return machine-readable dict suitable for JSON serialization."""
        return {
            "map_a": self.map_a_description,
            "map_b": self.map_b_description,
            "tile_changes": {
                "added": sum(1 for d in self.tile_diffs if d.change_type == "added"),
                "removed": sum(1 for d in self.tile_diffs if d.change_type == "removed"),
                "modified": sum(1 for d in self.tile_diffs if d.change_type == "modified"),
                "total": len(self.tile_diffs),
            },
            "tiles": [
                {
                    "coord": list(d.coord),
                    "change": d.change_type,
                    "ground_before": d.ground_before,
                    "ground_after": d.ground_after,
                    "items_before": d.items_before,
                    "items_after": d.items_after,
                    "flags_before": d.flags_before,
                    "flags_after": d.flags_after,
                }
                for d in self.tile_diffs
            ],
            "stats": {
                "tiles_before": self.stats_diff.tiles_before,
                "tiles_after": self.stats_diff.tiles_after,
                "towns_added": self.stats_diff.towns_added,
                "towns_removed": self.stats_diff.towns_removed,
                "waypoints_added": self.stats_diff.waypoints_added,
                "waypoints_removed": self.stats_diff.waypoints_removed,
                "spawns_before": self.stats_diff.spawns_before,
                "spawns_after": self.stats_diff.spawns_after,
                "houses_before": self.stats_diff.houses_before,
                "houses_after": self.stats_diff.houses_after,
            },
        }


# ---------------------------------------------------------------------------
# MapDiff — the main entry point
# ---------------------------------------------------------------------------

class MapDiff:
    """Compare two OTBM maps.

    Usage::

        # Compare MapData objects
        result = MapDiff.compare(map_a, map_b)

        # Compare .otbm files
        result = MapDiff.compare_files("old.otbm", "new.otbm")

        # Print report
        print(result.summary())
        print(result.detailed())

        # JSON output
        import json
        print(json.dumps(result.to_json(), indent=2))
    """

    @staticmethod
    def compare(map_a: MapData, map_b: MapData) -> MapDiffResult:
        """Compare two MapData objects and return a MapDiffResult."""
        tile_diffs = MapDiff._diff_tiles(map_a, map_b)
        stats_diff = MapDiff._diff_stats(map_a, map_b)

        return MapDiffResult(
            map_a_description=map_a.description,
            map_b_description=map_b.description,
            tile_diffs=tile_diffs,
            stats_diff=stats_diff,
        )

    @staticmethod
    def compare_files(path_a: str, path_b: str) -> MapDiffResult:
        """Compare two .otbm files by path."""
        map_a = OTBMReader.from_file(path_a)
        map_b = OTBMReader.from_file(path_b)
        return MapDiff.compare(map_a, map_b)

    @staticmethod
    def compare_bytes(data_a: bytes, data_b: bytes) -> MapDiffResult:
        """Compare two .otbm files from raw bytes."""
        map_a = OTBMReader(data_a).read()
        map_b = OTBMReader(data_b).read()
        return MapDiff.compare(map_a, map_b)

    # ---- Internal helpers ----

    @staticmethod
    def _tile_index(tiles: List[TileData]) -> Dict[Tuple[int, int, int], TileData]:
        """Build a lookup index from tile list."""
        idx: Dict[Tuple[int, int, int], TileData] = {}
        for t in tiles:
            idx[(t.x, t.y, t.z)] = t
        return idx

    @staticmethod
    def _diff_tiles(map_a: MapData, map_b: MapData) -> List[TileDiff]:
        """Compare tile sets between two maps."""
        idx_a = MapDiff._tile_index(map_a.tiles)
        idx_b = MapDiff._tile_index(map_b.tiles)

        diffs: List[TileDiff] = []
        all_coords: Set[Tuple[int, int, int]] = set(idx_a.keys()) | set(idx_b.keys())

        for coord in sorted(all_coords):
            ta = idx_a.get(coord)
            tb = idx_b.get(coord)

            if ta is None and tb is not None:
                diffs.append(TileDiff(
                    coord=coord, change_type="added",
                    ground_after=tb.ground_id,
                    items_after=len(tb.items),
                    flags_after=int(tb.flags),
                    house_id_after=tb.house_id,
                    item_ids_after=[i.id for i in tb.items],
                ))
            elif ta is not None and tb is None:
                diffs.append(TileDiff(
                    coord=coord, change_type="removed",
                    ground_before=ta.ground_id,
                    items_before=len(ta.items),
                    flags_before=int(ta.flags),
                    house_id_before=ta.house_id,
                    item_ids_before=[i.id for i in ta.items],
                ))
            else:
                # Both exist — check for modifications
                changed = False
                ground_before = ta.ground_id
                ground_after = tb.ground_id
                if ground_before != ground_after:
                    changed = True

                items_before_ids = [i.id for i in ta.items]
                items_after_ids = [i.id for i in tb.items]
                if items_before_ids != items_after_ids:
                    changed = True

                flags_before = int(ta.flags)
                flags_after = int(tb.flags)
                if flags_before != flags_after:
                    changed = True

                house_before = ta.house_id
                house_after = tb.house_id
                if house_before != house_after:
                    changed = True

                if changed:
                    diffs.append(TileDiff(
                        coord=coord, change_type="modified",
                        ground_before=ground_before,
                        ground_after=ground_after,
                        items_before=len(ta.items),
                        items_after=len(tb.items),
                        flags_before=flags_before,
                        flags_after=flags_after,
                        house_id_before=house_before,
                        house_id_after=house_after,
                        item_ids_before=items_before_ids,
                        item_ids_after=items_after_ids,
                    ))

        return diffs

    @staticmethod
    def _diff_stats(map_a: MapData, map_b: MapData) -> StatsDiff:
        """Compare high-level stats between two maps."""
        stats_a = map_a.stats()
        stats_b = map_b.stats()

        # Town changes
        town_names_a = {t.name for t in map_a.towns}
        town_names_b = {t.name for t in map_b.towns}
        towns_added = sorted(town_names_b - town_names_a)
        towns_removed = sorted(town_names_a - town_names_b)

        # Waypoint changes
        wp_names_a = {w.name for w in map_a.waypoints}
        wp_names_b = {w.name for w in map_b.waypoints}
        waypoints_added = sorted(wp_names_b - wp_names_a)
        waypoints_removed = sorted(wp_names_a - wp_names_b)

        return StatsDiff(
            tiles_before=int(stats_a.get("tiles", 0)),
            tiles_after=int(stats_b.get("tiles", 0)),
            ground_tiles_before=int(stats_a.get("ground_tiles", 0)),
            ground_tiles_after=int(stats_b.get("ground_tiles", 0)),
            towns_added=towns_added,
            towns_removed=towns_removed,
            waypoints_added=waypoints_added,
            waypoints_removed=waypoints_removed,
            spawns_before=int(stats_a.get("spawns", 0)),
            spawns_after=int(stats_b.get("spawns", 0)),
            houses_before=int(stats_a.get("houses", 0)),
            houses_after=int(stats_b.get("houses", 0)),
            npc_spawns_before=int(stats_a.get("npc_spawns", 0)),
            npc_spawns_after=int(stats_b.get("npc_spawns", 0)),
        )
