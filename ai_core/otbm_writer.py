"""
OTBM Binary Writer.

Serialises a MapData object into OTBM v2 or v3 binary format.

Features
--------
* Full escaping for every multi-byte field (0xFD prefix for bytes 0xFD–0xFF)
* All tile flags  (PROTECTIONZONE, NOPVPZONE, NOLOGOUTZONE, PVPZONE,
  NOSAVEZONE, HASLIGHT, …)
* All item attributes  (COUNT, CHARGES, DECAY_STATE, DURATION, ACTION_ID,
  UNIQUE_ID, TEXT, DESC, TELE_DEST, HOUSE, CONTAINER, DEPOT,
  WRITTENDATE, WRITTENBY, RUNE_CHARGES, SLEEPERGUID, SLEEPSTART)
* Houses (HOUSETILE nodes)
* Towns with temple positions
* Waypoints
* Spawns (monster + NPC)
* Containers with nested children (recursive)
* Map-level external file references (spawn, house, npc)
"""

from __future__ import annotations

import struct
from typing import BinaryIO, Dict, List, Tuple

from .models import (
    ESCAPE,
    ESCAPE_THRESHOLD,
    ItemData,
    MapData,
    NPCSpawnData,
    NODE_END,
    NODE_START,
    OtbVersion,
    OTB_V2_7,
    OTB_V3_12,
    OTBM_MAGIC,
    Position,
    SpawnData,
    TileData,
    TileFlag,
    TownData,
    WaypointData,
    Attr,
    NodeType,
)


