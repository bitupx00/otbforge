"""
Tile Pattern Library — Pre-built reusable tile patterns/structures for OTBM maps.

Provides 15+ built-in patterns organised by category (BUILDING, NATURE,
DUNGEON, ROAD, WATER, CUSTOM) and a :class:`TilePatternLibrary` to query,
list, and apply them to maps.

Each pattern is a 2-D grid of tile specifications using realistic Tibia
item IDs.

Usage::

    from ai_core.patterns import TilePatternLibrary

    lib = TilePatternLibrary()
    pattern = lib.get_pattern("tower")
    lib.apply_pattern(map_data, "tower", x=100, y=200, z=7)
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from ai_core.models import (
    ItemData,
    MapData,
    TileData,
    TileFlag,
)


# ---------------------------------------------------------------------------
# Well-known Tibia item IDs used by patterns
# ---------------------------------------------------------------------------

class PatternTiles:
    """Common ground / wall / item IDs used in patterns."""
    # Ground surfaces
    GRASS = 102
    DIRT = 103
    SAND = 231
    STONE_FLOOR = 3326
    WATER = 490
    WOOD_FLOOR = 530

    # Walls
    STONE_WALL = 1102
    WOOD_WALL = 1018
    BRICK_WALL = 1060

    # Doors
    CLOSED_DOOR = 5121
    OPEN_DOOR = 5122

    # Furniture
    CHEST = 3756
    TABLE = 1786
    CHAIR = 1787
    BED = 2497

    # Nature
    TREE = 2700
    BUSH = 2767
    FLOWER = 2740
    ROCK = 3638

    # None / empty (no tile)
    EMPTY = 0


# ---------------------------------------------------------------------------
# Category enum
# ---------------------------------------------------------------------------

class PatternCategory(Enum):
    BUILDING = "building"
    NATURE = "nature"
    DUNGEON = "dungeon"
    ROAD = "road"
    WATER = "water"
    CUSTOM = "custom"


# ---------------------------------------------------------------------------
# PatternTile — single cell in a pattern grid
# ---------------------------------------------------------------------------

@dataclass
class PatternTile:
    """A single tile within a pattern.

    Attributes
    ----------
    ground_id : int
        Ground surface item ID (0 = no ground).
    items : list[int]
        Item IDs placed on this tile.
    flags : TileFlag
        Tile flags (e.g. protection zone).
    """
    ground_id: int = 0
    items: List[int] = field(default_factory=list)
    flags: TileFlag = TileFlag.NONE

    @staticmethod
    def ground(gid: int, items: Optional[List[int]] = None) -> "PatternTile":
        return PatternTile(ground_id=gid, items=items or [])

    @staticmethod
    def wall(gid: int = PatternTiles.STONE_WALL) -> "PatternTile":
        return PatternTile(ground_id=0, items=[gid])

    @staticmethod
    def empty() -> "PatternTile":
        return PatternTile(ground_id=0, items=[])

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {"ground_id": self.ground_id}
        if self.items:
            d["items"] = self.items
        if self.flags:
            d["flags"] = int(self.flags)
        return d


# ---------------------------------------------------------------------------
# Pattern — a named 2-D tile layout
# ---------------------------------------------------------------------------

@dataclass
class Pattern:
    """A reusable tile pattern.

    Attributes
    ----------
    name : str
        Unique identifier (e.g. ``"tower"``).
    description : str
        Human-readable description.
    category : PatternCategory
        Pattern category.
    width : int
        Pattern width in tiles.
    height : int
        Pattern height in tiles.
    tiles : list[list[PatternTile]]
        2-D grid (rows × columns).  ``tiles[y][x]``.
    """
    name: str
    description: str
    category: PatternCategory
    width: int
    height: int
    tiles: List[List[PatternTile]] = field(default_factory=list)

    def get_tile(self, x: int, y: int) -> PatternTile:
        """Get the pattern tile at grid position ``(x, y)``."""
        if 0 <= y < len(self.tiles) and 0 <= x < len(self.tiles[y]):
            return self.tiles[y][x]
        return PatternTile.empty()


# ---------------------------------------------------------------------------
# Built-in patterns
# ---------------------------------------------------------------------------

def _stone_house() -> Pattern:
    """5×5 stone house with walls, floor, door, chest."""
    S = PatternTiles.STONE_WALL
    F = PatternTiles.STONE_FLOOR
    D = PatternTiles.CLOSED_DOOR
    C = PatternTiles.CHEST
    tiles = [
        [PatternTile.wall(S), PatternTile.wall(S), PatternTile.wall(S), PatternTile.wall(S), PatternTile.wall(S)],
        [PatternTile.wall(S), PatternTile.ground(F), PatternTile.ground(F), PatternTile.ground(F), PatternTile.wall(S)],
        [PatternTile.wall(S), PatternTile.ground(F, [C]), PatternTile.ground(F), PatternTile.ground(F), PatternTile.wall(S)],
        [PatternTile.wall(S), PatternTile.ground(F), PatternTile.ground(F), PatternTile.ground(F, [D]), PatternTile.wall(S)],
        [PatternTile.wall(S), PatternTile.ground(F), PatternTile.ground(F), PatternTile.ground(F), PatternTile.wall(S)],
    ]
    return Pattern("stone_house", "5×5 stone house with chest and door", PatternCategory.BUILDING, 5, 5, tiles)


def _wooden_house() -> Pattern:
    """4×3 wooden house."""
    W = PatternTiles.WOOD_WALL
    F = PatternTiles.WOOD_FLOOR
    D = PatternTiles.OPEN_DOOR
    tiles = [
        [PatternTile.wall(W), PatternTile.wall(W), PatternTile.wall(W), PatternTile.wall(W)],
        [PatternTile.wall(W), PatternTile.ground(F), PatternTile.ground(F, [D]), PatternTile.wall(W)],
        [PatternTile.wall(W), PatternTile.ground(F), PatternTile.ground(F), PatternTile.wall(W)],
    ]
    return Pattern("wooden_house", "4×3 wooden house with door", PatternCategory.BUILDING, 4, 3, tiles)


def _tower() -> Pattern:
    """3×3 stone tower."""
    S = PatternTiles.STONE_WALL
    F = PatternTiles.STONE_FLOOR
    tiles = [
        [PatternTile.wall(S), PatternTile.wall(S), PatternTile.wall(S)],
        [PatternTile.wall(S), PatternTile.ground(F), PatternTile.wall(S)],
        [PatternTile.wall(S), PatternTile.ground(F), PatternTile.wall(S)],
    ]
    return Pattern("tower", "3×3 stone tower", PatternCategory.BUILDING, 3, 3, tiles)


def _castle_wall() -> Pattern:
    """1×5 castle wall segment."""
    S = PatternTiles.STONE_WALL
    tiles = [
        [PatternTile.wall(S)],
        [PatternTile.wall(S)],
        [PatternTile.wall(S)],
        [PatternTile.wall(S)],
        [PatternTile.wall(S)],
    ]
    return Pattern("castle_wall", "1×5 castle wall segment (vertical)", PatternCategory.BUILDING, 1, 5, tiles)


def _gate() -> Pattern:
    """3×1 gate structure."""
    S = PatternTiles.STONE_WALL
    D = PatternTiles.OPEN_DOOR
    tiles = [
        [PatternTile.wall(S), PatternTile.ground(0, [D]), PatternTile.wall(S)],
    ]
    return Pattern("gate", "3×1 gate with open door", PatternCategory.BUILDING, 3, 1, tiles)


def _tree_cluster() -> Pattern:
    """3×3 tree cluster."""
    T = PatternTiles.TREE
    G = PatternTiles.GRASS
    tiles = [
        [PatternTile.ground(G, [T]), PatternTile.ground(G, [T]), PatternTile.ground(G, [T])],
        [PatternTile.ground(G), PatternTile.ground(G, [T]), PatternTile.ground(G)],
        [PatternTile.ground(G, [T]), PatternTile.ground(G), PatternTile.ground(G, [T])],
    ]
    return Pattern("tree_cluster", "3×3 cluster of trees on grass", PatternCategory.NATURE, 3, 3, tiles)


def _flower_garden() -> Pattern:
    """3×3 flower garden."""
    F = PatternTiles.FLOWER
    G = PatternTiles.GRASS
    tiles = [
        [PatternTile.ground(G, [F]), PatternTile.ground(G, [F]), PatternTile.ground(G, [F])],
        [PatternTile.ground(G, [F]), PatternTile.ground(G), PatternTile.ground(G, [F])],
        [PatternTile.ground(G, [F]), PatternTile.ground(G, [F]), PatternTile.ground(G, [F])],
    ]
    return Pattern("flower_garden", "3×3 flower garden", PatternCategory.NATURE, 3, 3, tiles)


def _pond() -> Pattern:
    """5×5 pond."""
    W = PatternTiles.WATER
    S = PatternTiles.SAND
    G = PatternTiles.GRASS
    tiles = [
        [PatternTile.ground(G), PatternTile.ground(S), PatternTile.ground(S), PatternTile.ground(S), PatternTile.ground(G)],
        [PatternTile.ground(S), PatternTile.ground(W), PatternTile.ground(W), PatternTile.ground(W), PatternTile.ground(S)],
        [PatternTile.ground(S), PatternTile.ground(W), PatternTile.ground(W), PatternTile.ground(W), PatternTile.ground(S)],
        [PatternTile.ground(S), PatternTile.ground(W), PatternTile.ground(W), PatternTile.ground(W), PatternTile.ground(S)],
        [PatternTile.ground(G), PatternTile.ground(S), PatternTile.ground(S), PatternTile.ground(S), PatternTile.ground(G)],
    ]
    return Pattern("pond", "5×5 pond with sand border", PatternCategory.NATURE, 5, 5, tiles)


def _rock_formation() -> Pattern:
    """3×2 rock formation."""
    R = PatternTiles.ROCK
    G = PatternTiles.GRASS
    tiles = [
        [PatternTile.ground(G, [R]), PatternTile.ground(G), PatternTile.ground(G, [R])],
        [PatternTile.ground(G), PatternTile.ground(G, [R]), PatternTile.ground(G)],
    ]
    return Pattern("rock_formation", "3×2 rock formation", PatternCategory.NATURE, 3, 2, tiles)


def _stone_room() -> Pattern:
    """6×6 stone dungeon room."""
    S = PatternTiles.STONE_WALL
    F = PatternTiles.STONE_FLOOR
    tiles = [
        [PatternTile.wall(S), PatternTile.wall(S), PatternTile.wall(S), PatternTile.wall(S), PatternTile.wall(S), PatternTile.wall(S)],
        [PatternTile.wall(S), PatternTile.ground(F), PatternTile.ground(F), PatternTile.ground(F), PatternTile.ground(F), PatternTile.wall(S)],
        [PatternTile.wall(S), PatternTile.ground(F), PatternTile.ground(F), PatternTile.ground(F), PatternTile.ground(F), PatternTile.wall(S)],
        [PatternTile.wall(S), PatternTile.ground(F), PatternTile.ground(F), PatternTile.ground(F), PatternTile.ground(F), PatternTile.wall(S)],
        [PatternTile.wall(S), PatternTile.ground(F), PatternTile.ground(F), PatternTile.ground(F), PatternTile.ground(F), PatternTile.wall(S)],
        [PatternTile.wall(S), PatternTile.wall(S), PatternTile.wall(S), PatternTile.wall(S), PatternTile.wall(S), PatternTile.wall(S)],
    ]
    return Pattern("stone_room", "6×6 stone dungeon room", PatternCategory.DUNGEON, 6, 6, tiles)


def _prison_cell() -> Pattern:
    """3×3 prison cell."""
    S = PatternTiles.STONE_WALL
    F = PatternTiles.STONE_FLOOR
    tiles = [
        [PatternTile.wall(S), PatternTile.wall(S), PatternTile.wall(S)],
        [PatternTile.wall(S), PatternTile.ground(F), PatternTile.wall(S)],
        [PatternTile.wall(S), PatternTile.ground(F), PatternTile.wall(S)],
    ]
    return Pattern("prison_cell", "3×3 prison cell", PatternCategory.DUNGEON, 3, 3, tiles)


def _torture_chamber() -> Pattern:
    """4×4 torture chamber."""
    S = PatternTiles.STONE_WALL
    F = PatternTiles.STONE_FLOOR
    T = PatternTiles.TABLE
    tiles = [
        [PatternTile.wall(S), PatternTile.wall(S), PatternTile.wall(S), PatternTile.wall(S)],
        [PatternTile.wall(S), PatternTile.ground(F), PatternTile.ground(F), PatternTile.wall(S)],
        [PatternTile.wall(S), PatternTile.ground(F, [T]), PatternTile.ground(F), PatternTile.wall(S)],
        [PatternTile.wall(S), PatternTile.wall(S), PatternTile.wall(S), PatternTile.wall(S)],
    ]
    return Pattern("torture_chamber", "4×4 torture chamber with table", PatternCategory.DUNGEON, 4, 4, tiles)


def _stone_path() -> Pattern:
    """1×5 stone path."""
    D = PatternTiles.DIRT
    tiles = [
        [PatternTile.ground(D)],
        [PatternTile.ground(D)],
        [PatternTile.ground(D)],
        [PatternTile.ground(D)],
        [PatternTile.ground(D)],
    ]
    return Pattern("stone_path", "1×5 dirt path (vertical)", PatternCategory.ROAD, 1, 5, tiles)


def _bridge_horizontal() -> Pattern:
    """5×3 horizontal bridge."""
    W = PatternTiles.WATER
    D = PatternTiles.DIRT
    S = PatternTiles.STONE_WALL
    tiles = [
        [PatternTile.ground(W), PatternTile.ground(W), PatternTile.ground(W), PatternTile.ground(W), PatternTile.ground(W)],
        [PatternTile.wall(S), PatternTile.ground(D), PatternTile.ground(D), PatternTile.ground(D), PatternTile.wall(S)],
        [PatternTile.ground(W), PatternTile.ground(W), PatternTile.ground(W), PatternTile.ground(W), PatternTile.ground(W)],
    ]
    return Pattern("bridge_horizontal", "5×3 horizontal bridge over water", PatternCategory.ROAD, 5, 3, tiles)


def _bridge_vertical() -> Pattern:
    """3×5 vertical bridge."""
    W = PatternTiles.WATER
    D = PatternTiles.DIRT
    S = PatternTiles.STONE_WALL
    tiles = [
        [PatternTile.ground(W), PatternTile.ground(D), PatternTile.ground(W)],
        [PatternTile.ground(W), PatternTile.ground(D), PatternTile.ground(W)],
        [PatternTile.ground(W), PatternTile.ground(D), PatternTile.ground(W)],
        [PatternTile.ground(W), PatternTile.ground(D), PatternTile.ground(W)],
        [PatternTile.wall(S), PatternTile.ground(D), PatternTile.wall(S)],
    ]
    return Pattern("bridge_vertical", "3×5 vertical bridge over water", PatternCategory.ROAD, 3, 5, tiles)


def _fountain() -> Pattern:
    """3×3 fountain."""
    S = PatternTiles.STONE_WALL
    W = PatternTiles.WATER
    F = PatternTiles.STONE_FLOOR
    tiles = [
        [PatternTile.wall(S), PatternTile.ground(W), PatternTile.wall(S)],
        [PatternTile.ground(W), PatternTile.ground(W), PatternTile.ground(W)],
        [PatternTile.wall(S), PatternTile.ground(W), PatternTile.wall(S)],
    ]
    return Pattern("fountain", "3×3 fountain", PatternCategory.WATER, 3, 3, tiles)


def _well() -> Pattern:
    """1×1 well."""
    S = PatternTiles.STONE_WALL
    W = PatternTiles.WATER
    tiles = [
        [PatternTile.ground(W, [S])],
    ]
    return Pattern("well", "1×1 stone well with water", PatternCategory.WATER, 1, 1, tiles)


# ---------------------------------------------------------------------------
# TilePatternLibrary
# ---------------------------------------------------------------------------

class TilePatternLibrary:
    """Registry of reusable tile patterns.

    Provides methods to list, query, and apply patterns to maps.

    Parameters
    ----------
    extra_patterns : list[Pattern], optional
        Additional custom patterns to register alongside the built-ins.
    """

    def __init__(self, extra_patterns: Optional[List[Pattern]] = None):
        self._patterns: Dict[str, Pattern] = {}
        # Register all built-in patterns
        for p in self._builtin_patterns():
            self._patterns[p.name] = p
        # Register extra patterns
        if extra_patterns:
            for p in extra_patterns:
                self._patterns[p.name] = p

    @staticmethod
    def _builtin_patterns() -> List[Pattern]:
        return [
            _stone_house(),
            _wooden_house(),
            _tower(),
            _castle_wall(),
            _gate(),
            _tree_cluster(),
            _flower_garden(),
            _pond(),
            _rock_formation(),
            _stone_room(),
            _prison_cell(),
            _torture_chamber(),
            _stone_path(),
            _bridge_horizontal(),
            _bridge_vertical(),
            _fountain(),
            _well(),
        ]

    def get_pattern(self, name: str) -> Pattern:
        """Get a pattern by name.

        Raises
        ------
        KeyError
            If no pattern with the given name exists.
        """
        if name not in self._patterns:
            available = ", ".join(sorted(self._patterns.keys()))
            raise KeyError(f"Pattern not found: {name!r}. Available: {available}")
        return self._patterns[name]

    def list_patterns(self, category: Optional[PatternCategory] = None) -> List[Pattern]:
        """List all patterns, optionally filtered by category."""
        patterns = list(self._patterns.values())
        if category is not None:
            patterns = [p for p in patterns if p.category == category]
        return patterns

    def list_pattern_names(self, category: Optional[PatternCategory] = None) -> List[str]:
        """List pattern names, optionally filtered by category."""
        return [p.name for p in self.list_patterns(category=category)]

    def apply_pattern(
        self,
        map_data: MapData,
        pattern_name: str,
        x: int,
        y: int,
        z: int,
        overwrite: bool = False,
    ) -> int:
        """Apply a pattern to the map at the given position.

        Parameters
        ----------
        map_data : MapData
            Target map (modified in-place).
        pattern_name : str
            Name of the pattern to apply.
        x, y, z : int
            Top-left anchor position.
        overwrite : bool
            If ``True``, replace existing tiles at the pattern position.
            If ``False``, skip tiles that already exist at those coordinates.

        Returns
        -------
        int
            Number of tiles placed.
        """
        pattern = self.get_pattern(pattern_name)
        placed = 0

        # Build a set of existing tile keys for fast lookup
        existing_keys: set = {(t.x, t.y, t.z) for t in map_data.tiles}

        for py in range(pattern.height):
            for px in range(pattern.width):
                ptile = pattern.tiles[py][px]
                # Skip empty pattern tiles
                if ptile.ground_id == 0 and not ptile.items:
                    continue

                tx = x + px
                ty = y + py
                key = (tx, ty, z)

                if not overwrite and key in existing_keys:
                    continue

                items = [ItemData(id=item_id) for item_id in ptile.items]
                tile = TileData(
                    x=tx, y=ty, z=z,
                    ground_id=ptile.ground_id,
                    items=items,
                    flags=ptile.flags,
                )
                map_data.tiles.append(tile)
                existing_keys.add(key)
                placed += 1

        return placed

    def create_custom_pattern(
        self,
        name: str,
        tiles_grid: List[List[Dict[str, Any]]],
        description: str = "",
        category: PatternCategory = PatternCategory.CUSTOM,
    ) -> Pattern:
        """Create and register a custom pattern from a grid of dicts.

        Each dict in the grid can have keys: ``"ground_id"``, ``"items"``
        (list of item IDs), ``"flags"`` (int).

        Returns
        -------
        Pattern
            The newly created and registered pattern.
        """
        rows: List[List[PatternTile]] = []
        height = len(tiles_grid)
        width = max(len(row) for row in tiles_grid) if tiles_grid else 0

        for row in tiles_grid:
            tile_row: List[PatternTile] = []
            for cell in row:
                if isinstance(cell, dict):
                    ptile = PatternTile(
                        ground_id=cell.get("ground_id", 0),
                        items=cell.get("items", []),
                        flags=TileFlag(cell.get("flags", 0)),
                    )
                else:
                    ptile = PatternTile.empty()
                tile_row.append(ptile)
            # Pad to uniform width
            while len(tile_row) < width:
                tile_row.append(PatternTile.empty())
            rows.append(tile_row)

        pattern = Pattern(
            name=name,
            description=description or f"Custom pattern: {name}",
            category=category,
            width=width,
            height=height,
            tiles=rows,
        )
        self._patterns[name] = pattern
        return pattern
