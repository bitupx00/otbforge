"""Road/Path generator using A* pathfinding with bridge support.

Connects points A → B with natural-looking roads that avoid water and
mountains, placing bridge tiles over water crossings. Supports configurable
width (1-3 tiles) and multi-path networks connecting N waypoints.

Features:
  - A* pathfinding avoiding water/mountains/lava
  - Bridge placement over water crossings
  - Configurable road width (1-3 tiles)
  - Multiple path networks (MST-based minimum network)
  - Natural road tiles (cobblestone, stone path, paved road)
  - Path smoothing to reduce jagged edges
"""

import heapq
import math
import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from ai_core.otbm_types import (
    ItemData,
    MapData,
    TileData,
    Tiles,
)


# ---------------------------------------------------------------------------
# Road tile IDs
# ---------------------------------------------------------------------------

class RoadTiles:
    """Tile IDs for road/path generation."""
    COBBLESTONE = 355
    STONE_PATH = 356
    PAVED_ROAD = 357
    BRIDGE_H = 5408   # horizontal bridge
    BRIDGE_V = 5409   # vertical bridge


# ---------------------------------------------------------------------------
# RoadGenerator
# ---------------------------------------------------------------------------

@dataclass
class RoadGenerator:
    """Road/path generator with A* pathfinding and bridge support.

    Parameters
    ----------
    map_data : MapData
        Base map to build roads on. Must have tiles populated.
    seed : int
        RNG seed for reproducibility.
    road_tile : int
        Ground tile ID for roads.
    bridge_tile_h : int
        Horizontal bridge tile ID.
    bridge_tile_v : int
        Vertical bridge tile ID.
    width : int
        Road width in tiles (1-3).
    avoid_water : bool
        Whether A* avoids water (uses bridges instead).
    avoid_mountains : bool
        Whether A* avoids mountain tiles.
    smooth_path : bool
        Whether to smooth the path to reduce zigzag.
    """
    map_data: MapData = field(default_factory=lambda: MapData(width=256, height=256))
    seed: int = 42
    road_tile: int = RoadTiles.COBBLESTONE
    bridge_tile_h: int = RoadTiles.BRIDGE_H
    bridge_tile_v: int = RoadTiles.BRIDGE_V
    width: int = 1
    avoid_water: bool = True
    avoid_mountains: bool = True
    smooth_path: bool = True

    # Tiles considered impassable by A*
    IMPASSABLE_TILES: Set[int] = field(default_factory=lambda: {Tiles.WATER, Tiles.LAVA, Tiles.STONE_WALL})
    MOUNTAIN_TILES: Set[int] = field(default_factory=lambda: {919})

    def generate_path(self, start: Tuple[int, int], end: Tuple[int, int]) -> List[Tuple[int, int]]:
        """Find a path from start to end using A* and return list of (x, y).

        The path avoids impassable tiles (water, lava, walls) by default,
        placing bridge tiles when water must be crossed.
        """
        ground_map = self._build_ground_map()
        sx, sy = start
        ex, ey = end

        path = self._astar(sx, sy, ex, ey, ground_map)
        if path is None:
            return []

        if self.smooth_path:
            path = self._smooth(path)

        return path

    def apply_path(self, path: List[Tuple[int, int]]) -> MapData:
        """Apply a road path to the map_data, placing road tiles and bridges.

        Returns the modified MapData.
        """
        if not path:
            return self.map_data

        ground_map = self._build_ground_map()
        z = 0
        road_cells: Dict[Tuple[int, int], str] = {}  # (x,y) -> "bridge" or "road"

        for (px, py) in path:
            gid = ground_map.get((px, py), Tiles.GRASS)
            if gid == Tiles.WATER:
                road_cells[(px, py)] = "bridge"
            else:
                road_cells[(px, py)] = "road"

        # Expand width
        expanded: Dict[Tuple[int, int], str] = dict(road_cells)
        for (px, py) in road_cells:
            if self.width >= 2:
                idx = next((i for i, (x, y) in enumerate(path) if x == px and y == py), 0)
                if idx < len(path) - 1:
                    dx = path[idx + 1][0] - path[idx][0]
                    dy = path[idx + 1][1] - path[idx][1]
                    kind = road_cells[(px, py)]
                    if dx != 0:
                        if (px, py + 1) not in expanded:
                            expanded[(px, py + 1)] = kind
                    elif dy != 0:
                        if (px + 1, py) not in expanded:
                            expanded[(px + 1, py)] = kind

        # Apply tiles to map
        tile_grid: Dict[Tuple[int, int, int], TileData] = {}
        for t in self.map_data.tiles:
            tile_grid[(t.x, t.y, t.z)] = t

        for (px, py), kind in expanded.items():
            if kind == "bridge":
                gid_n = ground_map.get((px, py - 1), 0)
                gid_s = ground_map.get((px, py + 1), 0)
                gid_w = ground_map.get((px - 1, py), 0)
                gid_e = ground_map.get((px + 1, py), 0)
                h_water = (gid_n == Tiles.WATER or gid_s == Tiles.WATER)
                v_water = (gid_w == Tiles.WATER or gid_e == Tiles.WATER)
                if v_water and not h_water:
                    tile_id = self.bridge_tile_v
                else:
                    tile_id = self.bridge_tile_h
                tile = TileData(x=px, y=py, z=z, ground_id=tile_id)
            else:
                tile = TileData(x=px, y=py, z=z, ground_id=self.road_tile)
            tile_grid[(px, py, z)] = tile

        return MapData(
            width=self.map_data.width,
            height=self.map_data.height,
            description=self.map_data.description,
            tiles=list(tile_grid.values()),
            towns=list(self.map_data.towns),
            waypoints=list(self.map_data.waypoints),
            spawns=list(self.map_data.spawns),
            npc_spawns=list(self.map_data.npc_spawns),
        )

    def generate_network(self, waypoints: List[Tuple[int, int]]) -> List[List[Tuple[int, int]]]:
        """Generate a minimum road network connecting all waypoints.

        Uses minimum spanning tree to determine which pairs to connect,
        then runs A* for each pair. Returns list of paths.
        """
        if len(waypoints) <= 1:
            return []

        # Build MST using Prim's algorithm
        connected: Set[int] = {0}
        edges: List[Tuple[int, int]] = []

        while len(connected) < len(waypoints):
            best_dist = float("inf")
            best_edge: Optional[Tuple[int, int]] = None
            for c in connected:
                for j in range(len(waypoints)):
                    if j not in connected:
                        d = math.hypot(
                            waypoints[c][0] - waypoints[j][0],
                            waypoints[c][1] - waypoints[j][1],
                        )
                        if d < best_dist:
                            best_dist = d
                            best_edge = (c, j)
            if best_edge is None:
                break
            edges.append(best_edge)
            connected.add(best_edge[1])

        paths: List[List[Tuple[int, int]]] = []
        for (i, j) in edges:
            path = self.generate_path(waypoints[i], waypoints[j])
            paths.append(path)

        return paths

    # ---- Internal methods ----

    def _build_ground_map(self) -> Dict[Tuple[int, int], int]:
        """Build a dict of (x, y) -> ground_id from map tiles."""
        ground_map: Dict[Tuple[int, int], int] = {}
        for tile in self.map_data.tiles:
            ground_map[(tile.x, tile.y)] = tile.ground_id
        return ground_map

    def _astar(
        self,
        sx: int, sy: int,
        ex: int, ey: int,
        ground_map: Dict[Tuple[int, int], int],
    ) -> Optional[List[Tuple[int, int]]]:
        """A* pathfinding from (sx, sy) to (ex, ey)."""
        w = self.map_data.width
        h = self.map_data.height

        def is_passable(x: int, y: int) -> bool:
            if x < 0 or x >= w or y < 0 or y >= h:
                return False
            gid = ground_map.get((x, y), Tiles.GRASS)
            if gid in self.IMPASSABLE_TILES:
                return self.avoid_water is False
            if gid in self.MOUNTAIN_TILES and self.avoid_mountains:
                return False
            return True

        def heuristic(x: int, y: int) -> float:
            return math.hypot(x - ex, y - ey)

        open_set: List[Tuple[float, float, int, int]] = [(heuristic(sx, sy), 0.0, sx, sy)]
        came_from: Dict[Tuple[int, int], Tuple[int, int]] = {}
        g_score: Dict[Tuple[int, int], float] = {(sx, sy): 0.0}
        visited: Set[Tuple[int, int]] = set()
        counter = 0.0

        DIRS = [(-1, 0), (1, 0), (0, -1), (0, 1),
                (-1, -1), (1, -1), (-1, 1), (1, 1)]

        while open_set:
            _f, _g, cx, cy = heapq.heappop(open_set)

            if (cx, cy) == (ex, ey):
                path = [(ex, ey)]
                cur = (cx, cy)
                while cur in came_from:
                    cur = came_from[cur]
                    path.append(cur)
                path.reverse()
                return path

            if (cx, cy) in visited:
                continue
            visited.add((cx, cy))

            for dx, dy in DIRS:
                nx, ny = cx + dx, cy + dy
                if (nx, ny) in visited:
                    continue
                if not is_passable(nx, ny):
                    continue

                cost = math.hypot(dx, dy)
                gid = ground_map.get((nx, ny), Tiles.GRASS)
                if gid == Tiles.WATER:
                    cost += 3.0

                new_g = g_score[(cx, cy)] + cost
                if new_g < g_score.get((nx, ny), float("inf")):
                    g_score[(nx, ny)] = new_g
                    came_from[(nx, ny)] = (cx, cy)
                    f = new_g + heuristic(nx, ny)
                    counter += 1.0
                    heapq.heappush(open_set, (f, counter, nx, ny))

        return None  # No path found

    def _smooth(self, path: List[Tuple[int, int]]) -> List[Tuple[int, int]]:
        """Smooth path by removing unnecessary detours using line-of-sight."""
        if len(path) <= 2:
            return path

        smoothed = [path[0]]
        current = 0

        while current < len(path) - 1:
            farthest = current + 1
            for look in range(len(path) - 1, current + 1, -1):
                if self._line_of_sight(path[current], path[look]):
                    farthest = look
                    break
            smoothed.append(path[farthest])
            current = farthest

        return smoothed

    def _line_of_sight(self, a: Tuple[int, int], b: Tuple[int, int]) -> bool:
        """Check if there's a clear line of sight between two points using Bresenham."""
        ground_map = self._build_ground_map()
        x0, y0 = a
        x1, y1 = b

        dx = abs(x1 - x0)
        dy = abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx - dy

        while True:
            if (x0, y0) != a and (x0, y0) != b:
                gid = ground_map.get((x0, y0), Tiles.GRASS)
                if gid in self.IMPASSABLE_TILES and self.avoid_water:
                    return False
                if gid in self.MOUNTAIN_TILES and self.avoid_mountains:
                    return False

            if x0 == x1 and y0 == y1:
                break

            e2 = 2 * err
            if e2 > -dy:
                err -= dy
                x0 += sx
            if e2 < dx:
                err += dx
                y0 += sy

        return True