class OTBMWriter:
    """Writes OTBM v2 / v3 binary format.

    Usage::

        writer = OTBMWriter(map_data)
        raw_bytes = writer.write()
        writer.save("path/to/map.otbm")
    """

    def __init__(self, map_data: MapData):
        self.map_data = map_data
        self._buf = bytearray()

    # ------------------------------------------------------------------
    # Low-level write helpers
    # ------------------------------------------------------------------

    def _raw_byte(self, value: int) -> None:
        """Write one unescaped byte (used for control / attribute tags)."""
        self._buf.append(value & 0xFF)

    def _escaped_byte(self, value: int) -> None:
        """Write one byte with proper escaping."""
        value = value & 0xFF
        if value >= ESCAPE_THRESHOLD:
            self._buf.append(ESCAPE)
        self._buf.append(value)

    def _escaped_bytes(self, data: bytes) -> None:
        """Write raw bytes with each byte individually escaped."""
        for b in data:
            self._escaped_byte(b)

    def _u16(self, value: int) -> None:
        """Write uint16 little-endian with per-byte escaping."""
        self._escaped_bytes(struct.pack("<H", value & 0xFFFF))

    def _u32(self, value: int) -> None:
        """Write uint32 little-endian with per-byte escaping."""
        self._escaped_bytes(struct.pack("<I", value & 0xFFFFFFFF))

    def _string(self, s: str) -> None:
        """Write a length-prefixed UTF-8 string (u16 length + escaped bytes)."""
        encoded = s.encode("utf-8")
        self._u16(len(encoded))
        self._escaped_bytes(encoded)

    def _start_node(self, node_type: int) -> None:
        """Write a node start marker (0xFE + type byte)."""
        self._buf.append(NODE_START)
        self._raw_byte(node_type)

    def _end_node(self) -> None:
        """Write a node end marker (0xFF)."""
        self._buf.append(NODE_END)

    # ------------------------------------------------------------------
    # Header
    # ------------------------------------------------------------------

    def _write_header(self) -> None:
        m = self.map_data
        self._u32(m.otbm_version)
        self._u16(m.width)
        self._u16(m.height)
        self._u32(m.otb_major_version)
        self._u32(m.otb_minor_version)

    # ------------------------------------------------------------------
    # Item attribute writing
    # ------------------------------------------------------------------

    def _write_item_attributes(self, item: ItemData) -> None:
        """Write all non-default attributes of an item."""
        if item.count > 0:
            self._raw_byte(Attr.COUNT)
            self._escaped_byte(item.count)
        if item.action_id > 0:
            self._raw_byte(Attr.ACTION_ID)
            self._u16(item.action_id)
        if item.unique_id > 0:
            self._raw_byte(Attr.UNIQUE_ID)
            self._u16(item.unique_id)
        if item.text:
            self._raw_byte(Attr.TEXT)
            self._string(item.text)
        if item.description:
            self._raw_byte(Attr.DESC)
            self._string(item.description)
        if item.charges > 0:
            self._raw_byte(Attr.CHARGES)
            self._u16(item.charges)
        if item.rune_charges > 0:
            self._raw_byte(Attr.RUNE_CHARGES)
            self._escaped_byte(item.rune_charges)
        if item.house_door_id > 0:
            self._raw_byte(Attr.HOUSEDOORID)
            self._escaped_byte(item.house_door_id)
        if item.depot_id > 0:
            self._raw_byte(Attr.DEPOT_ID)
            self._u16(item.depot_id)
        if item.teleport_dest is not None:
            self._raw_byte(Attr.TELE_DEST)
            self._u16(item.teleport_dest.x)
            self._u16(item.teleport_dest.y)
            self._escaped_byte(item.teleport_dest.z)
        if item.duration > 0:
            self._raw_byte(Attr.DURATION)
            self._u32(item.duration)
        if item.decay_state > 0:
            self._raw_byte(Attr.DECAYING_STATE)
            self._escaped_byte(item.decay_state)
        if item.written_date > 0:
            self._raw_byte(Attr.WRITTENDATE)
            self._u32(item.written_date)
        if item.written_by:
            self._raw_byte(Attr.WRITTENBY)
            self._string(item.written_by)
        if item.sleeper_guid > 0:
            self._raw_byte(Attr.SLEEPERGUID)
            self._u32(item.sleeper_guid)
        if item.sleep_start > 0:
            self._raw_byte(Attr.SLEEPSTART)
            self._u32(item.sleep_start)

    def _write_item_compact(self, item: ItemData) -> None:
        """Write compact ground item (ATTR_ITEM + u16 id).  No children."""
        self._raw_byte(Attr.ITEM)
        self._u16(item.id)

    def _write_item_node(self, item: ItemData) -> None:
        """Write full ITEM node with attributes + recursive children."""
        self._start_node(NodeType.ITEM)
        self._u16(item.id)
        self._write_item_attributes(item)
        for child in item.children:
            self._write_item_node(child)
        self._end_node()

    # ------------------------------------------------------------------
    # Tile writing
    # ------------------------------------------------------------------

    def _write_tile(self, tile: TileData, base_x: int, base_y: int) -> None:
        is_house = tile.house_id > 0
        self._start_node(NodeType.HOUSETILE if is_house else NodeType.TILE)

        self._escaped_byte(tile.x - base_x)
        self._escaped_byte(tile.y - base_y)

        if is_house:
            self._u32(tile.house_id)

        if tile.flags != TileFlag.NONE:
            self._raw_byte(Attr.TILE_FLAGS)
            self._u32(int(tile.flags))

        # Ground item — compact
        if tile.ground_id > 0:
            self._write_item_compact(ItemData(id=tile.ground_id))

        # Stacked / container items — full nodes
        for item in tile.items:
            self._write_item_node(item)

        self._end_node()

    # ------------------------------------------------------------------
    # Tile areas  (256×256 chunks per Z)
    # ------------------------------------------------------------------

    def _write_tile_areas(self) -> None:
        areas: Dict[Tuple[int, int, int], List[TileData]] = {}
        for tile in self.map_data.tiles:
            key = (tile.x & 0xFF00, tile.y & 0xFF00, tile.z)
            areas.setdefault(key, []).append(tile)

        for (bx, by, z), tiles in sorted(areas.items()):
            self._start_node(NodeType.TILE_AREA)
            self._u16(bx)
            self._u16(by)
            self._escaped_byte(z)
            for tile in tiles:
                self._write_tile(tile, bx, by)
            self._end_node()

    # ------------------------------------------------------------------
    # Towns
    # ------------------------------------------------------------------

    def _write_towns(self) -> None:
        self._start_node(NodeType.TOWNS)
        for town in self.map_data.towns:
            self._start_node(NodeType.TOWN)
            self._u32(town.id)
            self._string(town.name)
            self._u16(town.temple.x)
            self._u16(town.temple.y)
            self._escaped_byte(town.temple.z)
            self._end_node()
        self._end_node()

    # ------------------------------------------------------------------
    # Waypoints
    # ------------------------------------------------------------------

    def _write_waypoints(self) -> None:
        if not self.map_data.waypoints:
            return
        self._start_node(NodeType.WAYPOINTS)
        for wp in self.map_data.waypoints:
            self._start_node(NodeType.WAYPOINT)
            self._string(wp.name)
            self._u16(wp.pos.x)
            self._u16(wp.pos.y)
            self._escaped_byte(wp.pos.z)
            self._end_node()
        self._end_node()

    # ------------------------------------------------------------------
    # Spawns (monster + NPC)
    # ------------------------------------------------------------------

    def _write_spawns(self) -> None:
        m = self.map_data
        if not m.spawns:
            return
        self._start_node(NodeType.SPAWNS)
        for spawn in m.spawns:
            self._start_node(NodeType.SPAWN_AREA)
            self._u16(spawn.x)
            self._u16(spawn.y)
            self._escaped_byte(spawn.z)
            self._u32(spawn.radius)
            for monster_name, ox, oy in spawn.monsters:
                self._start_node(NodeType.MONSTER)
                self._string(monster_name)
                self._u16(ox & 0xFFFF)
                self._u16(oy & 0xFFFF)
                self._string("")
                self._end_node()
            self._end_node()
        self._end_node()

    def _write_npc_spawns(self) -> None:
        """NPCs encoded as SPAWN_AREA / MONSTER nodes (OTBM convention)."""
        m = self.map_data
        if not m.npc_spawns:
            return
        self._start_node(NodeType.SPAWNS)
        for npc in m.npc_spawns:
            self._start_node(NodeType.SPAWN_AREA)
            self._u16(npc.x)
            self._u16(npc.y)
            self._escaped_byte(npc.z)
            self._u32(1)
            self._start_node(NodeType.MONSTER)
            self._string(npc.npc_name)
            self._u16(0)
            self._u16(0)
            self._string("")
            self._end_node()
            self._end_node()
        self._end_node()

    # ------------------------------------------------------------------
    # Map-level external file attributes
    # ------------------------------------------------------------------

    def _write_ext_files(self) -> None:
        m = self.map_data
        if m.ext_spawn_file:
            self._raw_byte(Attr.EXT_SPAWN_FILE)
            self._string(m.ext_spawn_file)
        if m.ext_house_file:
            self._raw_byte(Attr.EXT_HOUSE_FILE)
            self._string(m.ext_house_file)
        if m.ext_spawn_npc_file:
            self._raw_byte(Attr.EXT_SPAWN_NPC_FILE)
            self._string(m.ext_spawn_npc_file)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def write(self) -> bytes:
        """Serialise the map and return raw bytes."""
        self._buf = bytearray()

        # Magic
        self._buf.extend(OTBM_MAGIC)

        # Root node
        self._start_node(NodeType.ROOTV1)
        self._write_header()

        # MAP_DATA child
        self._start_node(NodeType.MAP_DATA)

        # Description
        self._raw_byte(Attr.DESCRIPTION)
        self._string(self.map_data.description)

        # External file refs
        self._write_ext_files()

        # Content
        self._write_tile_areas()
        self._write_towns()
        self._write_waypoints()
        self._write_spawns()
        self._write_npc_spawns()

        self._end_node()  # MAP_DATA
        self._end_node()  # ROOTV1

        return bytes(self._buf)

    def save(self, path: str) -> int:
        """Write to file, return byte count."""
        data = self.write()
        with open(path, "wb") as f:
            f.write(data)
        return len(data)

    def save_stream(self, f: BinaryIO) -> int:
        """Write to any binary file-like object, return byte count."""
        data = self.write()
        f.write(data)
        return len(data)
