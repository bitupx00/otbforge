"""
OTBM Map Validator.

Validates a MapData instance for structural integrity, bounds, uniqueness
constraints, and common pitfalls.  Every check returns a list of
ValidationIssue objects classified by severity (error / warning / info).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import List, Optional, Tuple

from ai_core.otbm_types import (
    ItemData,
    MapData,
    NPCSpawnData,
    Position,
    SpawnData,
    TileData,
)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class ValidationIssue:
    """A single validation finding."""

    severity: str            # "error" | "warning" | "info"
    category: str            # e.g. "tiles", "spawns", "towns"
    message: str
    position: Optional[Tuple[int, int, int]] = None

    def __post_init__(self) -> None:
        if self.severity not in ("error", "warning", "info"):
            raise ValueError(f"Invalid severity: {self.severity!r}")


# ---------------------------------------------------------------------------
# Helper – compute container nesting depth
# ---------------------------------------------------------------------------

def _container_depth(item: ItemData) -> int:
    """Return the maximum nesting depth of *item*'s children tree.

    A leaf item (no children) has depth 0.  A container with children that
    are themselves leaves has depth 1, and so on.
    """
    if not item.children:
        return 0
    return 1 + max(_container_depth(child) for child in item.children)


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------

class MapValidator:
    """Stateless validator — all methods are static / class-level."""

    # Maximum reasonable map dimension (16-bit unsigned).
    MAX_DIM = 65536

    # Maximum allowed container nesting depth.
    MAX_CONTAINER_DEPTH = 3

    # ------------------------------------------------------------------
    # Public entry-point
    # ------------------------------------------------------------------

    @staticmethod
    def validate(map_data: MapData) -> List[ValidationIssue]:
        """Run *all* checks and return the combined list of issues."""
        issues: List[ValidationIssue] = []
        checks = [
            MapValidator.check_dimensions,
            MapValidator.check_empty_map,
            MapValidator.check_tiles_bounds,
            MapValidator.check_ground_ids,
            MapValidator.check_no_duplicate_tiles,
            MapValidator.check_tile_items_valid,
            MapValidator.check_container_depth,
            MapValidator.check_house_tiles_valid,
            MapValidator.check_spawns_bounds,
            MapValidator.check_spawn_monsters,
            MapValidator.check_towns_unique,
            MapValidator.check_waypoints_unique,
            MapValidator.check_npc_spawns_bounds,
        ]
        for check in checks:
            issues.extend(check(map_data))
        return issues

    # ------------------------------------------------------------------
    # 1. Dimensions
    # ------------------------------------------------------------------

    @staticmethod
    def check_dimensions(map_data: MapData) -> List[ValidationIssue]:
        issues: List[ValidationIssue] = []
        w, h = map_data.width, map_data.height
        if w <= 0:
            issues.append(ValidationIssue("error", "dimensions",
                          f"Map width must be > 0, got {w}"))
        if h <= 0:
            issues.append(ValidationIssue("error", "dimensions",
                          f"Map height must be > 0, got {h}"))
        if w >= MapValidator.MAX_DIM:
            issues.append(ValidationIssue("error", "dimensions",
                          f"Map width {w} exceeds maximum {MapValidator.MAX_DIM}"))
        if h >= MapValidator.MAX_DIM:
            issues.append(ValidationIssue("error", "dimensions",
                          f"Map height {h} exceeds maximum {MapValidator.MAX_DIM}"))
        if w > 2048 or h > 2048:
            if w < MapValidator.MAX_DIM and h < MapValidator.MAX_DIM:
                issues.append(ValidationIssue("info", "dimensions",
                              f"Large map dimensions: {w}x{h}"))
        return issues

    # ------------------------------------------------------------------
    # 2. Empty map
    # ------------------------------------------------------------------

    @staticmethod
    def check_empty_map(map_data: MapData) -> List[ValidationIssue]:
        if not map_data.tiles and not map_data.spawns and not map_data.npc_spawns:
            return [ValidationIssue("warning", "map",
                        "Map is empty (no tiles, spawns, or NPCs)")]
        return []

    # ------------------------------------------------------------------
    # 3. Tiles within bounds
    # ------------------------------------------------------------------

    @staticmethod
    def check_tiles_bounds(map_data: MapData) -> List[ValidationIssue]:
        issues: List[ValidationIssue] = []
        w, h = map_data.width, map_data.height
        if w <= 0 or h <= 0:
            return issues  # already flagged by check_dimensions
        for tile in map_data.tiles:
            if not (0 <= tile.x < w and 0 <= tile.y < h):
                issues.append(ValidationIssue(
                    "error", "tiles",
                    f"Tile at ({tile.x}, {tile.y}, {tile.z}) is out of map bounds {w}x{h}",
                    (tile.x, tile.y, tile.z)))
        return issues

    # ------------------------------------------------------------------
    # 4. Ground IDs > 0
    # ------------------------------------------------------------------

    @staticmethod
    def check_ground_ids(map_data: MapData) -> List[ValidationIssue]:
        issues: List[ValidationIssue] = []
        for tile in map_data.tiles:
            if tile.ground_id <= 0:
                issues.append(ValidationIssue(
                    "warning", "tiles",
                    f"Tile at ({tile.x}, {tile.y}, {tile.z}) has no ground (ground_id={tile.ground_id})",
                    (tile.x, tile.y, tile.z)))
        return issues

    # ------------------------------------------------------------------
    # 5. No duplicate tiles (same x, y, z)
    # ------------------------------------------------------------------

    @staticmethod
    def check_no_duplicate_tiles(map_data: MapData) -> List[ValidationIssue]:
        issues: List[ValidationIssue] = []
        seen: dict[Tuple[int, int, int], int] = {}
        for idx, tile in enumerate(map_data.tiles):
            key = (tile.x, tile.y, tile.z)
            if key in seen:
                issues.append(ValidationIssue(
                    "error", "tiles",
                    f"Duplicate tile at ({tile.x}, {tile.y}, {tile.z}) "
                    f"(first at index {seen[key]})",
                    (tile.x, tile.y, tile.z)))
            else:
                seen[key] = idx
        return issues

    # ------------------------------------------------------------------
    # 6. Tile items with valid IDs
    # ------------------------------------------------------------------

    @staticmethod
    def check_tile_items_valid(map_data: MapData) -> List[ValidationIssue]:
        issues: List[ValidationIssue] = []
        for tile in map_data.tiles:
            for item in tile.items:
                if item.id <= 0:
                    issues.append(ValidationIssue(
                        "error", "items",
                        f"Item with invalid id={item.id} on tile ({tile.x}, {tile.y}, {tile.z})",
                        (tile.x, tile.y, tile.z)))
        return issues

    # ------------------------------------------------------------------
    # 7. Container nesting depth
    # ------------------------------------------------------------------

    @staticmethod
    def check_container_depth(map_data: MapData) -> List[ValidationIssue]:
        issues: List[ValidationIssue] = []
        for tile in map_data.tiles:
            for item in tile.items:
                depth = _container_depth(item)
                if depth > MapValidator.MAX_CONTAINER_DEPTH:
                    issues.append(ValidationIssue(
                        "warning", "items",
                        f"Container nesting depth {depth} exceeds limit "
                        f"{MapValidator.MAX_CONTAINER_DEPTH} on tile "
                        f"({tile.x}, {tile.y}, {tile.z})",
                        (tile.x, tile.y, tile.z)))
        return issues

    # ------------------------------------------------------------------
    # 8. House tiles require at least one town
    # ------------------------------------------------------------------

    @staticmethod
    def check_house_tiles_valid(map_data: MapData) -> List[ValidationIssue]:
        issues: List[ValidationIssue] = []
        has_towns = len(map_data.towns) > 0
        for tile in map_data.tiles:
            if tile.house_id > 0 and not has_towns:
                issues.append(ValidationIssue(
                    "warning", "houses",
                    f"House tile at ({tile.x}, {tile.y}, {tile.z}) with "
                    f"house_id={tile.house_id} but no towns defined",
                    (tile.x, tile.y, tile.z)))
            elif tile.house_id < 0:
                issues.append(ValidationIssue(
                    "error", "houses",
                    f"Negative house_id={tile.house_id} on tile "
                    f"({tile.x}, {tile.y}, {tile.z})",
                    (tile.x, tile.y, tile.z)))
        return issues

    # ------------------------------------------------------------------
    # 9. Spawns within bounds
    # ------------------------------------------------------------------

    @staticmethod
    def check_spawns_bounds(map_data: MapData) -> List[ValidationIssue]:
        issues: List[ValidationIssue] = []
        w, h = map_data.width, map_data.height
        if w <= 0 or h <= 0:
            return issues
        for spawn in map_data.spawns:
            if not (0 <= spawn.x < w and 0 <= spawn.y < h):
                issues.append(ValidationIssue(
                    "error", "spawns",
                    f"Spawn at ({spawn.x}, {spawn.y}, {spawn.z}) is out of map bounds {w}x{h}",
                    (spawn.x, spawn.y, spawn.z)))
        return issues

    # ------------------------------------------------------------------
    # 10. Spawn monsters list non-empty
    # ------------------------------------------------------------------

    @staticmethod
    def check_spawn_monsters(map_data: MapData) -> List[ValidationIssue]:
        issues: List[ValidationIssue] = []
        for spawn in map_data.spawns:
            if not spawn.monsters:
                issues.append(ValidationIssue(
                    "error", "spawns",
                    f"Spawn at ({spawn.x}, {spawn.y}, {spawn.z}) has no monsters assigned",
                    (spawn.x, spawn.y, spawn.z)))
        return issues

    # ------------------------------------------------------------------
    # 11. Town IDs unique
    # ------------------------------------------------------------------

    @staticmethod
    def check_towns_unique(map_data: MapData) -> List[ValidationIssue]:
        issues: List[ValidationIssue] = []
        id_counts = Counter(t.id for t in map_data.towns)
        for town in map_data.towns:
            if id_counts[town.id] > 1:
                issues.append(ValidationIssue(
                    "error", "towns",
                    f"Duplicate town id={town.id} (name={town.name!r})",
                    (town.temple.x, town.temple.y, town.temple.z)))
        return issues

    # ------------------------------------------------------------------
    # 12. Waypoint names unique
    # ------------------------------------------------------------------

    @staticmethod
    def check_waypoints_unique(map_data: MapData) -> List[ValidationIssue]:
        issues: List[ValidationIssue] = []
        name_counts = Counter(wp.name for wp in map_data.waypoints)
        for wp in map_data.waypoints:
            if name_counts[wp.name] > 1:
                issues.append(ValidationIssue(
                    "warning", "waypoints",
                    f"Duplicate waypoint name={wp.name!r} at "
                    f"({wp.pos.x}, {wp.pos.y}, {wp.pos.z})",
                    (wp.pos.x, wp.pos.y, wp.pos.z)))
        return issues

    # ------------------------------------------------------------------
    # 13. NPC spawns within bounds
    # ------------------------------------------------------------------

    @staticmethod
    def check_npc_spawns_bounds(map_data: MapData) -> List[ValidationIssue]:
        issues: List[ValidationIssue] = []
        w, h = map_data.width, map_data.height
        if w <= 0 or h <= 0:
            return issues
        for npc in map_data.npc_spawns:
            if not (0 <= npc.x < w and 0 <= npc.y < h):
                issues.append(ValidationIssue(
                    "error", "npc_spawns",
                    f"NPC spawn for {npc.npc_name!r} at ({npc.x}, {npc.y}, {npc.z}) "
                    f"is out of map bounds {w}x{h}",
                    (npc.x, npc.y, npc.z)))
        return issues

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    @staticmethod
    def summary(issues: List[ValidationIssue]) -> dict[str, int]:
        """Return ``{"errors": n, "warnings": n, "info": n}``."""
        return {
            "errors": sum(1 for i in issues if i.severity == "error"),
            "warnings": sum(1 for i in issues if i.severity == "warning"),
            "info": sum(1 for i in issues if i.severity == "info"),
        }
