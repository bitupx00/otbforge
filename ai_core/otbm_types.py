"""
OTBM Type Definitions and Constants.

Defines all node types, attributes, control characters, tile flags,
and well-known Tile IDs for the OTBM v2 binary format used by Tibia 8.0.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

# ---------------------------------------------------------------------------
# File signature
# ---------------------------------------------------------------------------
OTBM_MAGIC = b"OTBM"

# ---------------------------------------------------------------------------
# Control / escape bytes (used in the "escaped" payload encoding)
# ---------------------------------------------------------------------------
NODE_START = 0xFE
NODE_END = 0xFF
ESCAPE = 0xFD

# Bytes >= 0xFC need the 0xFD escape prefix in the wire format.
ESCAPE_THRESHOLD = 0xFC

# ---------------------------------------------------------------------------
# OTBM Node Types (first byte inside a node after 0xFE)
# ---------------------------------------------------------------------------
class NodeType:
    ROOTV1 = 1
    MAP_DATA = 2
    ITEM_DEF = 3
    TILE_AREA = 4
    TILE = 5
    ITEM = 6
    TILE_SQUARE = 7
    TILE_REF = 8
    SPAWNS = 9
    SPAWN_AREA = 10
    MONSTER = 11
    TOWNS = 12
    TOWN = 13
    HOUSETILE = 14
    WAYPOINTS = 15
    WAYPOINT = 16


# ---------------------------------------------------------------------------
# OTBM Tile / Item Attributes
# ---------------------------------------------------------------------------
class Attr:
    DESCRIPTION = 1
    EXT_FILE = 2
    TILE_FLAGS = 3
    ACTION_ID = 4
    UNIQUE_ID = 5
    TEXT = 6
    DESC = 7
    TELE_DEST = 8
    ITEM = 9           # compact ground item on a tile
    DEPOT_ID = 10
    EXT_SPAWN_FILE = 11
    RUNE_CHARGES = 12
    EXT_HOUSE_FILE = 13
    HOUSEDOORID = 14
    COUNT = 15
    DURATION = 16
    DECAYING_STATE = 17
    WRITTENDATE = 18
    WRITTENBY = 19
    SLEEPERGUID = 20
    SLEEPSTART = 21
    CHARGES = 22
    EXT_SPAWN_NPC_FILE = 23
    PODIUMOUTFIT = 40
    TIER = 41
    ATTRIBUTE_MAP = 128


# ---------------------------------------------------------------------------
# Tile flags (bitfield)
# ---------------------------------------------------------------------------
class TileFlags:
    NONE = 0
    PROTECTIONZONE = 1 << 0        # 0x01
    NOSUMMON_MONSTERZONE = 1 << 1  # 0x02
    NOPVPZONE = 1 << 2             # 0x04
    NOLOGOUTZONE = 1 << 3          # 0x08
    PVPZONE = 1 << 4               # 0x10
    NOHOUSETILE = 1 << 5           # 0x20
    TILESTATE_REFRESH = 1 << 6     # 0x40  — dynamic


# ---------------------------------------------------------------------------
# Well-known Tile IDs (Tibia 8.0 client)
# ---------------------------------------------------------------------------
class Tiles:
    # Ground
    GRASS = 102
    DIRT = 103
    SAND = 231
    WATER = 490
    LAVA = 5967
    SNOW = 7731

    # Mountains
    ROCK = 3638
    STONE = 3326

    # Walls
    STONE_WALL = 1102
    BRICK = 1060
    WOOD = 1018

    # Indoor floors
    FLOOR_WOOD = 530
    CARPET_RED = 5565

    # Doors
    CLOSED_DOOR = 5121
    OPEN_DOOR = 5122

    # Trees
    TREE_MIN = 2700
    TREE_MAX = 2708

    # Bushes
    BUSH_1 = 2767
    BUSH_2 = 2768

    # Flowers
    FLOWER_MIN = 2740
    FLOWER_MAX = 2743

    # Containers
    CHEST = 3756
    DRAWER = 3757

    # Stairs
    STONE_STAIRS = 433

    # Special
    TELEPORT = 1387


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class Position:
    """3-D map position."""
    x: int = 0
    y: int = 0
    z: int = 0


@dataclass
class ItemData:
    """Represents an item (on a tile, or inside a container)."""
    id: int
    count: int = 0               # subtype / count (0 = default)
    action_id: int = 0
    unique_id: int = 0
    text: str = ""
    description: str = ""
    charges: int = 0
    house_door_id: int = 0
    depot_id: int = 0
    teleport_dest: Optional[Position] = None
    children: List["ItemData"] = field(default_factory=list)
    # New v2+ fields
    duration: int = 0
    decay_state: int = 0
    written_date: int = 0
    written_by: str = ""
    rune_charges: int = 0
    sleeper_guid: int = 0
    sleep_start: int = 0

    @property
    def has_children(self) -> bool:
        return len(self.children) > 0


@dataclass
class TileData:
    """Represents a single map tile."""
    x: int
    y: int
    z: int
    ground_id: int = 0            # 0 = no ground
    items: List[ItemData] = field(default_factory=list)
    flags: int = TileFlags.NONE
    house_id: int = 0             # 0 = not a house tile


@dataclass
class TownData:
    """A town with a temple position."""
    id: int
    name: str
    temple: Position = field(default_factory=Position)


@dataclass
class WaypointData:
    """A named waypoint on the map."""
    name: str
    pos: Position = field(default_factory=Position)


@dataclass
class SpawnData:
    """Monster spawn point (radius + centre)."""
    x: int
    y: int
    z: int
    radius: int                   # spawn radius in tiles
    monsters: List[Tuple[str, int, int]] = field(default_factory=list)
    # Each entry: (monster_name, x_offset, y_offset) relative to spawn centre


@dataclass
class NPCSpawnData:
    """NPC spawn point."""
    x: int
    y: int
    z: int
    npc_name: str = ""
    direction: int = 0            # 0=South, 1=East, 2=North, 3=West


@dataclass
class MapData:
    """Top-level map container."""
    width: int = 2048
    height: int = 2048
    description: str = "Generated Map"
    otbm_version: int = 2
    otb_major_version: int = 2    # OTB major for 8.0
    otb_minor_version: int = 7    # OTB id for 8.0
    tiles: List[TileData] = field(default_factory=list)
    towns: List[TownData] = field(default_factory=list)
    waypoints: List[WaypointData] = field(default_factory=list)
    spawns: List[SpawnData] = field(default_factory=list)
    npc_spawns: List[NPCSpawnData] = field(default_factory=list)
    # External file refs (new fields for writer compat)
    ext_spawn_file: str = ""
    ext_house_file: str = ""
    ext_spawn_npc_file: str = ""
