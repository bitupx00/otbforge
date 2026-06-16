"""Dungeon generator using Binary Space Partitioning (BSP) with room types,
corridors, doors, stairs, chests, and spawn points.

Generates a MapData with authentic Tibia tile IDs, suitable for OTBMWriter.
Features:
  - BSP splitting for room placement
  - 5 room types: normal, treasure, boss, spawn, trap
  - L-shaped corridors connecting rooms
  - Door tiles at room-corridor junctions
  - Chests in treasure/boss rooms
  - Spawn data in spawn rooms
  - Configurable parameters (rooms, sizes, floors, corridor width)
"""

import random
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Dict, List, Optional, Set, Tuple

from ai_core.otbm_types import (
    ItemData,
    MapData,
    Position,
    SpawnData,
    TileData,
    TileFlags,
    Tiles,
)


# ---------------------------------------------------------------------------
# Room types
# ---------------------------------------------------------------------------

class RoomType(IntEnum):
    """Types of dungeon rooms."""
    NORMAL   = 0
    TREASURE = 1
    BOSS     = 2
    SPAWN    = 3
    TRAP     = 4


# ---------------------------------------------------------------------------
# Tile ID sets for dungeon
# ---------------------------------------------------------------------------

class DungeonTiles:
    """Tibia tile IDs for dungeon construction."""
    # Floors (stone variations)
    FLOOR_MIN = 410
    FLOOR_MAX = 416

    # Walls
    WALL_MIN  = 1010
    WALL_MAX  = 1017

    # Doors
    CLOSED_DOOR = 5121
    OPEN_DOOR   = 5122

    # Stairs
    STAIRS_DOWN = 433
    STAIRS_UP   = 836

    # Chest
    CHEST = 3756

    # Spawn marker
    TELEPORT = 1387


# ---------------------------------------------------------------------------
# Internal data structures
# ---------------------------------------------------------------------------

@dataclass
class _Room:
    """Internal room representation."""
    x: int
    y: int
    w: int
    h: int
    room_type: RoomType = RoomType.NORMAL

    @property
    def cx(self) -> int:
        return self.x + self.w // 2

    @property
    def cy(self) -> int:
        return self.y + self.h // 2

    @property
    def area(self) -> int:
        return self.w * self.h


@dataclass
class _BSPNode:
    """BSP tree node for spatial partitioning."""
    x: int
    y: int
    w: int
    h: int
    left: Optional["_BSPNode"] = None
    right: Optional["_BSPNode"] = None
    room: Optional[_Room] = None


# ---------------------------------------------------------------------------
# DungeonGenerator
# ---------------------------------------------------------------------------

