"""Dungeon generator using Binary Space Partitioning (BSP)."""

import random
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from ai_core.otbm_types import (
    ItemData,
    MapData,
    Position,
    TileData,
    TileFlags,
    Tiles,
)


@dataclass
class _Room:
    x: int
    y: int
    w: int
    h: int

    @property
    def cx(self) -> int:
        return self.x + self.w // 2

    @property
    def cy(self) -> int:
        return self.y + self.h // 2


@dataclass
class _BSPNode:
    x: int
    y: int
    w: int
    h: int
    left: Optional["_BSPNode"] = None
    right: Optional["_BSPNode"] = None
    room: Optional[_Room] = None


@dataclass
class DungeonGenerator:
    width: int = 64
    height: int = 64
    rooms_count: int = 12
    min_room_size: int = 5
    max_room_size: int = 12
    floors: int = 1          # z-levels (negative: 0..-floors+1)
    seed: int = 42
    place_chests: bool = True
    place_stairs: bool = True

    def generate(self) -> MapData:
        rng = random.Random(self.seed)
        all_tiles: List[TileData] = []

        for floor_idx in range(self.floors):
            z = -floor_idx
            floor_tiles = self._generate_floor(rng, z, floor_idx)
            all_tiles.extend(floor_tiles)

        return MapData(
            width=self.width,
            height=self.height,
            description=f"Dungeon seed={self.seed} floors={self.floors}",
            tiles=all_tiles,
        )

    # ---- Floor generation ----

    def _generate_floor(self, rng: random.Random, z: int,
                        floor_idx: int) -> List[TileData]:
        w, h = self.width, self.height

        # BSP split
        root = _BSPNode(0, 0, w, h)
        self._split_bsp(root, self.rooms_count, rng, depth=0)

        # Create rooms in leaves
        rooms: List[_Room] = []
        self._create_rooms(root, rng, rooms)

        # Corridors connecting rooms sequentially
        corridors: set = set()
        for i in range(len(rooms) - 1):
            self._carve_corridor(rooms[i], rooms[i + 1], corridors, w, h)

        # Build tile grid (all rock first)
        tile_grid: dict = {}
        for ry in range(h):
            for rx in range(w):
                tile_grid[(rx, ry)] = TileData(
                    x=rx, y=ry, z=z,
                    ground_id=Tiles.STONE_WALL,
                )

        # Place rooms
        for room_idx, room in enumerate(rooms):
            for ry in range(room.y, room.y + room.h):
                for rx in range(room.x, room.x + room.w):
                    tile_grid[(rx, ry)] = TileData(
                        x=rx, y=ry, z=z,
                        ground_id=Tiles.STONE,
                    )

            # Walls: set tiles around room that aren't inside another room to wall
            # (rooms already override; surrounding stays wall from init)

            # Items in rooms
            if self.place_chests and (room_idx == 0 or rng.random() < 0.7):
                cx, cy = room.cx, room.cy
                items = [ItemData(id=Tiles.CHEST)]
                tile_grid[(cx, cy)] = TileData(
                    x=cx, y=cy, z=z,
                    ground_id=Tiles.STONE,
                    items=items,
                )

            # Stairs down (except last floor)
            if self.place_stairs and floor_idx < self.floors - 1 and rng.random() < 0.4:
                sx, sy = room.cx + 1, room.cy
                items = [ItemData(id=Tiles.STONE_STAIRS)]
                tile_grid[(sx, sy)] = TileData(
                    x=sx, y=sy, z=z,
                    ground_id=Tiles.STONE,
                    items=items,
                )

        # Place corridors (preserve items from rooms)
        for (cx, cy) in corridors:
            existing = tile_grid.get((cx, cy))
            if existing is None or existing.ground_id != Tiles.STONE:
                tile_grid[(cx, cy)] = TileData(
                    x=cx, y=cy, z=z,
                    ground_id=Tiles.STONE,
                )

        return list(tile_grid.values())

    # ---- BSP splitting ----

    def _split_bsp(self, node: _BSPNode, max_splits: int,
                   rng: random.Random, depth: int):
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

    def _create_rooms(self, node: _BSPNode, rng: random.Random,
                      rooms: List[_Room]):
        if node.left is None and node.right is None:
            max_rw = min(self.max_room_size, node.w - 2)
            max_rh = min(self.max_room_size, node.h - 2)
            if max_rw < self.min_room_size or max_rh < self.min_room_size:
                return  # partition too small for a room
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

    def _carve_corridor(self, a: _Room, b: _Room,
                        corridors: set, w: int, h: int):
        ax, ay = a.cx, a.cy
        bx, by = b.cx, b.cy
        # L-shape: go horizontal first then vertical (or vice-versa randomly)
        cx, cy = ax, ay
        while cx != bx:
            if 0 <= cx < w and 0 <= cy < h:
                corridors.add((cx, cy))
            cx += 1 if bx > ax else -1
        while cy != by:
            if 0 <= cx < w and 0 <= cy < h:
                corridors.add((cx, cy))
            cy += 1 if by > ay else -1
        if 0 <= cx < w and 0 <= cy < h:
            corridors.add((cx, cy))
