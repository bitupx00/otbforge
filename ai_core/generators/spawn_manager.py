"""Spawn manager for placing monsters and NPCs with biome awareness and safety zones.

The SpawnManager handles intelligent placement of monster spawns and NPC
spawns across a map, respecting:
  - Biome-based monster selection (plains, forest, hills, mountains, dungeon, etc.)
  - Difficulty scaling per area
  - Safety zones (no monster spawns inside towns/protection zones)
  - Configurable density and spawn radius per monster type
  - NPC placement in towns and designated areas

Monster database includes difficulty tiers from easy (rats) to very hard (demons).
"""

import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from ai_core.otbm_types import (
    MapData,
    NPCSpawnData,
    Position,
    SpawnData,
    TileData,
    TileFlags,
    Tiles,
)


# ---------------------------------------------------------------------------
# Monster database with biomes and difficulty
# ---------------------------------------------------------------------------

@dataclass
class MonsterEntry:
    """A monster type with biome preferences and difficulty."""
    name: str
    difficulty: int  # 1=easy, 2=medium, 3=hard, 4=very hard, 5=extreme
    biomes: List[str] = field(default_factory=list)
    min_radius: int = 3
    max_radius: int = 8
    max_per_spawn: int = 3


MONSTER_DATABASE: Dict[str, MonsterEntry] = {
    # Easy monsters
    "rat": MonsterEntry("rat", difficulty=1, biomes=["plains", "forest", "dirt"]),
    "spider": MonsterEntry("spider", difficulty=1, biomes=["forest", "plains", "dirt"]),
    "snake": MonsterEntry("snake", difficulty=1, biomes=["plains", "swamp", "dirt"]),
    "rabbit": MonsterEntry("rabbit", difficulty=1, biomes=["plains", "forest"]),
    "deer": MonsterEntry("deer", difficulty=1, biomes=["plains", "forest"]),
    "wolf": MonsterEntry("wolf", difficulty=2, biomes=["forest", "plains", "snow"]),
    "bear": MonsterEntry("bear", difficulty=2, biomes=["forest", "mountains"]),
    "crab": MonsterEntry("crab", difficulty=1, biomes=["beach", "water"]),
    # Medium monsters
    "orc": MonsterEntry("orc", difficulty=2, biomes=["forest", "hills", "dirt"]),
    "orc warrior": MonsterEntry("orc warrior", difficulty=3, biomes=["forest", "hills", "dirt"]),
    "orc shaman": MonsterEntry("orc shaman", difficulty=3, biomes=["forest", "dirt"]),
    "goblin": MonsterEntry("goblin", difficulty=2, biomes=["hills", "dirt", "plains"]),
    "troll": MonsterEntry("troll", difficulty=2, biomes=["mountains", "hills", "dirt"]),
    "cyclops": MonsterEntry("cyclops", difficulty=3, biomes=["mountains", "hills"]),
    "minotaur": MonsterEntry("minotaur", difficulty=3, biomes=["dungeon", "hills"]),
    # Hard monsters
    "dragon": MonsterEntry("dragon", difficulty=4, biomes=["mountains", "dungeon"]),
    "demon": MonsterEntry("demon", difficulty=5, biomes=["dungeon"]),
    "vampire": MonsterEntry("vampire", difficulty=4, biomes=["dungeon"]),
    "skeleton": MonsterEntry("skeleton", difficulty=3, biomes=["dungeon", "hills"]),
    "ghost": MonsterEntry("ghost", difficulty=4, biomes=["dungeon"]),
    "ghoul": MonsterEntry("ghoul", difficulty=3, biomes=["dungeon"]),
    # Aquatic
    "fish": MonsterEntry("fish", difficulty=1, biomes=["water"]),
}


# ---------------------------------------------------------------------------
# NPC types and their preferred locations
# ---------------------------------------------------------------------------

@dataclass
class NPCType:
    """An NPC type with placement preferences."""
    name: str
    needs_town: bool = True
    preferred_building: str = ""  # e.g. "temple", "depot", "shop"


NPC_DATABASE: Dict[str, NPCType] = {
    "Merchant": NPCType("Merchant", needs_town=True, preferred_building="shop"),
    "Banker": NPCType("Banker", needs_town=True, preferred_building="depot"),
    "Healer": NPCType("Healer", needs_town=True, preferred_building="temple"),
    "Guild Leader": NPCType("Guild Leader", needs_town=True),
    "Alchemist": NPCType("Alchemist", needs_town=True, preferred_building="shop"),
    "Blacksmith": NPCType("Blacksmith", needs_town=True, preferred_building="shop"),
    "Mage Trainer": NPCType("Mage Trainer", needs_town=True),
    "Paladin Trainer": NPCType("Paladin Trainer", needs_town=True),
    "Knight Trainer": NPCType("Knight Trainer", needs_town=True),
    "TownCrier": NPCType("TownCrier", needs_town=True),
    "Mailbox NPC": NPCType("Mailbox NPC", needs_town=True),
}


# ---------------------------------------------------------------------------
# Biome ground tile mapping
# ---------------------------------------------------------------------------

GROUND_TO_BIOME: Dict[int, str] = {
    Tiles.GRASS: "plains",
    Tiles.DIRT: "dirt",
    Tiles.SAND: "beach",
    Tiles.WATER: "water",
    Tiles.LAVA: "dungeon",
    Tiles.SNOW: "snow",
    Tiles.ROCK: "mountains",
    Tiles.STONE: "mountains",
    Tiles.STONE_WALL: "dungeon",
    Tiles.WOOD: "forest",
    Tiles.BRICK: "dungeon",
    Tiles.FLOOR_WOOD: "dungeon",
    Tiles.CARPET_RED: "dungeon",
}


# ---------------------------------------------------------------------------
# SpawnManager
# ---------------------------------------------------------------------------

