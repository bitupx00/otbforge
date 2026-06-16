"""City generator with grid-based layout, streets, buildings, parks."""

import random
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

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


@dataclass
class CityGenerator:
    width: int = 64
    height: int = 64
    buildings_count: int = 20
    street_width: int = 3
    seed: int = 42
    has_walls: bool = False
    has_park: bool = True

    def generate(self) -> MapData:
        rng = random.Random(self.seed)
        w, h = self.width, self.height

        tile_grid: dict = {}
        # Default: grass
        for ry in range(h):
            for rx in range(w):
                tile_grid[(rx, ry)] = TileData(
                    x=rx, y=ry, z=0,
                    ground_id=Tiles.GRASS,
                )

        # --- Street grid ---
        sw = self.street_width
        # Vertical streets
        v_streets = self._pick_streets(4, sw, w, rng)
        h_streets = self._pick_streets(4, sw, h, rng)

        for sx in v_streets:
            for dy in range(h):
                for dx in range(sw):
                    if 0 <= sx + dx < w:
                        tile_grid[(sx + dx, dy)] = TileData(
                            x=sx + dx, y=dy, z=0,
                            ground_id=Tiles.STONE,
                        )

        for sy in h_streets:
            for dx in range(w):
                for dy in range(sw):
                    if 0 <= sy + dy < h:
                        tile_grid[(dx, sy + dy)] = TileData(
                            x=dx, y=sy + dy, z=0,
                            ground_id=Tiles.STONE,
                        )

        # --- Buildings in blocks ---
        blocks = self._get_blocks(v_streets, h_streets, sw, w, h)
        npc_spawns: List[NPCSpawnData] = []
        placed = 0

        for bx, by, bw, bh in blocks:
            if placed >= self.buildings_count:
                break
            # Skip some blocks for parks
            if self.has_park and rng.random() < 0.15:
                self._place_park(tile_grid, bx + 1, by + 1,
                                 bw - 2, bh - 2, rng)
                continue

            # Place building
            placed += 1
            self._place_building(tile_grid, bx + 1, by + 1,
                                 bw - 2, bh - 2, rng, npc_spawns)

        # --- Plaza central (intersection of 2nd v-street and 2nd h-street) ---
        if len(v_streets) >= 2 and len(h_streets) >= 2:
            px = v_streets[1]
            py = h_streets[1]
            for dy in range(sw + 4):
                for dx in range(sw + 4):
                    xx, yy = px + dx - 2, py + dy - 2
                    if 0 <= xx < w and 0 <= yy < h:
                        tile_grid[(xx, yy)] = TileData(
                            x=xx, y=yy, z=0,
                            ground_id=Tiles.STONE,
                            flags=TileFlags.PROTECTIONZONE,
                        )

        # --- Perimeter walls ---
        if self.has_walls:
            for rx in range(w):
                for wy in (0, h - 1):
                    tile_grid[(rx, wy)] = TileData(
                        x=rx, y=wy, z=0,
                        ground_id=Tiles.STONE_WALL,
                    )
            for ry in range(h):
                for wx in (0, w - 1):
                    tile_grid[(wx, ry)] = TileData(
                        x=wx, y=ry, z=0,
                        ground_id=Tiles.STONE_WALL,
                    )

        # Town data
        town = TownData(
            id=1,
            name="Generated City",
            temple=Position(x=w // 2, y=h // 2, z=0),
        )

        return MapData(
            width=w,
            height=h,
            description=f"City seed={self.seed}",
            tiles=list(tile_grid.values()),
            towns=[town],
            npc_spawns=npc_spawns,
        )

    # ---- helpers ----

    def _pick_streets(self, count: int, sw: int, total: int,
                      rng: random.Random) -> List[int]:
        """Pick evenly-spaced street start positions."""
        margin = sw + 2
        if total - margin * 2 < count * (sw + 6):
            # fallback
            positions = list(range(margin, total - margin, sw + 8))
            return positions[:count]

        block_size = (total - 2 * margin) // count
        positions = []
        for i in range(count):
            base = margin + i * block_size + block_size // 2 - sw // 2
            base = max(0, min(base, total - sw))
            positions.append(base)
        return positions

    def _get_blocks(self, v_streets: List[int], h_streets: List[int],
                    sw: int, w: int, h: int) -> List[Tuple[int, int, int, int]]:
        blocks: List[Tuple[int, int, int, int]] = []
        # Horizontal strips between streets
        h_edges = [0] + [s + sw for s in h_streets] + [h]
        v_edges = [0] + [s + sw for s in v_streets] + [w]
        for hi in range(len(h_edges) - 1):
            for vi in range(len(v_edges) - 1):
                bx = v_edges[vi]
                by = h_edges[hi]
                bw = v_edges[vi + 1] - bx
                bh = h_edges[hi + 1] - by
                if bw > sw + 4 and bh > sw + 4:
                    blocks.append((bx, by, bw, bh))
        return blocks

    def _place_building(self, tile_grid: dict, x: int, y: int,
                        w: int, h: int, rng: random.Random,
                        npc_spawns: List[NPCSpawnData]):
        if w < 4 or h < 4:
            return
        map_w = self.width
        map_h = self.height

        # Walls around perimeter
        for rx in range(w):
            for ry in range(h):
                xx, yy = x + rx, y + ry
                if rx == 0 or rx == w - 1 or ry == 0 or ry == h - 1:
                    tile_grid[(xx, yy)] = TileData(
                        x=xx, y=yy, z=0,
                        ground_id=Tiles.STONE_WALL,
                    )
                else:
                    # Interior floor
                    tile_grid[(xx, yy)] = TileData(
                        x=xx, y=yy, z=0,
                        ground_id=Tiles.FLOOR_WOOD,
                    )

        # Door on south wall (center)
        door_x = x + w // 2
        door_y = y + h - 1
        if 0 <= door_x < map_w and 0 <= door_y < map_h:
            tile_grid[(door_x, door_y)] = TileData(
                x=door_x, y=door_y, z=0,
                ground_id=Tiles.CLOSED_DOOR,
            )

        # Maybe place NPC inside
        if rng.random() < 0.2:
            npc_names = ["Merchant", "Banker", "Healer", "Guild Leader"]
            npc_name = rng.choice(npc_names)
            nx = x + w // 2
            ny = y + h // 2
            npc_spawns.append(NPCSpawnData(
                x=nx, y=ny, z=0,
                npc_name=npc_name,
            ))

    def _place_park(self, tile_grid: dict, x: int, y: int,
                    w: int, h: int, rng: random.Random):
        for rx in range(max(0, w)):
            for ry in range(max(0, h)):
                xx, yy = x + rx, y + ry
                items: List[ItemData] = []
                r = rng.random()
                if r < 0.15:
                    tid = rng.randint(Tiles.TREE_MIN, Tiles.TREE_MAX)
                    items.append(ItemData(id=tid))
                elif r < 0.20:
                    fid = rng.randint(Tiles.FLOWER_MIN, Tiles.FLOWER_MAX)
                    items.append(ItemData(id=fid))
                elif r < 0.22:
                    items.append(ItemData(id=Tiles.BUSH_1))

                tile_grid[(xx, yy)] = TileData(
                    x=xx, y=yy, z=0,
                    ground_id=Tiles.GRASS,
                    items=items,
                )
