"""Town/City generator with grid or radial street layouts and buildings.

Generates towns with structured streets (grid or radial pattern), multiple
building types (house, shop, temple, depot, tavern), a central plaza,
paved roads, perimeter fences, and town registration in MapData.

Features:
  - Grid layout: evenly-spaced perpendicular streets forming blocks
  - Radial layout: streets radiating from a central plaza
  - Random layout: pseudo-random road network
  - Style variants: medieval (stone/wood), tropical (sand/palm), winter (snow/ice)
  - Building interiors with furniture items
  - Temple with protection zone and town registration
  - Depot with depot chest items
"""

import math
import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from ai_core.otbm_types import (
    ItemData,
    MapData,
    NPCSpawnData,
    Position,
    TileData,
    TileFlags,
    TownData,
    Tiles,
)

# ---------------------------------------------------------------------------
# Tile IDs for town generation (supplement to Tiles)
# ---------------------------------------------------------------------------

class TownTiles:
    """Tile IDs used by the town generator."""
    # Walls
    STONE_WALL = 1010
    WOOD_WALL = 1018
    SAND_WALL = 1065
    ICE_WALL = 6891

    # Floors
    STONE_FLOOR = 410
    WOOD_FLOOR = 355
    SAND_FLOOR = 231
    ICE_FLOOR = 7731

    # Pavement / roads
    PAVEMENT = 432
    SAND_ROAD = 231
    SNOW_ROAD = 7731

    # Doors
    CLOSED_WOOD_DOOR = 1209
    OPEN_WOOD_DOOR = 1210
    CLOSED_STONE_DOOR = 1220
    OPEN_STONE_DOOR = 1221

    # Furniture
    TABLE = 1666
    CHAIR = 1664
    BED = 1670
    CHEST = 2853
    CRATE = 2854
    DEPOT_CHEST = 1740
    COUNTER = 1668
    BARREL = 2854
    PILLOW = 1674

    # Fences
    FENCE = 2712
    GATE = 2713

    # Special
    ALTAR = 2918

    # Trees (tropical)
    PALM_TREE = 2723


# ---------------------------------------------------------------------------
# Style definitions
# ---------------------------------------------------------------------------

TOWN_STYLES: Dict[str, dict] = {
    "medieval": {
        "wall": TownTiles.STONE_WALL,
        "floor": TownTiles.STONE_FLOOR,
        "road": TownTiles.PAVEMENT,
        "door_closed": TownTiles.CLOSED_STONE_DOOR,
        "door_open": TownTiles.OPEN_STONE_DOOR,
        "fence": TownTiles.FENCE,
    },
    "tropical": {
        "wall": TownTiles.WOOD_WALL,
        "floor": TownTiles.WOOD_FLOOR,
        "road": TownTiles.SAND_ROAD,
        "door_closed": TownTiles.CLOSED_WOOD_DOOR,
        "door_open": TownTiles.OPEN_WOOD_DOOR,
        "fence": TownTiles.PALM_TREE,
    },
    "winter": {
        "wall": TownTiles.ICE_WALL,
        "floor": TownTiles.ICE_FLOOR,
        "road": TownTiles.SNOW_ROAD,
        "door_closed": TownTiles.CLOSED_STONE_DOOR,
        "door_open": TownTiles.OPEN_STONE_DOOR,
        "fence": TownTiles.FENCE,
    },
}


# ---------------------------------------------------------------------------
# Building type definitions
# ---------------------------------------------------------------------------

@dataclass
class BuildingSpec:
    """Specification for a building type."""
    name: str
    min_width: int
    max_width: int
    min_height: int
    max_height: int
    weight: float  # relative probability
    is_special: bool = False
    is_temple: bool = False
    is_depot: bool = False


BUILDING_TYPES: List[BuildingSpec] = [
    BuildingSpec("house", 4, 6, 4, 6, weight=5.0),
    BuildingSpec("shop", 5, 7, 4, 6, weight=2.0),
    BuildingSpec("tavern", 6, 8, 5, 7, weight=1.5),
    BuildingSpec("temple", 8, 10, 8, 10, weight=0.0, is_special=True, is_temple=True),
    BuildingSpec("depot", 6, 8, 4, 6, weight=0.0, is_special=True, is_depot=True),
]