@dataclass
class DungeonGenerator:
    """Procedural dungeon generator using BSP with room types.

    Parameters
    ----------
    width, height : int
        Dungeon dimensions in tiles per floor.
    rooms_count : int
        Target number of rooms (approximate due to BSP).
    min_room_size, max_room_size : int
        Minimum and maximum room dimensions.
    floors : int
        Number of underground floors (z = 0, -1, -2, …).
    seed : int
        RNG seed for reproducible generation.
    corridor_width : int
        Width of corridors (1 or 2).
    place_chests : bool
        Whether to place chests in treasure/boss rooms.
    place_stairs : bool
        Whether to place stairs between floors.
    room_type_weights : dict
        Weight distribution for room types (must sum to ~1.0).
    default_monsters : list
        Monster names for spawn rooms.
    """

    width: int = 64
    height: int = 64
    rooms_count: int = 12
    min_room_size: int = 5
    max_room_size: int = 12
    floors: int = 1
    seed: int = 42
    corridor_width: int = 1
    place_chests: bool = True
    place_stairs: bool = True
    room_type_weights: Dict[str, float] = field(default_factory=lambda: {
        "normal": 0.50,
        "treasure": 0.15,
        "boss": 0.05,
        "spawn": 0.20,
        "trap": 0.10,
    })
    default_monsters: List[str] = field(default_factory=lambda: [
        "rat", "spider", "orc", "skeleton",
    ])

    def generate(self) -> MapData:
        """Generate the full dungeon and return MapData."""
        rng = random.Random(self.seed)
        all_tiles: List[TileData] = []
        all_spawns: List[SpawnData] = []

        for floor_idx in range(self.floors):
            z = -floor_idx
            floor_tiles, floor_spawns = self._generate_floor(rng, z, floor_idx)
            all_tiles.extend(floor_tiles)
            all_spawns.extend(floor_spawns)

        return MapData(
            width=self.width,
            height=self.height,
            description=f"Dungeon seed={self.seed} floors={self.floors}",
            tiles=all_tiles,
            spawns=all_spawns,
        )

    # ---- Floor generation ----

    def _generate_floor(
        self, rng: random.Random, z: int, floor_idx: int
    ) -> Tuple[List[TileData], List[SpawnData]]:
        """Generate one dungeon floor, returning tiles and spawns."""
        w, h = self.width, self.height

        # BSP split
        root = _BSPNode(0, 0, w, h)
        self._split_bsp(root, self.rooms_count, rng, depth=0)

        # Create rooms in leaves
        rooms: List[_Room] = []
        self._create_rooms(root, rng, rooms)

        # Assign room types
        self._assign_room_types(rooms, rng, floor_idx)

        # Corridors connecting rooms sequentially
        corridor_cells: Set[Tuple[int, int]] = set()
        for i in range(len(rooms) - 1):
            self._carve_corridor(rooms[i], rooms[i + 1], corridor_cells, w, h)

        # Identify door positions (room edge at corridor entry)
        door_cells: Set[Tuple[int, int]] = set()
        for room in rooms:
            for cx, cy in corridor_cells:
                if (room.x <= cx < room.x + room.w and
                        room.y <= cy < room.y + room.h):
                    # Find edge of room facing corridor
                    self._mark_door(room, cx, cy, door_cells, w, h)
                    break

        # Build tile grid (all wall first)
        tile_grid: Dict[Tuple[int, int], TileData] = {}
        for ry in range(h):
            for rx in range(w):
                tile_grid[(rx, ry)] = TileData(
                    x=rx, y=ry, z=z,
                    ground_id=DungeonTiles.WALL_MIN,
                )

        # Place rooms
        for room in rooms:
            floor_id = rng.randint(DungeonTiles.FLOOR_MIN, DungeonTiles.FLOOR_MAX)
            for ry in range(room.y, room.y + room.h):
                for rx in range(room.x, room.x + room.w):
                    tile_grid[(rx, ry)] = TileData(
                        x=rx, y=ry, z=z,
                        ground_id=floor_id,
                    )

            # Room-type-specific content
            self._place_room_content(room, rng, z, floor_idx, tile_grid)

        # Place corridors
        for (cx, cy) in corridor_cells:
            existing = tile_grid.get((cx, cy))
            if existing is None or existing.ground_id < DungeonTiles.FLOOR_MIN or \
               existing.ground_id > DungeonTiles.FLOOR_MAX:
                tile_grid[(cx, cy)] = TileData(
                    x=cx, y=cy, z=z,
                    ground_id=DungeonTiles.FLOOR_MIN,
                )

        # Place doors
        for (dx, dy) in door_cells:
            tile_grid[(dx, dy)] = TileData(
                x=dx, y=dy, z=z,
                ground_id=DungeonTiles.OPEN_DOOR,
            )

        # Collect spawns from spawn rooms
        spawns: List[SpawnData] = []
        for room in rooms:
            if room.room_type == RoomType.SPAWN:
                monsters = [
                    (name, 0, 0)
                    for name in rng.sample(
                        self.default_monsters,
                        k=min(len(self.default_monsters),
                              rng.randint(1, 3))
                    )
                ]
                spawns.append(SpawnData(
                    x=room.cx, y=room.cy, z=z,
                    radius=max(room.w, room.h),
                    monsters=monsters,
                ))

        return list(tile_grid.values()), spawns

    # ---- Room content ----

    def _place_room_content(
        self,
        room: _Room,
        rng: random.Random,
        z: int,
        floor_idx: int,
        tile_grid: Dict[Tuple[int, int], TileData],
    ):
        """Place items in rooms based on room type."""
        cx, cy = room.cx, room.cy

        if room.room_type == RoomType.TREASURE and self.place_chests:
            # Place chest at center
            items = [ItemData(id=DungeonTiles.CHEST)]
            tile_grid[(cx, cy)] = TileData(
                x=cx, y=cy, z=z,
                ground_id=DungeonTiles.FLOOR_MIN,
                items=items,
            )
            # Additional chests in corners
            for ox, oy in [(1, 1), (-1, 1), (1, -1), (-1, -1)]:
                px, py = cx + ox, cy + oy
                if (room.x < px < room.x + room.w - 1 and
                        room.y < py < room.y + room.h - 1):
                    if rng.random() < 0.4:
                        tile_grid[(px, py)] = TileData(
                            x=px, y=py, z=z,
                            ground_id=DungeonTiles.FLOOR_MIN,
                            items=[ItemData(id=DungeonTiles.CHEST)],
                        )

        elif room.room_type == RoomType.BOSS:
            # Big room with chest and stairs marker
            if self.place_chests:
                items = [ItemData(id=DungeonTiles.CHEST)]
                tile_grid[(cx, cy)] = TileData(
                    x=cx, y=cy, z=z,
                    ground_id=DungeonTiles.FLOOR_MAX,
                    items=items,
                )
            if self.place_stairs and floor_idx < self.floors - 1:
                items2 = [ItemData(id=DungeonTiles.STAIRS_DOWN)]
                sx = cx + 1 if cx + 1 < room.x + room.w else cx - 1
                tile_grid[(sx, cy)] = TileData(
                    x=sx, y=cy, z=z,
                    ground_id=DungeonTiles.FLOOR_MAX,
                    items=items2,
                )

        elif room.room_type == RoomType.TRAP:
            # Place teleport as "trap" marker
            if rng.random() < 0.5:
                items = [ItemData(
                    id=DungeonTiles.TELEPORT,
                    action_id=1,
                    teleport_dest=Position(x=cx, y=cy, z=z),
                )]
                tile_grid[(cx, cy)] = TileData(
                    x=cx, y=cy, z=z,
                    ground_id=DungeonTiles.FLOOR_MIN,
                    items=items,
                )

        elif room.room_type == RoomType.NORMAL and self.place_chests:
            # Small chance of a chest
            if rng.random() < 0.15:
                tile_grid[(cx, cy)] = TileData(
                    x=cx, y=cy, z=z,
                    ground_id=DungeonTiles.FLOOR_MIN,
                    items=[ItemData(id=DungeonTiles.CHEST)],
                )

        elif room.room_type == RoomType.SPAWN:
            # Stairs in spawn rooms (entry point) if first floor
            if floor_idx == 0 and self.place_stairs:
                items = [ItemData(id=DungeonTiles.STAIRS_UP)]
                tile_grid[(cx, cy)] = TileData(
                    x=cx, y=cy, z=z,
                    ground_id=DungeonTiles.FLOOR_MIN,
                    items=items,
                )

    # ---- Door marking ----

    def _mark_door(
        self,
        room: _Room,
        cx: int,
        cy: int,
        door_cells: Set[Tuple[int, int]],
        w: int,
        h: int,
    ):
        """Mark door position at room edge nearest to corridor entry."""
        # Check which edge the corridor entry is near
        if cx == room.x or cx == room.x + room.w - 1:
            # Horizontal edge
            dx = -1 if cx == room.x else 1
            door_x = cx + dx
            if 0 <= door_x < w:
                door_cells.add((door_x, cy))
        elif cy == room.y or cy == room.y + room.h - 1:
            # Vertical edge
            dy = -1 if cy == room.y else 1
            door_y = cy + dy
            if 0 <= door_y < h:
                door_cells.add((cx, door_y))
        else:
            # Interior corridor entry — place door just outside
            for dx2, dy2 in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                nx, ny = cx + dx2, cy + dy2
                if nx < room.x or nx >= room.x + room.w or \
                   ny < room.y or ny >= room.y + room.h:
                    if 0 <= nx < w and 0 <= ny < h:
                        door_cells.add((nx, ny))
                        break

    # ---- Room type assignment ----

    def _assign_room_types(
        self,
        rooms: List[_Room],
        rng: random.Random,
        floor_idx: int,
    ):
        """Assign types to rooms based on weights."""
        if not rooms:
            return

        # Always make first room on floor 0 a spawn room
        if floor_idx == 0 and len(rooms) > 0:
            rooms[0].room_type = RoomType.SPAWN

        # Always make last room a boss room
        if len(rooms) > 1:
            rooms[-1].room_type = RoomType.BOSS

        # Assign types to remaining rooms
        type_map = {
            "normal": RoomType.NORMAL,
            "treasure": RoomType.TREASURE,
            "boss": RoomType.BOSS,
            "spawn": RoomType.SPAWN,
            "trap": RoomType.TRAP,
        }

        weights = list(self.room_type_weights.values())
        type_names = list(self.room_type_weights.keys())

        for i, room in enumerate(rooms):
            if room.room_type != RoomType.NORMAL:
                continue  # Already assigned (first/last)
            r = rng.random()
            cumulative = 0.0
            chosen = type_names[0]
            for name, weight in zip(type_names, weights):
                cumulative += weight
                if r <= cumulative:
                    chosen = name
                    break
            room.room_type = type_map[chosen]

    # ---- BSP splitting ----

    def _split_bsp(
        self,
        node: _BSPNode,
        max_splits: int,
        rng: random.Random,
        depth: int,
    ):
        """Recursively split BSP node to create room partitions."""
        if depth > 6 or node.w < self.min_room_size * 2 + 2 or \
           node.h < self.min_room_size * 2 + 2:
            return

        horizontal = rng.random() < 0.5
        if node.w < node.h * 0.8:
            horizontal = True
        elif node.h < node.w * 0.8:
            horizontal = False

        if horizontal:
            split = rng.randint(node.y + self.min_room_size,
                                node.y + node.h - self.min_room_size - 1)
            node.left = _BSPNode(node.x, node.y, node.w, split - node.y)
            node.right = _BSPNode(node.x, split, node.w,
                                   node.y + node.h - split)
        else:
            split = rng.randint(node.x + self.min_room_size,
                                node.x + node.w - self.min_room_size - 1)
            node.left = _BSPNode(node.x, node.y, split - node.x, node.h)
            node.right = _BSPNode(split, node.y,
                                   node.x + node.w - split, node.h)

        self._split_bsp(node.left, max_splits, rng, depth + 1)
        self._split_bsp(node.right, max_splits, rng, depth + 1)

    def _create_rooms(
        self,
        node: _BSPNode,
        rng: random.Random,
        rooms: List[_Room],
    ):
        """Create rooms in BSP leaf nodes."""
        if node.left is None and node.right is None:
            max_rw = min(self.max_room_size, node.w - 2)
            max_rh = min(self.max_room_size, node.h - 2)
            if max_rw < self.min_room_size or max_rh < self.min_room_size:
                return
            rw = rng.randint(self.min_room_size, max_rw)
            rh = rng.randint(self.min_room_size, max_rh)
            rx = rng.randint(node.x + 1, max(node.x + 1, node.x + node.w - rw - 1))
            ry = rng.randint(node.y + 1, max(node.y + 1, node.y + node.h - rh - 1))
            node.room = _Room(rx, ry, rw, rh)
            rooms.append(node.room)
            return

        if node.left:
            self._create_rooms(node.left, rng, rooms)
        if node.right:
            self._create_rooms(node.right, rng, rooms)

    # ---- L-shaped corridor ----

    def _carve_corridor(
        self,
        a: _Room,
        b: _Room,
        corridors: Set[Tuple[int, int]],
        w: int,
        h: int,
    ):
        """Carve an L-shaped corridor between two rooms."""
        ax, ay = a.cx, a.cy
        bx, by = b.cx, b.cy

        # Corridor width
        hw = self.corridor_width // 2

        # Go horizontal first, then vertical
        cx, cy = ax, ay
        while cx != bx:
            for dw in range(-hw, hw + 1):
                if 0 <= cx < w and 0 <= cy + dw < h:
                    corridors.add((cx, cy + dw))
            cx += 1 if bx > ax else -1
        while cy != by:
            for dw in range(-hw, hw + 1):
                if 0 <= cx + dw < w and 0 <= cy < h:
                    corridors.add((cx + dw, cy))
            cy += 1 if by > ay else -1
        # Endpoint
        for dw in range(-hw, hw + 1):
            if 0 <= cx < w and 0 <= cy + dw < h:
                corridors.add((cx, cy + dw))

    # ---- Public helpers for testing / inspection ----

    def get_room_list(self) -> List[_Room]:
        """Generate and return the room list (without full tile generation)."""
        rng = random.Random(self.seed)
        root = _BSPNode(0, 0, self.width, self.height)
        self._split_bsp(root, self.rooms_count, rng, depth=0)
        rooms: List[_Room] = []
        self._create_rooms(root, rng, rooms)
        self._assign_room_types(rooms, rng, 0)
        return rooms