@dataclass
class SpawnManager:
    """Intelligent spawn placement manager.

    Parameters
    ----------
    map_data : MapData or None
        Base map to place spawns on. If None, uses width/height to create one.
    width, height : int
        Map dimensions (used if map_data is None).
    seed : int
        RNG seed for reproducibility.
    difficulty : int
        Global difficulty multiplier (1-5). Affects which monsters are selected.
    monster_density : float
        Target monster spawns per 1000 walkable tiles.
    npc_names : list[str]
        NPC types to place.
    safety_zone_margin : int
        Extra margin around protection zones where no monsters spawn.
    """

    map_data: Optional[MapData] = None
    width: int = 256
    height: int = 256
    seed: int = 42
    difficulty: int = 3
    monster_density: float = 0.8
    npc_names: List[str] = field(default_factory=lambda: [
        "Merchant", "Banker", "Healer", "TownCrier",
    ])
    safety_zone_margin: int = 5

    def generate(self) -> MapData:
        """Place monster and NPC spawns on the map and return updated MapData."""
        rng = random.Random(self.seed)
        md = self.map_data or MapData(width=self.width, height=self.height)

        # Build ground map and identify protection zones
        ground_map: Dict[Tuple[int, int, int], int] = {}
        protection_zones: set = set()

        for tile in md.tiles:
            key = (tile.x, tile.y, tile.z)
            ground_map[key] = tile.ground_id
            if tile.flags & TileFlags.PROTECTIONZONE:
                # Expand by margin
                for dx in range(-self.safety_zone_margin, self.safety_zone_margin + 1):
                    for dy in range(-self.safety_zone_margin, self.safety_zone_margin + 1):
                        protection_zones.add((tile.x + dx, tile.y + dy, tile.z))

        # Walkable tiles (non-water, non-wall)
        walkable: List[Tuple[int, int, int]] = []
        for (x, y, z), gid in ground_map.items():
            if gid > 0 and gid != Tiles.WATER and gid != Tiles.STONE_WALL:
                walkable.append((x, y, z))

        # --- Monster spawns ---
        spawns: List[SpawnData] = list(md.spawns)
        used_centers: set = set()

        # Determine eligible monsters based on difficulty
        eligible_monsters = [
            m for m in MONSTER_DATABASE.values()
            if m.difficulty <= self.difficulty
        ]
        if not eligible_monsters:
            eligible_monsters = list(MONSTER_DATABASE.values())

        # Target spawn count based on density
        target_count = int(len(walkable) * self.monster_density / 1000.0)

        for _ in range(target_count):
            if not walkable:
                break

            # Pick random walkable position
            idx = rng.randint(0, len(walkable) - 1)
            pos = walkable[idx]
            px, py, pz = pos

            # Skip safety zones
            if pos in protection_zones:
                continue

            # Skip if too close to existing spawn center
            if any(abs(px - ux) < 10 and abs(py - uy) < 10
                   for (ux, uy, _) in used_centers):
                continue

            # Determine biome from ground tile
            gid = ground_map.get(pos, Tiles.GRASS)
            biome = GROUND_TO_BIOME.get(gid, "plains")

            # Filter monsters by biome
            matching = [m for m in eligible_monsters
                        if biome in m.biomes or "dungeon" in m.biomes]
            if not matching:
                matching = eligible_monsters

            # Pick 1-2 monsters
            count = rng.randint(1, min(2, len(matching)))
            chosen = rng.sample(matching, count)

            radius = rng.randint(3, 8)
            monsters: List[Tuple[str, int, int]] = []
            for m in chosen:
                ox = rng.randint(-radius, radius)
                oy = rng.randint(-radius, radius)
                monsters.append((m.name, ox, oy))

            spawn = SpawnData(
                x=px, y=py, z=pz,
                radius=radius,
                monsters=monsters,
            )
            spawns.append(spawn)
            used_centers.add((px, py, pz))

        # --- NPC spawns ---
        npc_spawns: List[NPCSpawnData] = list(md.npc_spawns)

        for npc_name in self.npc_names:
            # Try to place NPC in a protection zone / town
            placed = False

            # Find protection zone tiles
            pz_tiles = [pos for pos in walkable if pos in protection_zones]
            if pz_tiles:
                idx = rng.randint(0, len(pz_tiles) - 1)
                nx, ny, nz = pz_tiles[idx]
                npc_spawns.append(NPCSpawnData(
                    x=nx, y=ny, z=nz,
                    npc_name=npc_name,
                    direction=rng.randint(0, 3),
                ))
                placed = True

            if not placed and walkable:
                idx = rng.randint(0, len(walkable) - 1)
                nx, ny, nz = walkable[idx]
                npc_spawns.append(NPCSpawnData(
                    x=nx, y=ny, z=nz,
                    npc_name=npc_name,
                    direction=rng.randint(0, 3),
                ))

        # Return updated map
        result = MapData(
            width=md.width,
            height=md.height,
            description=md.description,
            tiles=list(md.tiles),
            towns=list(md.towns),
            waypoints=list(md.waypoints),
            spawns=spawns,
            npc_spawns=npc_spawns,
        )
        # Preserve houses if the underlying MapData supports it
        if hasattr(md, 'houses'):
            result.houses = list(md.houses)
        return result

    def get_monsters_for_biome(self, biome: str) -> List[str]:
        """Return monster names appropriate for a given biome."""
        return [
            m.name for m in MONSTER_DATABASE.values()
            if biome in m.biomes
        ]

    def get_monsters_for_difficulty(self, max_difficulty: int) -> List[str]:
        """Return monster names at or below a difficulty level."""
        return [
            m.name for m in MONSTER_DATABASE.values()
            if m.difficulty <= max_difficulty
        ]
