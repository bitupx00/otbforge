"""
Quest Generator — Procedural quest dungeon areas.

Generates themed quest areas with:
  - Entry area with NPC quest giver
  - Challenge rooms (monsters, puzzles)
  - Boss room with special items
  - Reward chest area

Built on top of the dungeon generator tile conventions.
Uses QuestTemplate dataclasses for 12+ predefined quest themes.

Usage::

    from ai_core.generators.quest import QuestGenerator, DragonSlayerQuest

    gen = QuestGenerator(seed=42)
    gen.generate_quest(map_data, DragonSlayerQuest, position=Position(100, 100, 7))
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple

from ai_core.models import (
    ItemData,
    MapData,
    NPCSpawnData,
    Position,
    SpawnData,
    TileData,
    TileFlag,
    Tiles,
)


# ---------------------------------------------------------------------------
# Dungeon tile IDs (matching DungeonGenerator conventions)
# ---------------------------------------------------------------------------

class QuestTiles:
    """Tibia tile IDs for quest area construction."""
    FLOOR_STONE = 410
    FLOOR_DARK = 411
    FLOOR_MOSS = 412
    WALL_STONE = 1010
    WALL_BRICK = 1011
    WALL_DARK = 1012
    DOOR_CLOSED = 5121
    DOOR_OPEN = 5122
    STAIRS_DOWN = 433
    STAIRS_UP = 836
    CHEST = 3756
    TELEPORT = 1387
    # Ground tiles for surface entry
    GRASS = 102
    DIRT = 103


# ---------------------------------------------------------------------------
# Quest difficulty levels
# ---------------------------------------------------------------------------

class QuestDifficulty(str, Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"
    LEGENDARY = "legendary"


# ---------------------------------------------------------------------------
# Room types within a quest
# ---------------------------------------------------------------------------

class QuestRoomType(str, Enum):
    ENTRY = "entry"
    CORRIDOR = "corridor"
    CHALLENGE = "challenge"
    BOSS = "boss"
    REWARD = "reward"


# ---------------------------------------------------------------------------
# QuestTemplate dataclass
# ---------------------------------------------------------------------------

@dataclass
class QuestTemplate:
    """Template defining a quest theme and its parameters."""
    name: str
    description: str
    difficulty: QuestDifficulty = QuestDifficulty.MEDIUM
    required_level: int = 20
    boss_monster: str = "Dragon"
    boss_item_id: int = 0  # Special item placed in boss room
    reward_items: List[int] = field(default_factory=lambda: [3756])  # Chest by default
    ground_id: int = QuestTiles.FLOOR_STONE
    wall_id: int = QuestTiles.WALL_STONE
    challenge_monsters: List[str] = field(default_factory=lambda: ["rat", "spider"])
    num_challenge_rooms: int = 3
    entry_npc_name: str = "Quest Giver"
    area_width: int = 30
    area_height: int = 30
    theme_color_desc: str = "stone"  # For visual description

    def __repr__(self) -> str:
        return (f"QuestTemplate({self.name!r}, level={self.required_level}, "
                f"difficulty={self.difficulty.value})")


# ---------------------------------------------------------------------------
# 12+ predefined quest templates
# ---------------------------------------------------------------------------

@dataclass
class DragonSlayerQuest(QuestTemplate):
    """Classic dragon slayer quest in a volcanic cave."""
    name: str = "Dragon's Lair"
    description: str = "Slay the ancient dragon terrorizing the kingdom."
    difficulty: QuestDifficulty = QuestDifficulty.HARD
    required_level: int = 50
    boss_monster: str = "Dragon Lord"
    boss_item_id: int = 5919  # Dragon scale
    reward_items: List[int] = field(default_factory=lambda: [3756, 5919])
    challenge_monsters: List[str] = field(default_factory=lambda: ["dragon hatchling", "fire elemental"])
    ground_id: int = 411
    wall_id: int = 1011
    entry_npc_name: str = "The Dragon Hunter"
    area_width: int = 35
    area_height: int = 35
    theme_color_desc: str = "volcanic"


@dataclass
class TombRaiderQuest(QuestTemplate):
    """Explore ancient tombs and defeat the mummy lord."""
    name: str = "Tomb of the Pharaoh"
    description: str = "Explore the cursed tomb and find the pharaoh's treasure."
    difficulty: QuestDifficulty = QuestDifficulty.MEDIUM
    required_level: int = 35
    boss_monster: str = "Mummy Pharaoh"
    boss_item_id: int = 4850  # Golden sarcophagus
    reward_items: List[int] = field(default_factory=lambda: [3756, 4850, 3031])
    challenge_monsters: List[str] = field(default_factory=lambda: ["mummy", "scarab", "ghost"])
    ground_id: int = 410
    wall_id: int = 1010
    entry_npc_name: str = "Archaeologist Jones"
    area_width: int = 30
    area_height: int = 30
    theme_color_desc: str = "sandy"


@dataclass
class ElvenRuinsQuest(QuestTemplate):
    """Haunted elven forest ruins."""
    name: str = "Elven Ruins"
    description: str = "Purify the corrupted elven sanctuary."
    difficulty: QuestDifficulty = QuestDifficulty.MEDIUM
    required_level: int = 30
    boss_monster: str = "Corrupted Elf"
    boss_item_id: int = 3059
    reward_items: List[int] = field(default_factory=lambda: [3756, 3059])
    challenge_monsters: List[str] = field(default_factory=lambda: ["wilowisp", "pixie", "treechnid"])
    ground_id: int = 412
    wall_id: int = 1012
    entry_npc_name: str = "Elven Sage"
    area_width: int = 28
    area_height: int = 28
    theme_color_desc: str = "forest"


@dataclass
class IceCaveQuest(QuestTemplate):
    """Frozen cave with ice creatures."""
    name: str = "Frozen Depths"
    description: str = "Delve into the eternal ice and defeat the frost titan."
    difficulty: QuestDifficulty = QuestDifficulty.HARD
    required_level: int = 45
    boss_monster: str = "Frost Titan"
    boss_item_id: int = 7442
    reward_items: List[int] = field(default_factory=lambda: [3756, 7442])
    challenge_monsters: List[str] = field(default_factory=lambda: ["ice golem", "frostbite", "crystal spider"])
    ground_id: int = 413
    wall_id: int = 1013
    entry_npc_name: str = "Frost Explorer"
    area_width: int = 32
    area_height: int = 32
    theme_color_desc: str = "icy"


@dataclass
class DemonCryptQuest(QuestTemplate):
    """Underground demon crypt."""
    name: str = "Demon Crypt"
    description: str = "Seal the demon portal before it's too late."
    difficulty: QuestDifficulty = QuestDifficulty.LEGENDARY
    required_level: int = 80
    boss_monster: str = "Archdemon"
    boss_item_id: int = 5906
    reward_items: List[int] = field(default_factory=lambda: [3756, 5906, 6528])
    challenge_monsters: List[str] = field(default_factory=lambda: ["demon", "dark torturer", "destroyer"])
    ground_id: int = 414
    wall_id: int = 1014
    entry_npc_name: str = "The Exorcist"
    area_width: int = 35
    area_height: int = 35
    theme_color_desc: str = "dark"


@dataclass
class PirateCoveQuest(QuestTemplate):
    """Pirate cove with undead pirates."""
    name: str = "Pirate's Cove"
    description: str = "Plunder the cursed pirate treasure."
    difficulty: QuestDifficulty = QuestDifficulty.EASY
    required_level: int = 15
    boss_monster: str = "Captain Bones"
    boss_item_id: int = 6126
    reward_items: List[int] = field(default_factory=lambda: [3756, 6126])
    challenge_monsters: List[str] = field(default_factory=lambda: ["pirate ghost", "skeleton", "crab"])
    ground_id: int = 415
    wall_id: int = 1015
    entry_npc_name: str = "Old Sailor"
    area_width: int = 25
    area_height: int = 25
    theme_color_desc: str = "sandy"


@dataclass
class SpiderNestQuest(QuestTemplate):
    """Giant spider nest infestation."""
    name: str = "Spider Nest"
    description: str = "Clear out the giant spider infestation."
    difficulty: QuestDifficulty = QuestDifficulty.EASY
    required_level: int = 10
    boss_monster: str = "Spider Queen"
    boss_item_id: int = 8857
    reward_items: List[int] = field(default_factory=lambda: [3756, 8857])
    challenge_monsters: List[str] = field(default_factory=lambda: ["spider", "tarantula", "scorpion"])
    ground_id: int = 410
    wall_id: int = 1010
    entry_npc_name: str = "Village Elder"
    area_width: int = 22
    area_height: int = 22
    theme_color_desc: str = "earthy"


@dataclass
class OrcFortressQuest(QuestTemplate):
    """Storm an orc fortress."""
    name: str = "Orc Fortress"
    description: str = "Lay siege to the orc warlord's fortress."
    difficulty: QuestDifficulty = QuestDifficulty.MEDIUM
    required_level: int = 25
    boss_monster: str = "Orc Warlord"
    boss_item_id: int = 3365
    reward_items: List[int] = field(default_factory=lambda: [3756, 3365])
    challenge_monsters: List[str] = field(default_factory=lambda: ["orc", "orc warrior", "orc shaman"])
    ground_id: int = 410
    wall_id: int = 1010
    entry_npc_name: str = "General Knight"
    area_width: int = 30
    area_height: int = 30
    theme_color_desc: str = "stone"


@dataclass
class VampireManorQuest(QuestTemplate):
    """Haunted vampire manor."""
    name: str = "Vampire Manor"
    description: str = "Defeat the vampire lord and free the manor from darkness."
    difficulty: QuestDifficulty = QuestDifficulty.HARD
    required_level: int = 55
    boss_monster: str = "Vampire Lord"
    boss_item_id: int = 3976
    reward_items: List[int] = field(default_factory=lambda: [3756, 3976])
    challenge_monsters: List[str] = field(default_factory=lambda: ["vampire", "blood bat", "ghoul"])
    ground_id: int = 412
    wall_id: int = 1012
    entry_npc_name: str = "The Priest"
    area_width: int = 28
    area_height: int = 28
    theme_color_desc: str = "gothic"


@dataclass
class DwarvenMinesQuest(QuestTemplate):
    """Abandoned dwarf mines with rock creatures."""
    name: str = "Dwarven Mines"
    description: str = "Reclaim the lost dwarven mines from the stone creatures."
    difficulty: QuestDifficulty = QuestDifficulty.MEDIUM
    required_level: int = 30
    boss_monster: str = "Stone Golem King"
    boss_item_id: int = 5891
    reward_items: List[int] = field(default_factory=lambda: [3756, 5891])
    challenge_monsters: List[str] = field(default_factory=lambda: ["dwarf geomancer", "stone golem", "cave rat"])
    ground_id: int = 410
    wall_id: int = 1010
    entry_npc_name: str = "Dwarven Engineer"
    area_width: int = 32
    area_height: int = 32
    theme_color_desc: str = "rocky"


@dataclass
class AncientTempleQuest(QuestTemplate):
    """Sunken ancient temple."""
    name: str = "Ancient Temple"
    description: str = "Explore the sunken temple and retrieve the sacred relic."
    difficulty: QuestDifficulty = QuestDifficulty.LEGENDARY
    required_level: int = 70
    boss_monster: str = "Temple Guardian"
    boss_item_id: int = 8266
    reward_items: List[int] = field(default_factory=lambda: [3756, 8266, 3049])
    challenge_monsters: List[str] = field(default_factory=lambda: ["serpent spawn", "medusa", "sea serpent"])
    ground_id: int = 411
    wall_id: int = 1011
    entry_npc_name: str = "High Priestess"
    area_width: int = 35
    area_height: int = 35
    theme_color_desc: str = "aquatic"


@dataclass
class BanditHideoutQuest(QuestTemplate):
    """Forest bandit camp."""
    name: str = "Bandit Hideout"
    description: str = "Clear the bandit camp threatening the trade routes."
    difficulty: QuestDifficulty = QuestDifficulty.EASY
    required_level: int = 12
    boss_monster: str = "Bandit King"
    boss_item_id: int = 3367
    reward_items: List[int] = field(default_factory=lambda: [3756, 3367])
    challenge_monsters: List[str] = field(default_factory=lambda: ["bandit", "highwayman", "mugger"])
    ground_id: int = 412
    wall_id: int = 1012
    entry_npc_name: str = "Merchant Guild Leader"
    area_width: int = 24
    area_height: int = 24
    theme_color_desc: str = "woodland"


# ---------------------------------------------------------------------------
# QuestRoom internal data
# ---------------------------------------------------------------------------

@dataclass
class _QuestRoom:
    """Internal room within a quest area."""
    x: int
    y: int
    w: int
    h: int
    room_type: QuestRoomType = QuestRoomType.CHALLENGE

    @property
    def cx(self) -> int:
        return self.x + self.w // 2

    @property
    def cy(self) -> int:
        return self.y + self.h // 2


# ---------------------------------------------------------------------------
# QuestGenerator
# ---------------------------------------------------------------------------

@dataclass
class QuestGenerator:
    """Procedural quest area generator.

    Parameters
    ----------
    seed : int
        RNG seed for reproducible generation.
    corridor_width : int
        Width of corridors between rooms.
    """

    seed: int = 42
    corridor_width: int = 2

    # ---- Public API ----

    def generate_quest(
        self,
        map_data: MapData,
        template: QuestTemplate,
        position: Position,
    ) -> None:
        """Generate a quest area on the given map at the given position.

        Modifies map_data in-place by appending tiles, spawns, and NPC spawns.
        """
        rng = random.Random(self.seed)
        ox, oy, oz = position.x, position.y, position.z

        # Generate room layout
        rooms = self._plan_rooms(template, rng, ox, oy)
        tile_grid: Dict[Tuple[int, int], TileData] = {}
        spawns: List[SpawnData] = []
        npc_spawns: List[NPCSpawnData] = []

        # Build each room
        for room in rooms:
            self._build_room(room, template, rng, oz, tile_grid, spawns, npc_spawns)

        # Connect rooms with corridors
        for i in range(len(rooms) - 1):
            self._connect_rooms(rooms[i], rooms[i + 1], template, oz, tile_grid)

        # Add all tiles to the map
        for tile in tile_grid.values():
            # Avoid overwriting existing tiles at the same position
            existing = None
            for t in map_data.tiles:
                if t.x == tile.x and t.y == tile.y and t.z == tile.z:
                    existing = t
                    break
            if existing is None:
                map_data.tiles.append(tile)

        # Add spawns
        map_data.spawns.extend(spawns)
        map_data.npc_spawns.extend(npc_spawns)

    def generate_standalone(
        self,
        template: QuestTemplate,
        position: Optional[Position] = None,
    ) -> MapData:
        """Generate a quest area as a standalone MapData."""
        if position is None:
            position = Position(0, 0, 7)
        map_data = MapData(
            width=template.area_width + 10,
            height=template.area_height + 10,
            description=f"Quest: {template.name}",
        )
        self.generate_quest(map_data, template, position)
        return map_data

    @staticmethod
    def get_templates() -> List[QuestTemplate]:
        """Return all predefined quest templates."""
        return [
            DragonSlayerQuest(),
            TombRaiderQuest(),
            ElvenRuinsQuest(),
            IceCaveQuest(),
            DemonCryptQuest(),
            PirateCoveQuest(),
            SpiderNestQuest(),
            OrcFortressQuest(),
            VampireManorQuest(),
            DwarvenMinesQuest(),
            AncientTempleQuest(),
            BanditHideoutQuest(),
        ]

    # ---- Internal methods ----

    def _plan_rooms(
        self,
        template: QuestTemplate,
        rng: random.Random,
        ox: int,
        oy: int,
    ) -> List[_QuestRoom]:
        """Plan the room layout for the quest."""
        w, h = template.area_width, template.area_height
        rooms: List[_QuestRoom] = []

        # Entry room (top-left area)
        entry_w = max(5, w // 5)
        entry_h = max(5, h // 5)
        rooms.append(_QuestRoom(
            x=ox + 1, y=oy + 1,
            w=entry_w, h=entry_h,
            room_type=QuestRoomType.ENTRY,
        ))

        # Challenge rooms (middle section)
        num_challenges = template.num_challenge_rooms
        challenge_area_x = ox + entry_w + 2
        challenge_area_w = w - entry_w - 6  # Reserve space for boss + reward

        if num_challenges > 0 and challenge_area_w > 5:
            room_w = min(6, challenge_area_w // num_challenges - 1)
            room_h = max(5, h - 4)
            spacing = (challenge_area_w - room_w * num_challenges) // max(num_challenges - 1, 1)
            spacing = max(spacing, 1)

            for i in range(num_challenges):
                rx = challenge_area_x + i * (room_w + spacing)
                ry = oy + 1 + (h - room_h) // 2
                rooms.append(_QuestRoom(
                    x=rx, y=ry,
                    w=max(4, room_w), h=max(4, room_h),
                    room_type=QuestRoomType.CHALLENGE,
                ))

        # Boss room
        boss_w = max(6, w // 5)
        boss_h = max(6, h - 4)
        boss_x = ox + w - boss_w - 2
        boss_y = oy + 2
        rooms.append(_QuestRoom(
            x=boss_x, y=boss_y,
            w=boss_w, h=boss_h,
            room_type=QuestRoomType.BOSS,
        ))

        # Reward room (bottom-right)
        reward_w = max(4, w // 6)
        reward_h = max(4, h // 4)
        reward_x = ox + w - reward_w - 1
        reward_y = oy + h - reward_h - 1
        rooms.append(_QuestRoom(
            x=reward_x, y=reward_y,
            w=reward_w, h=reward_h,
            room_type=QuestRoomType.REWARD,
        ))

        return rooms

    def _build_room(
        self,
        room: _QuestRoom,
        template: QuestTemplate,
        rng: random.Random,
        oz: int,
        tile_grid: Dict[Tuple[int, int], TileData],
        spawns: List[SpawnData],
        npc_spawns: List[NPCSpawnData],
    ) -> None:
        """Build a single room and populate it based on type."""
        # Fill room with floor
        for ry in range(room.y, room.y + room.h):
            for rx in range(room.x, room.x + room.w):
                tile_grid[(rx, ry)] = TileData(
                    x=rx, y=ry, z=oz,
                    ground_id=template.ground_id,
                )

        # Build walls around room perimeter
        for rx in range(room.x - 1, room.x + room.w + 1):
            for ry in range(room.y - 1, room.y + room.h + 1):
                if (rx, ry) not in tile_grid:
                    tile_grid[(rx, ry)] = TileData(
                        x=rx, y=ry, z=oz,
                        ground_id=template.wall_id,
                    )

        cx, cy = room.cx, room.cy

        if room.room_type == QuestRoomType.ENTRY:
            # NPC quest giver at center
            npc_spawns.append(NPCSpawnData(
                x=cx, y=cy, z=oz,
                npc_name=template.entry_npc_name,
                direction=0,
            ))
            # Place a decorative chest/teleport for quest start marker
            tile_grid[(cx, cy)] = TileData(
                x=cx, y=cy, z=oz,
                ground_id=template.ground_id,
                items=[ItemData(id=QuestTiles.CHEST, unique_id=1000 + hash(template.name) % 9000)],
            )

        elif room.room_type == QuestRoomType.CHALLENGE:
            # Place monster spawns
            monsters = []
            for name in template.challenge_monsters:
                x_off = rng.randint(-2, 2)
                y_off = rng.randint(-2, 2)
                monsters.append((name, x_off, y_off))
            if monsters:
                spawns.append(SpawnData(
                    x=cx, y=cy, z=oz,
                    radius=max(room.w, room.h) // 2,
                    monsters=monsters,
                ))
            # Occasionally place a chest
            if rng.random() < 0.3:
                tile_grid[(cx, cy)] = TileData(
                    x=cx, y=cy, z=oz,
                    ground_id=template.ground_id,
                    items=[ItemData(id=QuestTiles.CHEST)],
                )

        elif room.room_type == QuestRoomType.BOSS:
            # Boss spawn
            spawns.append(SpawnData(
                x=cx, y=cy, z=oz,
                radius=max(room.w, room.h) // 2,
                monsters=[(template.boss_monster, 0, 0)],
            ))
            # Boss special item on ground
            items = []
            if template.boss_item_id > 0:
                items.append(ItemData(id=template.boss_item_id, unique_id=2000 + hash(template.name) % 8000))
            items.append(ItemData(id=QuestTiles.CHEST))
            tile_grid[(cx, cy)] = TileData(
                x=cx, y=cy, z=oz,
                ground_id=template.ground_id,
                items=items,
                flags=TileFlag.NONE,
            )

        elif room.room_type == QuestRoomType.REWARD:
            # Multiple reward chests
            reward_positions = [(cx, cy)]
            for dx, dy in [(1, 0), (-1, 0), (0, 1), (0, -1)]:
                px, py = cx + dx, cy + dy
                if room.x <= px < room.x + room.w and room.y <= py < room.y + room.h:
                    reward_positions.append((px, py))

            for rpx, rpy in reward_positions:
                reward_items = [ItemData(id=item_id) for item_id in template.reward_items]
                tile_grid[(rpx, rpy)] = TileData(
                    x=rpx, y=rpy, z=oz,
                    ground_id=template.ground_id,
                    items=reward_items,
                )

    def _connect_rooms(
        self,
        a: _QuestRoom,
        b: _QuestRoom,
        template: QuestTemplate,
        oz: int,
        tile_grid: Dict[Tuple[int, int], TileData],
    ) -> None:
        """Carve an L-shaped corridor between two rooms."""
        ax, ay = a.cx, a.cy
        bx, by = b.cx, b.cy
        hw = self.corridor_width // 2

        cx, cy = ax, ay
        while cx != bx:
            for dw in range(-hw, hw + 1):
                key = (cx, cy + dw)
                if key not in tile_grid or tile_grid[key].ground_id == template.wall_id:
                    tile_grid[key] = TileData(x=cx, y=cy + dw, z=oz, ground_id=template.ground_id)
            cx += 1 if bx > ax else -1
        while cy != by:
            for dw in range(-hw, hw + 1):
                key = (cx + dw, cy)
                if key not in tile_grid or tile_grid[key].ground_id == template.wall_id:
                    tile_grid[key] = TileData(x=cx + dw, y=cy, z=oz, ground_id=template.ground_id)
            cy += 1 if by > ay else -1
        # Endpoint
        for dw in range(-hw, hw + 1):
            key = (cx, cy + dw)
            if key not in tile_grid or tile_grid[key].ground_id == template.wall_id:
                tile_grid[key] = TileData(x=cx, y=cy + dw, z=oz, ground_id=template.ground_id)