# ---------------------------------------------------------------------------
# TownGenerator
# ---------------------------------------------------------------------------

@dataclass
class TownGenerator:
    """Procedural town/city generator with structured layouts.

    Parameters
    ----------
    center_x, center_y : int
        Center position of the town on the map.
    size : int
        Approximate radius (grid) or radius (radial) in tiles.
    town_id : int
        Town ID for OTBM town registration.
    town_name : str
        Name of the town.
    style : str
        One of 'medieval', 'tropical', 'winter'.
    layout : str
        One of 'grid', 'radial', 'random'.
    seed : int
        RNG seed for reproducible generation.
    street_width : int
        Width of streets in tiles.
    has_fence : bool
        Whether to place fences around the town perimeter.
    num_buildings : int
        Target number of buildings to place.
    """

    center_x: int = 128
    center_y: int = 128
    size: int = 30
    town_id: int = 1
    town_name: str = "Sample Town"
    style: str = "medieval"
    layout: str = "grid"
    seed: int = 42
    street_width: int = 3
    has_fence: bool = True
    num_buildings: int = 15
    map_width: int = 256
    map_height: int = 256

    def generate(self, base_map: Optional[MapData] = None) -> MapData:
        """Generate town tiles and return a new MapData with the town added.

        If *base_map* is provided, town tiles are merged on top.
        """
        rng = random.Random(self.seed)
        style = TOWN_STYLES.get(self.style, TOWN_STYLES["medieval"])

        # Build tile grid from base_map or empty
        tile_grid: Dict[Tuple[int, int, int], TileData] = {}
        if base_map:
            for t in base_map.tiles:
                tile_grid[(t.x, t.y, t.z)] = t

        # Track modified tiles
        modified: List[TileData] = []
        npc_spawns: List[NPCSpawnData] = list(base_map.npc_spawns if base_map else [])
        towns: List[TownData] = list(base_map.towns if base_map else [])
        waypoints: List = list(base_map.waypoints if base_map else [])
        spawns: List = list(base_map.spawns if base_map else [])
        houses: List = list(getattr(base_map, 'houses', []) if base_map else [])

        cx, cy = self.center_x, self.center_y
        z = 0

        # --- Generate street layout ---
        street_cells: set = set()

        if self.layout == "grid":
            street_cells = self._layout_grid(cx, cy, style)
        elif self.layout == "radial":
            street_cells = self._layout_radial(cx, cy, style)
        else:
            street_cells = self._layout_random(cx, cy, style, rng)

        # Place street tiles
        for (sx, sy) in street_cells:
            tile = TileData(x=sx, y=sy, z=z, ground_id=style["road"])
            tile_grid[(sx, sy, z)] = tile

        # --- Central plaza ---
        plaza_cells = self._place_plaza(cx, cy, style)
        for (sx, sy) in plaza_cells:
            tile = TileData(
                x=sx, y=sy, z=z,
                ground_id=style["road"],
                flags=TileFlags.PROTECTIONZONE,
            )
            tile_grid[(sx, sy, z)] = tile

        # --- Place buildings ---
        temple_pos = None
        depot_pos = None
        building_rects: List[Tuple[int, int, int, int, str]] = []

        # First place temple
        temple_rect = self._find_building_spot(
            cx, cy, street_cells, building_rects,
            min_w=8, min_h=8, rng=rng
        )
        if temple_rect:
            bx, by, bw, bh = temple_rect
            self._place_building_rect(
                tile_grid, bx, by, bw, bh, style, "temple", rng
            )
            building_rects.append((bx, by, bw, bh, "temple"))
            temple_pos = Position(x=bx + bw // 2, y=by + bh // 2, z=z)

        # Place depot
        depot_rect = self._find_building_spot(
            cx, cy, street_cells, building_rects,
            min_w=6, min_h=4, rng=rng
        )
        if depot_rect:
            bx, by, bw, bh = depot_rect
            self._place_building_rect(
                tile_grid, bx, by, bw, bh, style, "depot", rng
            )
            building_rects.append((bx, by, bw, bh, "depot"))
            depot_pos = Position(x=bx + bw // 2, y=by + bh // 2, z=z)

        # Place regular buildings
        placed = 0
        attempts = 0
        while placed < self.num_buildings and attempts < self.num_buildings * 10:
            attempts += 1
            btype = self._pick_building_type(rng)
            min_w = btype.min_width
            min_h = btype.min_height
            max_w = btype.max_width
            max_h = btype.max_height
            bw = rng.randint(min_w, max_w)
            bh = rng.randint(min_h, max_h)

            rect = self._find_building_spot(
                cx, cy, street_cells, building_rects,
                min_w=bw, min_h=bh, rng=rng
            )
            if rect:
                bx, by, rw, rh = rect
                self._place_building_rect(
                    tile_grid, bx, by, rw, rh, style, btype.name, rng
                )
                building_rects.append((bx, by, rw, rh, btype.name))
                placed += 1

        # --- Place fences around perimeter ---
        if self.has_fence:
            self._place_fence_safe(tile_grid, cx, cy, style, street_cells)

        # --- Register town ---
        if temple_pos is None:
            temple_pos = Position(x=cx, y=cy, z=z)

        town = TownData(
            id=self.town_id,
            name=self.town_name,
            temple=temple_pos,
        )
        towns.append(town)

        # Place NPCs in temple
        npc_spawns.append(NPCSpawnData(
            x=temple_pos.x, y=temple_pos.y, z=z,
            npc_name="TownCrier",
        ))

        # Return merged map
        all_tiles = list(tile_grid.values())
        result = MapData(
            width=base_map.width if base_map else self.map_width,
            height=base_map.height if base_map else self.map_height,
            description=base_map.description if base_map else f"Town: {self.town_name}",
            tiles=all_tiles,
            towns=towns,
            npc_spawns=npc_spawns,
            waypoints=waypoints,
            spawns=spawns,
        )
        if hasattr(result, 'houses') and houses:
            result.houses = houses
        return result

    # ---- Layout generators ----

    def _layout_grid(self, cx: int, cy: int, style: dict) -> set:
        """Generate a grid of streets around center."""
        cells: set = set()
        sw = self.street_width
        s = self.size

        # Vertical streets at regular intervals
        num_v = max(2, s // 10)
        num_h = max(2, s // 10)

        for i in range(num_v):
            x = cx - s + (i + 1) * (2 * s) // (num_v + 1)
            x -= sw // 2
            for dy in range(-s - 2, s + 3):
                for dx in range(sw):
                    cells.add((x + dx, cy + dy))

        for i in range(num_h):
            y = cy - s + (i + 1) * (2 * s) // (num_h + 1)
            y -= sw // 2
            for dx in range(-s - 2, s + 3):
                for dy in range(sw):
                    cells.add((cx + dx, y + dy))

        return cells

    def _layout_radial(self, cx: int, cy: int, style: dict) -> set:
        """Generate radial streets from center."""
        cells: set = set()
        sw = self.street_width
        s = self.size
        num_rays = 8

        for i in range(num_rays):
            angle = (2 * math.pi * i) / num_rays
            for dist in range(s + 3):
                x = cx + int(round(dist * math.cos(angle)))
                y = cy + int(round(dist * math.sin(angle)))
                for dx in range(-sw // 2, sw // 2 + 1):
                    for dy in range(-sw // 2, sw // 2 + 1):
                        cells.add((x + dx, y + dy))

        # Add concentric ring roads
        for ring in range(1, max(2, s // 12)):
            r = ring * 10
            angle_step = 0.1
            angle = 0.0
            while angle < 2 * math.pi:
                x = cx + int(round(r * math.cos(angle)))
                y = cy + int(round(r * math.sin(angle)))
                for dx in range(-1, 2):
                    for dy in range(-1, 2):
                        cells.add((x + dx, y + dy))
                angle += angle_step

        return cells

    def _layout_random(self, cx: int, cy: int, style: dict,
                       rng: random.Random) -> set:
        """Generate pseudo-random connected roads."""
        cells: set = set()
        sw = self.street_width
        s = self.size

        # Main roads: random lines through center area
        num_roads = rng.randint(3, 6)
        for _ in range(num_roads):
            is_vertical = rng.random() < 0.5
            if is_vertical:
                x = cx + rng.randint(-s, s)
                length = rng.randint(s, s * 2)
                y_start = cy + rng.randint(-s // 2, s // 2)
                for dy in range(length):
                    for dx in range(sw):
                        cells.add((x + dx, y_start + dy))
                        cells.add((x + dx, y_start - dy))
            else:
                y = cy + rng.randint(-s, s)
                length = rng.randint(s, s * 2)
                x_start = cx + rng.randint(-s // 2, s // 2)
                for dx in range(length):
                    for dy in range(sw):
                        cells.add((x_start + dx, y + dy))
                        cells.add((x_start - dx, y + dy))

        return cells

    # ---- Plaza ----

    def _place_plaza(self, cx: int, cy: int, style: dict) -> set:
        """Place a central plaza around (cx, cy)."""
        cells: set = set()
        plaza_radius = 4
        for dx in range(-plaza_radius, plaza_radius + 1):
            for dy in range(-plaza_radius, plaza_radius + 1):
                if dx * dx + dy * dy <= plaza_radius * plaza_radius:
                    cells.add((cx + dx, cy + dy))
        return cells

    # ---- Building placement ----

    def _find_building_spot(
        self, cx: int, cy: int, street_cells: set,
        existing: List[Tuple[int, int, int, int, str]],
        min_w: int, min_h: int, rng: random.Random,
    ) -> Optional[Tuple[int, int, int, int]]:
        """Find a valid position for a building near streets."""
        s = self.size
        for _ in range(50):
            # Try position near a random street cell
            if street_cells:
                sx, sy = rng.choice(list(street_cells))
                bx = sx + rng.randint(-8, 4)
                by = sy + rng.randint(-8, 4)
            else:
                bx = cx + rng.randint(-s, s)
                by = cy + rng.randint(-s, s)

            # Check overlap with existing buildings
            overlap = False
            for ex, ey, ew, eh, _ in existing:
                if (bx < ex + ew + 1 and bx + min_w + 1 > ex and
                        by < ey + eh + 1 and by + min_h + 1 > ey):
                    overlap = True
                    break

            if not overlap:
                return (bx, by, min_w, min_h)

        return None

    def _place_building_rect(
        self, tile_grid: Dict[Tuple[int, int, int], TileData],
        x: int, y: int, w: int, h: int,
        style: dict, btype: str, rng: random.Random,
    ):
        """Place a complete building with walls, floor, door, and interior."""
        z = 0
        wall_id = style["wall"]
        floor_id = style["floor"]
        door_id = style["door_closed"]

        # Walls and floor
        for rx in range(w):
            for ry in range(h):
                xx, yy = x + rx, y + ry
                if rx == 0 or rx == w - 1 or ry == 0 or ry == h - 1:
                    tile = TileData(x=xx, y=yy, z=z, ground_id=wall_id)
                else:
                    tile = TileData(x=xx, y=yy, z=z, ground_id=floor_id)
                tile_grid[(xx, yy, z)] = tile

        # Door on south wall, centered
        door_x = x + w // 2
        door_y = y + h - 1
        tile_grid[(door_x, door_y, z)] = TileData(
            x=door_x, y=door_y, z=z, ground_id=door_id
        )

        # Interior furniture based on building type
        if btype == "house":
            self._furnish_house(tile_grid, x, y, w, h, rng)
        elif btype == "shop":
            self._furnish_shop(tile_grid, x, y, w, h, rng)
        elif btype == "tavern":
            self._furnish_tavern(tile_grid, x, y, w, h, rng)
        elif btype == "temple":
            self._furnish_temple(tile_grid, x, y, w, h, rng)
        elif btype == "depot":
            self._furnish_depot(tile_grid, x, y, w, h, rng)

    def _furnish_house(self, tile_grid, x, y, w, h, rng):
        """Place furniture in a house: bed, table, chair."""
        z = 0
        # Bed in top-left corner
        if w > 4 and h > 4:
            self._add_item(tile_grid, x + 1, y + 1, z, TownTiles.BED)
        # Table
        self._add_item(tile_grid, x + w // 2, y + h // 2, z, TownTiles.TABLE)
        # Chair next to table
        if w > 3:
            self._add_item(tile_grid, x + w // 2 + 1, y + h // 2, z, TownTiles.CHAIR)

    def _furnish_shop(self, tile_grid, x, y, w, h, rng):
        """Place furniture in a shop: counter, crates."""
        z = 0
        # Counter near door
        self._add_item(tile_grid, x + w // 2, y + h - 2, z, TownTiles.COUNTER)
        # Crates
        if w > 5:
            self._add_item(tile_grid, x + 1, y + 1, z, TownTiles.CRATE)
            self._add_item(tile_grid, x + 2, y + 1, z, TownTiles.CRATE)

    def _furnish_tavern(self, tile_grid, x, y, w, h, rng):
        """Place furniture in a tavern: tables, chairs, barrels."""
        z = 0
        # Multiple tables
        self._add_item(tile_grid, x + 2, y + 2, z, TownTiles.TABLE)
        self._add_item(tile_grid, x + 2, y + 2, z, TownTiles.CHAIR)
        if w > 6:
            self._add_item(tile_grid, x + w - 3, y + 2, z, TownTiles.TABLE)
            self._add_item(tile_grid, x + w - 3, y + 2, z, TownTiles.CHAIR)
        # Barrels
        self._add_item(tile_grid, x + 1, y + h - 2, z, TownTiles.BARREL)

    def _furnish_temple(self, tile_grid, x, y, w, h, rng):
        """Place furniture in a temple: altar, rows of chairs."""
        z = 0
        # Altar in center
        altar_x = x + w // 2
        altar_y = y + h // 2
        self._add_item(tile_grid, altar_x, altar_y, z, TownTiles.ALTAR)
        # Chairs in rows
        for row_y in range(y + 2, altar_y - 1, 2):
            for col_x in range(x + 2, x + w - 1):
                self._add_item(tile_grid, col_x, row_y, z, TownTiles.CHAIR)

    def _furnish_depot(self, tile_grid, x, y, w, h, rng):
        """Place furniture in a depot: multiple depot chests."""
        z = 0
        # Depot chests along the back wall
        for dx in range(2, w - 2):
            self._add_item(tile_grid, x + dx, y + 1, z, TownTiles.DEPOT_CHEST)

    def _add_item(self, tile_grid, x, y, z, item_id):
        """Add an item to a tile in the grid."""
        key = (x, y, z)
        if key in tile_grid:
            tile = tile_grid[key]
            tile.items.append(ItemData(id=item_id))
        else:
            tile = TileData(x=x, y=y, z=z, items=[ItemData(id=item_id)])
            tile_grid[key] = tile

    # ---- Fence ----

    def _place_fence_safe(self, tile_grid, cx, cy, style, street_cells):
        """Place fence tiles around the town perimeter."""
        s = self.size + 3
        z = 0
        fence_id = style["fence"]

        # Simple rectangular fence
        for dx in range(-s, s + 1):
            for (fx, fy) in [(cx + dx, cy - s), (cx + dx, cy + s)]:
                key = (fx, fy, z)
                if key not in tile_grid:
                    tile_grid[key] = TileData(x=fx, y=fy, z=z, ground_id=fence_id)
        for dy in range(-s, s + 1):
            for (fx, fy) in [(cx - s, cy + dy), (cx + s, cy + dy)]:
                key = (fx, fy, z)
                if key not in tile_grid:
                    tile_grid[key] = TileData(x=fx, y=fy, z=z, ground_id=fence_id)

    # ---- Helpers ----

    @staticmethod
    def _pick_building_type(rng: random.Random) -> BuildingSpec:
        """Pick a random non-special building type weighted by probability."""
        pool = [b for b in BUILDING_TYPES if not b.is_special]
        total = sum(b.weight for b in pool)
        r = rng.random() * total
        cumulative = 0.0
        for b in pool:
            cumulative += b.weight
            if r <= cumulative:
                return b
        return pool[-1]
