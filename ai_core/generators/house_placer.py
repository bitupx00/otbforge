"""House placer for defining house rectangles with tiles, doors, and interiors.

The HousePlacer creates house rectangles on a map with:
  - Wall tiles around the perimeter
  - Interior floor tiles
  - House IDs on all interior tiles
  - Door tiles with house_door_id
  - Furniture items (bed, table, chair, chest)
  - Town association for each house
  - Integration with existing map data

Houses are placed as rectangular areas with walls, a door entry point,
and interior tiles marked with a house_id for the OTBM house system.
"""

import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from ai_core.otbm_types import (
    ItemData,
    MapData,
    TileData,
    Tiles,
)


# ---------------------------------------------------------------------------
# Tile IDs for house construction
# ---------------------------------------------------------------------------

class HouseTiles:
    """Tile IDs used for house construction."""
    STONE_WALL = 1010
    WOOD_WALL = 1018
    STONE_FLOOR = 410
    WOOD_FLOOR = 355
    CLOSED_DOOR = 1209
    OPEN_DOOR = 1210
    TABLE = 1666
    CHAIR = 1664
    BED = 1670
    CHEST = 2853
    CRATE = 2854
    DRAWER = 3757


# ---------------------------------------------------------------------------
# HousePlacer
# ---------------------------------------------------------------------------

