"""
Map Stitcher — Combine multiple maps into one large map.

Supports several layout strategies (horizontal, vertical, grid, auto) and
configurable conflict resolution when tiles from different source maps
overlap.  Towns, waypoints, spawns, NPC spawns, and houses are merged
with automatic ID remapping to avoid collisions.

Usage::

    from ai_core.map_stitcher import MapStitcher

    result = MapStitcher.stitch_maps([map_a, map_b], layout="horizontal")
    result = MapStitcher.stitch_files(["a.otbm", "b.otbm"])
"""

from __future__ import annotations

import math
from copy import deepcopy
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from ai_core.models import (
    HouseData,
    ItemData,
    MapData,
    NPCSpawnData,
    Position,
    SpawnData,
    TileData,
    TileFlag,
    TownData,
    WaypointData,
)
from ai_core.otbm_reader import OTBMReader


# ---------------------------------------------------------------------------
# Offset helper
# ---------------------------------------------------------------------------

@dataclass
class MapOffset:
    """Describes where a source map is placed in the stitched result."""
    offset_x: int
    offset_y: int


# ---------------------------------------------------------------------------
# MapStitcher
# ---------------------------------------------------------------------------

class MapStitcher:
    """Combine multiple :class:`MapData` instances into a single large map.

    Parameters
    ----------
    conflict_strategy : str
        How to resolve overlapping tiles.  One of ``"first"``, ``"last"``,
        or ``"merge"``.  Default is ``"first"``.
    """

    def __init__(self, conflict_strategy: str = "first"):
        if conflict_strategy not in ("first", "last", "merge"):
            raise ValueError(f"Unknown conflict strategy: {conflict_strategy!r}")
        self.conflict_strategy = conflict_strategy

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def stitch_maps(
        self,
        maps: List[MapData],
        layout: str = "auto",
    ) -> MapData:
        """Stitch *maps* together and return a new :class:`MapData`.

        Parameters
        ----------
        maps : list[MapData]
            2–16 source maps.
        layout : str
            ``"horizontal"``, ``"vertical"``, ``"grid"``, or ``"auto"``.
        """
        if not maps:
            raise ValueError("No maps provided to stitch")
        if len(maps) < 2:
            raise ValueError("Need at least 2 maps to stitch")
        if len(maps) > 16:
            raise ValueError("Maximum 16 maps supported for stitching")

        offsets = self._calculate_layout(maps, layout)
        return self._stitch(maps, offsets)

    def stitch_files(self, filenames: List[str], layout: str = "auto") -> MapData:
        """Load ``.otbm`` files and stitch them together.

        Parameters
        ----------
        filenames : list[str]
            Paths to ``.otbm`` files (2–16).
        layout : str
            Same as :meth:`stitch_maps`.
        """
        if not filenames:
            raise ValueError("No filenames provided")
        if len(filenames) < 2:
            raise ValueError("Need at least 2 files to stitch")
        if len(filenames) > 16:
            raise ValueError("Maximum 16 files supported for stitching")

        maps: List[MapData] = []
        for path in filenames:
            maps.append(OTBMReader.from_file(path))
        return self.stitch_maps(maps, layout=layout)

    # ------------------------------------------------------------------
    # Layout calculation
    # ------------------------------------------------------------------

    @staticmethod
    def _calculate_layout(
        maps: List[MapData],
        layout: str,
    ) -> List[MapOffset]:
        """Return a list of :class:`MapOffset` — one per source map."""
        n = len(maps)

        if layout == "horizontal":
            return MapStitcher._layout_horizontal(maps)
        elif layout == "vertical":
            return MapStitcher._layout_vertical(maps)
        elif layout == "grid":
            return MapStitcher._layout_grid(maps)
        elif layout == "auto":
            return MapStitcher._layout_auto(maps)
        else:
            raise ValueError(f"Unknown layout: {layout!r}")

    @staticmethod
    def _layout_horizontal(maps: List[MapData]) -> List[MapOffset]:
        offsets: List[MapOffset] = []
        x_off = 0
        for m in maps:
            offsets.append(MapOffset(offset_x=x_off, offset_y=0))
            x_off += m.width
        return offsets

    @staticmethod
    def _layout_vertical(maps: List[MapData]) -> List[MapOffset]:
        offsets: List[MapOffset] = []
        y_off = 0
        for m in maps:
            offsets.append(MapOffset(offset_x=0, offset_y=y_off))
            y_off += m.height
        return offsets

    @staticmethod
    def _layout_grid(maps: List[MapData]) -> List[MapOffset]:
        n = len(maps)
        cols = math.ceil(math.sqrt(n))
        rows = math.ceil(n / cols)

        # Compute per-column max-width
        col_widths: List[int] = [0] * cols
        for i, m in enumerate(maps):
            col = i % cols
            col_widths[col] = max(col_widths[col], m.width)

        offsets: List[MapOffset] = [MapOffset(0, 0)] * n
        y_cursor = 0
        row_height = 0

        for idx, m in enumerate(maps):
            row_idx = idx // cols
            col_idx = idx % cols

            x_off = sum(col_widths[c] for c in range(col_idx))

            offsets[idx] = MapOffset(offset_x=x_off, offset_y=y_cursor)

            # After finishing a row, advance y cursor
            if col_idx == cols - 1 or idx == n - 1:
                row_height = max(
                    m2.height
                    for i2, m2 in enumerate(maps)
                    if i2 // cols == row_idx
                )
                y_cursor += row_height

        return offsets

    @staticmethod
    def _layout_auto(maps: List[MapData]) -> List[MapOffset]:
        n = len(maps)
        if n <= 3:
            return MapStitcher._layout_horizontal(maps)
        elif n <= 4:
            return MapStitcher._layout_grid(maps)
        else:
            # For larger counts, use grid (more square, better fit)
            return MapStitcher._layout_grid(maps)

    # ------------------------------------------------------------------
    # Core stitching
    # ------------------------------------------------------------------

    def _stitch(
        self,
        maps: List[MapData],
        offsets: List[MapOffset],
    ) -> MapData:
        """Perform the actual stitching of tiles and metadata."""

        # Build tile grid: (x, y, z) -> TileData
        tile_grid: Dict[Tuple[int, int, int], TileData] = {}

        for map_idx, (src, off) in enumerate(zip(maps, offsets)):
            for tile in src.tiles:
                nx = tile.x + off.offset_x
                ny = tile.y + off.offset_y
                nz = tile.z
                key = (nx, ny, nz)
                new_tile = TileData(
                    x=nx, y=ny, z=nz,
                    ground_id=tile.ground_id,
                    items=[deepcopy(it) for it in tile.items],
                    flags=tile.flags,
                    house_id=tile.house_id,
                )
                if key in tile_grid:
                    existing = tile_grid[key]
                    tile_grid[key] = self._resolve_conflict(existing, new_tile)
                else:
                    tile_grid[key] = new_tile

        # Result dimensions
        max_x = max(t[0] for t in tile_grid) if tile_grid else 0
        max_y = max(t[1] for t in tile_grid) if tile_grid else 0
        result_width = max_x + 1
        result_height = max_y + 1

        result = MapData(
            width=result_width,
            height=result_height,
            description=f"Stitched map ({len(maps)} sources)",
            tiles=list(tile_grid.values()),
        )

        # --- Merge towns ---
        next_town_id = self._max_town_id(maps) + 1
        used_ids: Dict[int, int] = {}  # old -> new
        for src, off in zip(maps, offsets):
            for town in src.towns:
                new_id = self._remap_id(used_ids, town.id, next_town_id)
                next_town_id = max(next_town_id, new_id + 1)
                result.towns.append(TownData(
                    id=new_id,
                    name=town.name,
                    temple=Position(
                        x=town.temple.x + off.offset_x,
                        y=town.temple.y + off.offset_y,
                        z=town.temple.z,
                    ),
                ))

        # --- Merge waypoints ---
        wp_names: set = set()
        for src, off in zip(maps, offsets):
            for wp in src.waypoints:
                name = wp.name
                if name in wp_names:
                    # Make unique
                    name = f"{name}_{off.offset_x}_{off.offset_y}"
                wp_names.add(name)
                result.waypoints.append(WaypointData(
                    name=name,
                    pos=Position(
                        x=wp.pos.x + off.offset_x,
                        y=wp.pos.y + off.offset_y,
                        z=wp.pos.z,
                    ),
                ))

        # --- Merge spawns ---
        for src, off in zip(maps, offsets):
            for spawn in src.spawns:
                result.spawns.append(SpawnData(
                    x=spawn.x + off.offset_x,
                    y=spawn.y + off.offset_y,
                    z=spawn.z,
                    radius=spawn.radius,
                    monsters=list(spawn.monsters),
                ))

        # --- Merge NPC spawns ---
        for src, off in zip(maps, offsets):
            for npc in src.npc_spawns:
                result.npc_spawns.append(NPCSpawnData(
                    x=npc.x + off.offset_x,
                    y=npc.y + off.offset_y,
                    z=npc.z,
                    npc_name=npc.npc_name,
                    direction=npc.direction,
                ))

        # --- Merge houses ---
        next_house_id = self._max_house_id(maps) + 1
        h_used_ids: Dict[int, int] = {}
        for src, off in zip(maps, offsets):
            for house in src.houses:
                new_id = self._remap_id(h_used_ids, house.id, next_house_id)
                next_house_id = max(next_house_id, new_id + 1)
                result.houses.append(HouseData(
                    id=new_id,
                    name=house.name,
                    rent=house.rent,
                    town_id=house.town_id,
                    size=house.size,
                    tile_ids=list(house.tile_ids),
                ))
                # Remap house_id on tiles
                for tile in result.tiles:
                    if tile.house_id == house.id and tile.x >= off.offset_x:
                        tile.house_id = new_id

        return result

    # ------------------------------------------------------------------
    # Conflict resolution
    # ------------------------------------------------------------------

    def _resolve_conflict(self, existing: TileData, incoming: TileData) -> TileData:
        """Resolve an overlap between two tiles."""
        if self.conflict_strategy == "first":
            return existing
        elif self.conflict_strategy == "last":
            return incoming
        elif self.conflict_strategy == "merge":
            merged_items = list(existing.items) + list(incoming.items)
            # Prefer incoming ground if existing has none
            ground = existing.ground_id or incoming.ground_id
            return TileData(
                x=existing.x, y=existing.y, z=existing.z,
                ground_id=ground,
                items=merged_items,
                flags=existing.flags | incoming.flags,
                house_id=existing.house_id or incoming.house_id,
            )
        else:
            return existing

    # ------------------------------------------------------------------
    # ID helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _max_town_id(maps: List[MapData]) -> int:
        m = 0
        for src in maps:
            for town in src.towns:
                if town.id > m:
                    m = town.id
        return m

    @staticmethod
    def _max_house_id(maps: List[MapData]) -> int:
        m = 0
        for src in maps:
            for house in src.houses:
                if house.id > m:
                    m = house.id
        return m

    @staticmethod
    def _remap_id(used: Dict[int, int], old_id: int, fallback: int) -> int:
        if old_id in used:
            return used[old_id]
        used[old_id] = old_id  # first occurrence keeps its id
        return old_id
