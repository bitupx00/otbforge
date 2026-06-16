"""
OTBM Data Models.

Defines all data classes, constants, and enums for the OTBM binary format
used by Tibia (versions 2 and 3).  Every model includes validation and
human-readable ``__repr__`` output.

Constants
---------
* Control bytes:  NODE_START, NODE_END, ESCAPE
* Node types:     NodeType  (ROOTV1 … WAYPOINT)
* Attributes:     Attr     (DESCRIPTION … TIER)
* Tile flags:     TileFlag (PROTECTIONZONE … HASLIGHT)
* OTB IDs:        OtbVersion  presets for common client versions
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from enum import IntFlag
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# File signature
# ---------------------------------------------------------------------------
OTBM_MAGIC = b"OTBM"

# ---------------------------------------------------------------------------
# Control / escape bytes
# ---------------------------------------------------------------------------
NODE_START = 0xFE
NODE_END   = 0xFF
ESCAPE     = 0xFD

# Bytes with value >= ESCAPE_THRESHOLD need the ESCAPE prefix on the wire.
ESCAPE_THRESHOLD = 0xFD  # 0xFD, 0xFE, 0xFF


# ---------------------------------------------------------------------------
# OTBM Node Types
# ---------------------------------------------------------------------------
class NodeType:
    ROOTV1      = 1
    MAP_DATA    = 2
    ITEM_DEF    = 3
    TILE_AREA   = 4
    TILE        = 5
    ITEM        = 6
    TILE_SQUARE = 7
    TILE_REF    = 8
    SPAWNS      = 9
    SPAWN_AREA  = 10
    MONSTER     = 11
    TOWNS       = 12
    TOWN        = 13
    HOUSETILE   = 14
    WAYPOINTS   = 15
    WAYPOINT    = 16


# ---------------------------------------------------------------------------
# OTBM Attribute IDs
# ---------------------------------------------------------------------------
class Attr:
    DESCRIPTION      = 1
    EXT_FILE         = 2
    TILE_FLAGS       = 3
    ACTION_ID        = 4
    UNIQUE_ID        = 5
    TEXT             = 6
    DESC             = 7
    TELE_DEST        = 8
    ITEM             = 9      # compact ground item on a tile
    DEPOT_ID         = 10
    EXT_SPAWN_FILE   = 11
    RUNE_CHARGES     = 12
    EXT_HOUSE_FILE   = 13
    HOUSEDOORID      = 14
    COUNT            = 15
    DURATION         = 16
    DECAYING_STATE   = 17
    WRITTENDATE      = 18
    WRITTENBY        = 19
    SLEEPERGUID      = 20
    SLEEPSTART       = 21
    CHARGES          = 22
    EXT_SPAWN_NPC_FILE = 23
    PODIUMOUTFIT     = 40     # v3+
    TIER             = 41     # v3+
    ATTRIBUTE_MAP    = 128


# ---------------------------------------------------------------------------
# Tile Flags  (bitfield)
# ---------------------------------------------------------------------------
class TileFlag(IntFlag):
    NONE              = 0
    PROTECTIONZONE    = 1 << 0   # 0x01
    NOSUMMON_MONSTERZONE = 1 << 1  # 0x02
    NOPVPZONE         = 1 << 2   # 0x04
    NOLOGOUTZONE      = 1 << 3   # 0x08
    PVPZONE           = 1 << 4   # 0x10
    NOHOUSETILE       = 1 << 5   # 0x20
    REFRESH           = 1 << 6   # 0x40  (dynamic / no-save)
    NOSAVEZONE        = 1 << 7   # 0x80
    HASLIGHT          = 1 << 8   # 0x100


# Backward-compat alias
TileFlags = TileFlag


# ---------------------------------------------------------------------------
# OTB version presets  (major, minor)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class OtbVersion:
    major: int
    minor: int

    def __repr__(self) -> str:
        return f"OtbVersion(major={self.major}, minor={self.minor})"


# Common presets
OTB_V2_7  = OtbVersion(major=2, minor=7)   # Tibia 7.6–8.x  (OTBM v2)
OTB_V3_12 = OtbVersion(major=3, minor=12)   # Tibia 10+      (OTBM v3)


# ---------------------------------------------------------------------------
# Well-known Tile IDs (Tibia 8.0 client)
# ---------------------------------------------------------------------------
class Tiles:
    GRASS       = 102
    DIRT        = 103
    SAND        = 231
    WATER       = 490
    LAVA        = 5967
    SNOW        = 7731
    ROCK        = 3638
    STONE       = 3326
    STONE_WALL  = 1102
    BRICK       = 1060
    WOOD        = 1018
    FLOOR_WOOD  = 530
    CARPET_RED  = 5565
    CLOSED_DOOR = 5121
    OPEN_DOOR   = 5122
    TREE_MIN    = 2700
    TREE_MAX    = 2708
    BUSH_1      = 2767
    BUSH_2      = 2768
    FLOWER_MIN  = 2740
    FLOWER_MAX  = 2743
    CHEST       = 3756
    DRAWER      = 3757
    STONE_STAIRS = 433
    TELEPORT    = 1387


# ===========================================================================
# Data classes
# ===========================================================================

@dataclass
class Position:
    """3-D map position."""
    x: int = 0
    y: int = 0
    z: int = 0

    def __repr__(self) -> str:
        return f"Position({self.x}, {self.y}, {self.z})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Position):
            return NotImplemented
        return (self.x, self.y, self.z) == (other.x, other.y, other.z)

    def validate(self) -> None:
        if not (0 <= self.x <= 0xFFFF):
            raise ValueError(f"x out of range: {self.x}")
        if not (0 <= self.y <= 0xFFFF):
            raise ValueError(f"y out of range: {self.y}")
        if not (0 <= self.z <= 15):
            raise ValueError(f"z out of range: {self.z}")


@dataclass
class ItemData:
    """An item on a tile, or inside a container."""
    id: int
    count: int          = 0
    action_id: int      = 0
    unique_id: int      = 0
    text: str           = ""
    description: str    = ""
    charges: int        = 0
    house_door_id: int  = 0
    depot_id: int       = 0
    teleport_dest: Optional[Position] = None
    duration: int       = 0       # v2+
    decay_state: int    = 0       # 0=default, 1=decaying, 2=stopped
    written_date: int   = 0       # unix timestamp
    written_by: str     = ""
    rune_charges: int   = 0
    sleeper_guid: int   = 0
    sleep_start: int    = 0
    children: List["ItemData"] = field(default_factory=list)

    @property
    def has_children(self) -> bool:
        return len(self.children) > 0

    def __repr__(self) -> str:
        parts = [f"ItemData(id={self.id}"]
        extras: list = []
        if self.count:        extras.append(f"count={self.count}")
        if self.action_id:    extras.append(f"action_id={self.action_id}")
        if self.unique_id:    extras.append(f"unique_id={self.unique_id}")
        if self.text:         extras.append(f"text={self.text!r}")
        if self.description:  extras.append(f"desc={self.description!r}")
        if self.charges:      extras.append(f"charges={self.charges}")
        if self.house_door_id:extras.append(f"door_id={self.house_door_id}")
        if self.depot_id:     extras.append(f"depot={self.depot_id}")
        if self.teleport_dest:extras.append(f"tele_dest={self.teleport_dest!r}")
        if self.duration:     extras.append(f"duration={self.duration}")
        if self.decay_state:  extras.append(f"decay={self.decay_state}")
        if self.written_date: extras.append(f"written_date={self.written_date}")
        if self.written_by:   extras.append(f"written_by={self.written_by!r}")
        if self.children:     extras.append(f"children={len(self.children)}")
        if extras:
            parts.append(", " + ", ".join(extras))
        parts.append(")")
        return "".join(parts)

    def validate(self) -> None:
        if not (0 < self.id <= 0xFFFF):
            raise ValueError(f"item id out of range: {self.id}")
        if not (0 <= self.count <= 0xFF):
            raise ValueError(f"count out of range: {self.count}")
        if not (0 <= self.action_id <= 0xFFFF):
            raise ValueError(f"action_id out of range: {self.action_id}")
        if not (0 <= self.unique_id <= 0xFFFF):
            raise ValueError(f"unique_id out of range: {self.unique_id}")
        if self.teleport_dest:
            self.teleport_dest.validate()


@dataclass
class TileData:
    """A single map tile."""
    x: int
    y: int
    z: int
    ground_id: int      = 0
    items: List[ItemData] = field(default_factory=list)
    flags: TileFlag      = TileFlag.NONE
    house_id: int        = 0

    def __repr__(self) -> str:
        flag_str = ""
        if self.flags:
            flag_str = f", flags={self.flags:#x}"
        house_str = ""
        if self.house_id:
            house_str = f", house={self.house_id}"
        items_str = ""
        if self.items:
            items_str = f", items={len(self.items)}"
        return (f"TileData({self.x}, {self.y}, {self.z}, "
                f"ground={self.ground_id}{flag_str}{house_str}{items_str})")

    def validate(self) -> None:
        if not (0 <= self.x <= 0xFFFF):
            raise ValueError(f"tile x out of range: {self.x}")
        if not (0 <= self.y <= 0xFFFF):
            raise ValueError(f"tile y out of range: {self.y}")
        if not (0 <= self.z <= 15):
            raise ValueError(f"tile z out of range: {self.z}")
        for item in self.items:
            item.validate()


@dataclass
class TownData:
    """A town with a temple position (spawn point)."""
    id: int
    name: str
    temple: Position = field(default_factory=Position)

    def __repr__(self) -> str:
        return f"TownData(id={self.id}, name={self.name!r}, temple={self.temple})"

    def validate(self) -> None:
        if self.id <= 0:
            raise ValueError(f"town id must be > 0: {self.id}")
        self.temple.validate()


@dataclass
class WaypointData:
    """A named waypoint on the map."""
    name: str
    pos: Position = field(default_factory=Position)

    def __repr__(self) -> str:
        return f"WaypointData(name={self.name!r}, pos={self.pos})"

    def validate(self) -> None:
        self.pos.validate()


@dataclass
class SpawnData:
    """Monster spawn point (centre + radius)."""
    x: int
    y: int
    z: int
    radius: int = 0
    monsters: List[Tuple[str, int, int]] = field(default_factory=list)

    def __repr__(self) -> str:
        return (f"SpawnData({self.x}, {self.y}, {self.z}, "
                f"radius={self.radius}, monsters={len(self.monsters)})")

    def validate(self) -> None:
        if not (0 <= self.z <= 15):
            raise ValueError(f"spawn z out of range: {self.z}")


@dataclass
class NPCSpawnData:
    """NPC spawn point."""
    x: int
    y: int
    z: int
    npc_name: str = ""
    direction: int = 0   # 0=South, 1=East, 2=North, 3=West

    def __repr__(self) -> str:
        return f"NPCSpawnData({self.x}, {self.y}, {self.z}, npc={self.npc_name!r})"


@dataclass
class HouseData:
    """A house definition (tiles + name + rent)."""
    id: int
    name: str             = ""
    rent: int             = 0
    town_id: int          = 0
    size: int             = 0
    tile_ids: List[int]   = field(default_factory=list)  # house tile coords (encoded)

    def __repr__(self) -> str:
        return (f"HouseData(id={self.id}, name={self.name!r}, "
                f"town={self.town_id}, tiles={len(self.tile_ids)})")

    def validate(self) -> None:
        if self.id <= 0:
            raise ValueError(f"house id must be > 0: {self.id}")


@dataclass
class MapData:
    """Top-level map container."""
    width: int            = 2048
    height: int           = 2048
    description: str      = "Generated Map"
    otbm_version: int     = 2
    otb_major_version: int = 2     # OTB major (2 for 7.6–8.x, 3 for 10+)
    otb_minor_version: int = 7     # OTB id
    tiles: List[TileData] = field(default_factory=list)
    towns: List[TownData] = field(default_factory=list)
    waypoints: List[WaypointData] = field(default_factory=list)
    spawns: List[SpawnData] = field(default_factory=list)
    npc_spawns: List[NPCSpawnData] = field(default_factory=list)
    houses: List[HouseData] = field(default_factory=list)

    # External file references (written as attributes on MAP_DATA)
    ext_spawn_file: str   = ""
    ext_house_file: str   = ""
    ext_spawn_npc_file: str = ""

    def __repr__(self) -> str:
        return (f"MapData({self.width}x{self.height}, v{self.otbm_version}, "
                f"tiles={len(self.tiles)}, towns={len(self.towns)}, "
                f"waypoints={len(self.waypoints)}, spawns={len(self.spawns)}, "
                f"houses={len(self.houses)})")

    def validate(self) -> None:
        if not (1 <= self.otbm_version <= 3):
            raise ValueError(f"unsupported OTBM version: {self.otbm_version}")
        if not (0 < self.width <= 0xFFFF):
            raise ValueError(f"width out of range: {self.width}")
        if not (0 < self.height <= 0xFFFF):
            raise ValueError(f"height out of range: {self.height}")
        for t in self.towns:
            t.validate()
        for wp in self.waypoints:
            wp.validate()
        for t in self.tiles:
            t.validate()

    # Convenience builder methods ------------------------------------------

    def add_tile(self, x: int, y: int, z: int, ground_id: int,
                 items: Optional[List[ItemData]] = None,
                 flags: TileFlag = TileFlag.NONE,
                 house_id: int = 0) -> "TileData":
        """Create and append a tile, returning it for chaining."""
        tile = TileData(x=x, y=y, z=z, ground_id=ground_id,
                        items=items or [], flags=flags, house_id=house_id)
        self.tiles.append(tile)
        return tile

    def add_item(self, x: int, y: int, z: int, item: ItemData) -> "TileData":
        """Add an item to an existing tile (or create one)."""
        for tile in self.tiles:
            if tile.x == x and tile.y == y and tile.z == z:
                tile.items.append(item)
                return tile
        tile = TileData(x=x, y=y, z=z, items=[item])
        self.tiles.append(tile)
        return tile

    def set_house(self, x: int, y: int, z: int, house_id: int,
                  ground_id: int = 0) -> "TileData":
        """Mark a tile as a house tile."""
        for tile in self.tiles:
            if tile.x == x and tile.y == y and tile.z == z:
                tile.house_id = house_id
                if ground_id and not tile.ground_id:
                    tile.ground_id = ground_id
                return tile
        tile = TileData(x=x, y=y, z=z, ground_id=ground_id, house_id=house_id)
        self.tiles.append(tile)
        return tile

    def add_town(self, town_id: int, name: str,
                 temple: Position) -> "TownData":
        """Add a town and return it."""
        town = TownData(id=town_id, name=name, temple=temple)
        self.towns.append(town)
        return town

    def add_waypoint(self, name: str, pos: Position) -> "WaypointData":
        """Add a waypoint and return it."""
        wp = WaypointData(name=name, pos=pos)
        self.waypoints.append(wp)
        return wp

    def stats(self) -> Dict[str, object]:
        """Return a dict of statistics about the map."""
        total_items = sum(len(t.items) for t in self.tiles)
        ground_tiles = sum(1 for t in self.tiles if t.ground_id > 0)
        house_tiles = sum(1 for t in self.tiles if t.house_id > 0)
        z_levels = len({t.z for t in self.tiles}) if self.tiles else 0

        xs = [t.x for t in self.tiles] if self.tiles else [0]
        ys = [t.y for t in self.tiles] if self.tiles else [0]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)

        return {
            "tiles": len(self.tiles),
            "ground_tiles": ground_tiles,
            "total_items": total_items,
            "house_tiles": house_tiles,
            "towns": len(self.towns),
            "waypoints": len(self.waypoints),
            "spawns": len(self.spawns),
            "npc_spawns": len(self.npc_spawns),
            "houses": len(self.houses),
            "z_levels": z_levels,
            "x_range": f"{min_x}–{max_x}",
            "y_range": f"{min_y}–{max_y}",
            "area_coverage": (max_x - min_x + 1) * (max_y - min_y + 1) if self.tiles else 0,
        }