@dataclass
class HousePlacer:
    """Place house rectangles on a map with proper house tiles.

    Parameters
    ----------
    map_data : MapData or None
        Base map to place houses on.
    seed : int
        RNG seed for reproducibility.
    wall_id : int
        Tile ID for house walls.
    floor_id : int
        Tile ID for interior floors.
    door_id : int
        Tile ID for house doors.
    starting_house_id : int
        First house_id to use. Subsequent houses get incremented IDs.
    town_id : int
        Town ID that houses belong to.
    """

    map_data: Optional[MapData] = None
    seed: int = 42
    wall_id: int = HouseTiles.STONE_WALL
    floor_id: int = HouseTiles.STONE_FLOOR
    door_id: int = HouseTiles.CLOSED_DOOR
    starting_house_id: int = 1
    town_id: int = 1
    width: int = 256
    height: int = 256

    def generate(self) -> MapData:
        """Return the map_data (use place_house/place_houses first)."""
        return self.map_data or MapData(width=self.width, height=self.height)

    def place_house(
        self,
        x: int, y: int, w: int, h: int,
        house_id: Optional[int] = None,
        door_side: str = "south",
        furniture: bool = True,
    ) -> int:
        """Place a single house rectangle and return its house_id.

        Parameters
        ----------
        x, y : int
            Top-left corner of the house.
        w, h : int
            Width and height of the house (minimum 3x3).
        house_id : int or None
            Specific house ID, or auto-increment if None.
        door_side : str
            Side to place the door: 'north', 'south', 'east', 'west'.
        furniture : bool
            Whether to place furniture inside.
        """
        if house_id is None:
            house_id = self.starting_house_id
        self.starting_house_id = max(self.starting_house_id, house_id + 1)

        md = self.map_data
        if md is None:
            md = MapData(width=self.width, height=self.height)
            self.map_data = md

        z = 0

        # Place walls and floor
        for rx in range(w):
            for ry in range(h):
                xx, yy = x + rx, y + ry
                is_edge = (rx == 0 or rx == w - 1 or ry == 0 or ry == h - 1)

                if is_edge:
                    tile = self._get_or_create_tile(md, xx, yy, z)
                    tile.ground_id = self.wall_id
                    tile.items = []
                else:
                    tile = self._get_or_create_tile(md, xx, yy, z)
                    tile.ground_id = self.floor_id
                    tile.house_id = house_id

        # Place door
        door_x, door_y = self._get_door_position(x, y, w, h, door_side)
        door_tile = self._get_or_create_tile(md, door_x, door_y, z)
        door_tile.ground_id = self.door_id
        door_item = ItemData(id=self.door_id, house_door_id=1)
        door_tile.items = [door_item]
        door_tile.house_id = house_id

        # Place furniture
        if furniture and w >= 4 and h >= 4:
            self._place_furniture(md, x, y, w, h, z, house_id)

        return house_id

    def place_houses(
        self,
        houses_spec: List[Tuple[int, int, int, int]],
        door_side: str = "south",
        furniture: bool = True,
    ) -> List[int]:
        """Place multiple houses from a list of (x, y, w, h) specs.

        Returns list of assigned house_ids.
        """
        house_ids = []
        for (x, y, w, h) in houses_spec:
            hid = self.place_house(x, y, w, h, door_side=door_side,
                                   furniture=furniture)
            house_ids.append(hid)
        return house_ids

    def place_random_houses(
        self,
        count: int,
        region_x: int, region_y: int,
        region_w: int, region_h: int,
        min_size: int = 4,
        max_size: int = 7,
        spacing: int = 2,
    ) -> List[int]:
        """Place random non-overlapping houses in a region.

        Returns list of assigned house_ids.
        """
        rng = random.Random(self.seed)
        placed_rects: List[Tuple[int, int, int, int]] = []
        house_ids = []

        for _ in range(count * 10):  # max attempts
            if len(house_ids) >= count:
                break

            w = rng.randint(min_size, max_size)
            h = rng.randint(min_size, max_size)
            bx = rng.randint(region_x, region_x + region_w - w)
            by = rng.randint(region_y, region_y + region_h - h)

            # Check overlap
            overlap = False
            for (ex, ey, ew, eh) in placed_rects:
                if (bx < ex + ew + spacing and bx + w + spacing > ex and
                        by < ey + eh + spacing and by + h + spacing > ey):
                    overlap = True
                    break

            if not overlap:
                hid = self.place_house(bx, by, w, h)
                placed_rects.append((bx, by, w, h))
                house_ids.append(hid)

        return house_ids

    def _get_or_create_tile(self, md: MapData, x: int, y: int, z: int) -> TileData:
        """Get existing tile or create a new one."""
        for tile in md.tiles:
            if tile.x == x and tile.y == y and tile.z == z:
                return tile
        tile = TileData(x=x, y=y, z=z)
        md.tiles.append(tile)
        return tile

    def _get_door_position(self, x: int, y: int, w: int, h: int,
                           side: str) -> Tuple[int, int]:
        """Calculate door position based on side."""
        if side == "north":
            return (x + w // 2, y)
        elif side == "south":
            return (x + w // 2, y + h - 1)
        elif side == "east":
            return (x + w - 1, y + h // 2)
        elif side == "west":
            return (x, y + h // 2)
        else:
            return (x + w // 2, y + h - 1)

    def _place_furniture(self, md: MapData, x: int, y: int, w: int, h: int,
                         z: int, house_id: int):
        """Place furniture items inside a house."""
        # Bed in top-left area
        bed_x = x + 1
        bed_y = y + 1
        tile = self._get_or_create_tile(md, bed_x, bed_y, z)
        tile.items.append(ItemData(id=HouseTiles.BED))

        # Table in center
        table_x = x + w // 2
        table_y = y + h // 2
        tile = self._get_or_create_tile(md, table_x, table_y, z)
        tile.items.append(ItemData(id=HouseTiles.TABLE))

        # Chair next to table
        if w > 4:
            chair_x = table_x + 1
            tile = self._get_or_create_tile(md, chair_x, table_y, z)
            tile.items.append(ItemData(id=HouseTiles.CHAIR))

        # Chest near door
        chest_x = x + w // 2
        chest_y = y + h - 2
        tile = self._get_or_create_tile(md, chest_x, chest_y, z)
        tile.items.append(ItemData(id=HouseTiles.CHEST))

    def count_house_tiles(self, house_id: int) -> int:
        """Count tiles with the given house_id."""
        if not self.map_data:
            return 0
        return sum(1 for t in self.map_data.tiles if t.house_id == house_id)

    def get_house_rect(self, house_id: int) -> Optional[Tuple[int, int, int, int]]:
        """Get bounding rectangle of a house by its house_id."""
        if not self.map_data:
            return None
        tiles = [t for t in self.map_data.tiles if t.house_id == house_id]
        if not tiles:
            return None
        min_x = min(t.x for t in tiles)
        max_x = max(t.x for t in tiles)
        min_y = min(t.y for t in tiles)
        max_y = max(t.y for t in tiles)
        return (min_x, min_y, max_x - min_x + 1, max_y - min_y + 1)
