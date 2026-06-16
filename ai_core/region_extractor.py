"""
Region Extractor — Extract rectangular regions, town areas, or single
floors from an OTBM map.

All extracted data is re-anchored so that the new origin (0, 0) corresponds
to the top-left corner of the extracted region.  Towns, waypoints, spawns,
NPC spawns, and houses are remapped relative to the new origin.

Usage::

    from ai_core.region_extractor import RegionExtractor, Region

    region = Region(x1=100, y1=200, x2=300, y2=400)
    small = RegionExtractor.extract(map_data, region)

    around_town = RegionExtractor.extract_by_town(map_data, "Thais")
    floor7 = RegionExtractor.extract_floor(map_data, z_level=7)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from ai_core.models import (
    HouseData,
    MapData,
    NPCSpawnData,
    Position,
    SpawnData,
    TownData,
    WaypointData,
)
from ai_core.otbm_reader import OTBMReader


# ---------------------------------------------------------------------------
# Region descriptor
# ---------------------------------------------------------------------------

@dataclass
class Region:
    """Rectangular region with optional Z-level filter.

    Attributes
    ----------
    x1, y1, x2, y2 : int
        Bounding box in map coordinates (inclusive).
    z_min, z_max : int
        Minimum and maximum Z levels to include.  Default ``0`` / ``15``
        means all floors.
    """
    x1: int
    y1: int
    x2: int
    y2: int
    z_min: int = 0
    z_max: int = 15

    @property
    def width(self) -> int:
        return max(self.x2 - self.x1 + 1, 0)

    @property
    def height(self) -> int:
        return max(self.y2 - self.y1 + 1, 0)

    def contains(self, x: int, y: int, z: int) -> bool:
        return (
            self.x1 <= x <= self.x2
            and self.y1 <= y <= self.y2
            and self.z_min <= z <= self.z_max
        )

    def normalize(self) -> "Region":
        """Return a region with x1<=x2 and y1<=y2."""
        return Region(
            x1=min(self.x1, self.x2),
            y1=min(self.y1, self.y2),
            x2=max(self.x1, self.x2),
            y2=max(self.y1, self.y2),
            z_min=self.z_min,
            z_max=self.z_max,
        )


# ---------------------------------------------------------------------------
# RegionExtractor
# ---------------------------------------------------------------------------

class RegionExtractor:
    """Extract sub-regions from a :class:`MapData` map."""

    DEFAULT_RADIUS = 30  # tiles around a town temple

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @staticmethod
    def extract(
        map_data: MapData,
        region: Region,
    ) -> MapData:
        """Extract a rectangular region and return a new :class:`MapData`.

        All coordinates are re-anchored so ``(x1, y1)`` becomes ``(0, 0)``.
        """
        region = region.normalize()
        off_x = region.x1
        off_y = region.y1

        new_tiles = []
        for tile in map_data.tiles:
            if region.contains(tile.x, tile.y, tile.z):
                new_tiles.append(_shift_tile(tile, -off_x, -off_y))

        result = MapData(
            width=region.width,
            height=region.height,
            description=f"Extracted region ({region.width}x{region.height})",
            tiles=new_tiles,
        )

        # Remap towns whose temple falls inside the region
        for town in map_data.towns:
            if region.contains(town.temple.x, town.temple.y, town.temple.z):
                result.towns.append(TownData(
                    id=town.id,
                    name=town.name,
                    temple=Position(
                        x=town.temple.x - off_x,
                        y=town.temple.y - off_y,
                        z=town.temple.z,
                    ),
                ))

        # Remap waypoints inside the region
        for wp in map_data.waypoints:
            if region.contains(wp.pos.x, wp.pos.y, wp.pos.z):
                result.waypoints.append(WaypointData(
                    name=wp.name,
                    pos=Position(
                        x=wp.pos.x - off_x,
                        y=wp.pos.y - off_y,
                        z=wp.pos.z,
                    ),
                ))

        # Remap spawns whose centre falls inside
        for spawn in map_data.spawns:
            if region.contains(spawn.x, spawn.y, spawn.z):
                result.spawns.append(SpawnData(
                    x=spawn.x - off_x,
                    y=spawn.y - off_y,
                    z=spawn.z,
                    radius=spawn.radius,
                    monsters=list(spawn.monsters),
                ))

        # Remap NPC spawns inside
        for npc in map_data.npc_spawns:
            if region.contains(npc.x, npc.y, npc.z):
                result.npc_spawns.append(NPCSpawnData(
                    x=npc.x - off_x,
                    y=npc.y - off_y,
                    z=npc.z,
                    npc_name=npc.npc_name,
                    direction=npc.direction,
                ))

        # Houses: include if any house tile falls inside region
        # Build set of house_ids whose tiles are in region
        house_ids_in_region: set = set()
        for tile in new_tiles:
            if tile.house_id > 0:
                house_ids_in_region.add(tile.house_id)
        for house in map_data.houses:
            if house.id in house_ids_in_region:
                result.houses.append(HouseData(
                    id=house.id,
                    name=house.name,
                    rent=house.rent,
                    town_id=house.town_id,
                    size=house.size,
                    tile_ids=list(house.tile_ids),
                ))

        return result

    @staticmethod
    def extract_by_town(
        map_data: MapData,
        town_name: str,
        radius: int = 30,
    ) -> MapData:
        """Extract a square region around a town's temple position.

        Parameters
        ----------
        map_data : MapData
            Source map.
        town_name : str
            Exact name of the town (case-sensitive).
        radius : int
            Half-side of the square in tiles.  Default 30 (gives a 61×61 area).
        """
        town = RegionExtractor._find_town(map_data, town_name)
        region = Region(
            x1=town.temple.x - radius,
            y1=town.temple.y - radius,
            x2=town.temple.x + radius,
            y2=town.temple.y + radius,
        )
        return RegionExtractor.extract(map_data, region)

    @staticmethod
    def extract_floor(map_data: MapData, z_level: int) -> MapData:
        """Extract all tiles on a single Z-level, re-anchored to ``(0, 0)``.

        Parameters
        ----------
        map_data : MapData
            Source map.
        z_level : int
            Floor to extract (0–15).
        """
        tiles_on_floor = [t for t in map_data.tiles if t.z == z_level]
        if not tiles_on_floor:
            return MapData(
                width=0,
                height=0,
                description=f"Floor {z_level} (empty)",
            )

        xs = [t.x for t in tiles_on_floor]
        ys = [t.y for t in tiles_on_floor]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)

        region = Region(x1=min_x, y1=min_y, x2=max_x, y2=max_y, z_min=z_level, z_max=z_level)
        return RegionExtractor.extract(map_data, region)

    @staticmethod
    def extract_file(
        path: str,
        region: Optional[Region] = None,
        town_name: Optional[str] = None,
        z_level: Optional[int] = None,
    ) -> MapData:
        """Extract from an ``.otbm`` file.

        Exactly one of *region*, *town_name*, or *z_level* must be provided.
        """
        if sum(1 for v in (region, town_name, z_level) if v is not None) != 1:
            raise ValueError("Provide exactly one of region, town_name, or z_level")

        map_data = OTBMReader.from_file(path)

        if region is not None:
            return RegionExtractor.extract(map_data, region)
        elif town_name is not None:
            return RegionExtractor.extract_by_town(map_data, town_name)
        elif z_level is not None:
            return RegionExtractor.extract_floor(map_data, z_level)
        else:
            raise ValueError("No extraction criteria provided")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _find_town(map_data: MapData, name: str) -> TownData:
        for town in map_data.towns:
            if town.name == name:
                return town
        raise ValueError(f"Town not found: {name!r}")


# ---------------------------------------------------------------------------
# Module-level helper
# ---------------------------------------------------------------------------

def _shift_tile(tile, dx: int, dy: int):
    """Return a copy of *tile* shifted by (dx, dy)."""
    from copy import deepcopy
    t = deepcopy(tile)
    t.x += dx
    t.y += dy
    return t
