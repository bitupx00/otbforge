"""Spawn generator for monsters and NPCs."""

import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from ai_core.otbm_types import (
    MapData,
    NPCSpawnData,
    SpawnData,
    TileData,
    Tiles,
)


# Built-in monster database with biome hints
MONSTER_DB: Dict[str, str] = {
    # Overworld
    "rat": "dirt",
    "spider": "forest",
    "snake": "dirt",
    "wolf": "forest",
    "deer": "grass",
    "bear": "forest",
    "orc": "dirt",
    "orc warrior": "dirt",
    "orc shaman": "dirt",
    "goblin": "dirt",
    "troll": "dirt",
    "minotaur": "dungeon",
    # Underground / dungeon
    "skeleton": "dungeon",
    "demon": "dungeon",
    "dragon": "dungeon",
    "vampire": "dungeon",
    "cyclops": "dungeon",
    "ghoul": "dungeon",
    "ghost": "dungeon",
    "crypt shambler": "dungeon",
    # Aquatic
    "crab": "water",
    "fish": "water",
}

# NPC types
NPC_TYPES: List[str] = [
    "Merchant",
    "Banker",
    "Healer",
    "Guild Leader",
    "Alchemist",
    "Blacksmith",
    "Mage Trainer",
    "Paladin Trainer",
    "Knight Trainer",
]


@dataclass
class SpawnGenerator:
    """Place monster spawns and NPCs on a map.

    If *base_map* is provided, spawns are added on top of it and a new
    MapData is returned. Otherwise a fresh (empty) MapData is created.
    """
    width: int = 64
    height: int = 64
    seed: int = 42
    monster_types: List[str] = field(default_factory=lambda: [
        "rat", "spider", "orc", "skeleton", "dragon", "demon",
        "vampire", "wolf", "bear", "goblin",
    ])
    npc_types: List[str] = field(default_factory=lambda: [
        "Merchant", "Banker", "Healer",
    ])
    density: float = 0.005  # spawns per walkable tile
    spawn_radius: int = 6
    base_map: Optional[MapData] = None

    def generate(self) -> MapData:
        rng = random.Random(self.seed)
        w, h = self.width, self.height

        # Build walkable set from base_map tiles if available
        walkable: set = set()
        ground_map: dict = {}  # (x,y,z) -> ground_id
        if self.base_map:
            for t in self.base_map.tiles:
                key = (t.x, t.y, t.z)
                if t.ground_id > 0 and t.ground_id != Tiles.WATER:
                    walkable.add(key)
                    ground_map[key] = t.ground_id
                elif t.ground_id == Tiles.WATER:
                    ground_map[key] = Tiles.WATER
        else:
            for ry in range(h):
                for rx in range(w):
                    walkable.add((rx, ry, 0))

        # Build resulting tile list
        tiles: List[TileData]
        if self.base_map:
            tiles = list(self.base_map.tiles)
        else:
            tiles = [TileData(x=x, y=y, z=0, ground_id=Tiles.GRASS)
                     for y in range(h) for x in range(w)]

        # Collect existing NPC spawns from base_map
        npc_spawns: List[NPCSpawnData] = []
        if self.base_map:
            npc_spawns = list(self.base_map.npc_spawns)

        spawns: List[SpawnData] = []
        used: set = set()

        # Filter valid monsters
        valid_monsters = [m for m in self.monster_types if m in MONSTER_DB]
        if not valid_monsters:
            return MapData(
                width=self.base_map.width if self.base_map else w,
                height=self.base_map.height if self.base_map else h,
                description=self.base_map.description if self.base_map else "Spawns",
                tiles=tiles,
                spawns=[],
                npc_spawns=npc_spawns,
            )

        # Walk through walkable tiles and place spawns based on density
        walkable_list = sorted(walkable)
        target_count = max(1, int(len(walkable_list) * self.density))

        for _ in range(target_count):
            # Pick a random walkable position
            idx = rng.randint(0, len(walkable_list) - 1)
            px, py, pz = walkable_list[idx]

            # Avoid overlapping spawn centres
            if any(abs(px - ux) < self.spawn_radius and
                   abs(py - uy) < self.spawn_radius
                   for (ux, uy, _) in used):
                continue

            # Determine biome from ground
            gid = ground_map.get((px, py, pz), Tiles.GRASS)
            biome = self._ground_to_biome(gid)

            # Select matching monsters
            matching = [m for m in valid_monsters
                        if MONSTER_DB.get(m) in (biome, "dungeon", "dirt")]
            if not matching:
                matching = valid_monsters  # fallback

            # Pick 1-3 monsters
            count = rng.randint(1, min(3, len(matching)))
            chosen = rng.sample(matching, count)
            monsters: List[Tuple[str, int, int]] = []
            for mname in chosen:
                mx = rng.randint(-self.spawn_radius, self.spawn_radius)
                my = rng.randint(-self.spawn_radius, self.spawn_radius)
                monsters.append((mname, mx, my))

            spawns.append(SpawnData(
                x=px, y=py, z=pz,
                radius=self.spawn_radius,
                monsters=monsters,
            ))
            used.add((px, py, pz))

        # Place NPCs in safe spots
        for npc_name in self.npc_types:
            idx = rng.randint(0, max(0, len(walkable_list) - 1))
            nx, ny, nz = walkable_list[idx]
            npc_spawns.append(NPCSpawnData(
                x=nx, y=ny, z=nz,
                npc_name=npc_name,
            ))

        return MapData(
            width=self.base_map.width if self.base_map else w,
            height=self.base_map.height if self.base_map else h,
            description=self.base_map.description if self.base_map else "Spawns",
            tiles=tiles,
            spawns=spawns,
            npc_spawns=npc_spawns,
        )

    @staticmethod
    def _ground_to_biome(ground_id: int) -> str:
        if ground_id == Tiles.WATER:
            return "water"
        if ground_id in (Tiles.GRASS,):
            return "grass"
        if ground_id in (Tiles.DIRT,):
            return "dirt"
        if ground_id in (Tiles.SAND,):
            return "sand"
        if ground_id in (Tiles.SNOW,):
            return "snow"
        if ground_id in (Tiles.ROCK, Tiles.STONE):
            return "dungeon"
        if ground_id == Tiles.STONE_WALL:
            return "dungeon"
        return "grass"
