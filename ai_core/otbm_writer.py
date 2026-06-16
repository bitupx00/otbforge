"""
OTBM Binary Writer.

Serialises a MapData object into the OTBM v2 binary format.
"""

from __future__ import annotations

import struct
from typing import BinaryIO, Dict, List, Tuple

from .otbm_types import (
    ESCAPE,
    ESCAPE_THRESHOLD,
    NODE_END,
    NODE_START,
    OTBM_MAGIC,
    Attr,
    NodeType,
    TileFlags,
    ItemData,
    MapData,
    NPCSpawnData,
    Position,
    SpawnData,
    TileData,
    TownData,
    WaypointData,
)


class OTBMWriter:
    """Writes OTBM v2 binary format."""

    def __init__(self, map_data: MapData):
        self.map_data = map_data
        self._buf = bytearray()

    # ------------------------------------------------------------------
    # Low-level write helpers
    # ------------------------------------------------------------------

    def _raw_byte(self, value: int) -> None:
        self._buf.append(value & 0xFF)

    def _escaped_byte(self, value: int) -> None:
        value = value & 0xFF
        if value >= ESCAPE_THRESHOLD:
            self._buf.append(ESCAPE)
        self._buf.append(value)

    def _escaped_bytes(self, data: bytes) -> None:
        for b in data:
            self._escaped_byte(b)

    def _u16(self, value: int) -> None:
        self._escaped_bytes(struct.pack("<H", value))

    def _u32(self, value: int) -> None:
        self._escaped_bytes(struct.pack("<I", value))

    def _string(self, s: str) -> None:
        encoded = s.encode("utf-8")
        self._u16(len(encoded))
        self._escaped_bytes(encoded)

    def _start_node(self, node_type: int) -> None:
        self._buf.append(NODE_START)
        self._raw_byte(node_type)

    def _end_node(self) -> None:
        self._buf.append(NODE_END)

    # ------------------------------------------------------------------
    # High-level writers
    # ------------------------------------------------------------------

    def _write_header(self) -> None:
        m = self.map_data
        self._u32(m.otbm_version)
        self._u16(m.width)
        self._u16(m.height)
        self._u32(m.otb_major_version)
        self._u32(m.otb_minor_version)

    def _write_item_attributes(self, item: ItemData) -> None:
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

    def _write_item_compact(self, item: ItemData) -> None:
        """Compact item on tile (ATTR_ITEM u16 id). No children."""
        self._raw_byte(Attr.ITEM)
        self._u16(item.id)

    def _write_item_node(self, item: ItemData) -> None:
        """Full item node with attributes and children (containers)."""
        self._start_node(NodeType.ITEM)
        self._u16(item.id)
        self._write_item_attributes(item)
        for child in item.children:
            self._write_item_node(child)
        self._end_node()

    def _write_tile(self, tile: TileData, base_x: int, base_y: int) -> None:
        is_house = tile.house_id > 0
        self._start_node(NodeType.HOUSETILE if is_house else NodeType.TILE)
        self._escaped_byte(tile.x - base_x)
        self._escaped_byte(tile.y - base_y)
        if is_house:
            self._u32(tile.house_id)
        if tile.flags != TileFlags.NONE:
            self._raw_byte(Attr.TILE_FLAGS)
            self._u32(tile.flags)

        # Ground item — compact format
        if tile.ground_id > 0:
            ground = ItemData(id=tile.ground_id)
            self._write_item_compact(ground)

        # Stacked items as full ITEM nodes
        for item in tile.items:
            self._write_item_node(item)

        self._end_node()

    def _write_tile_areas(self) -> None:
        m = self.map_data
        # Group tiles into 256×256 chunks per Z
        areas: Dict[Tuple[int, int, int], List[TileData]] = {}
        for tile in m.tiles:
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

    def _write_towns(self) -> None:
        m = self.map_data
        self._start_node(NodeType.TOWNS)
        for town in m.towns:
            self._start_node(NodeType.TOWN)
            self._u32(town.id)
            self._string(town.name)
            self._u16(town.temple.x)
            self._u16(town.temple.y)
            self._escaped_byte(town.temple.z)
            self._end_node()
        self._end_node()

    def _write_waypoints(self) -> None:
        m = self.map_data
        if not m.waypoints:
            return
        self._start_node(NodeType.WAYPOINTS)
        for wp in m.waypoints:
            self._start_node(NodeType.WAYPOINT)
            self._string(wp.name)
            self._u16(wp.pos.x)
            self._u16(wp.pos.y)
            self._escaped_byte(wp.pos.z)
            self._end_node()
        self._end_node()

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
                self._u16(ox)
                self._u16(oy)
                self._string("")  # spawn file (empty)
                self._end_node()
            self._end_node()
        self._end_node()

    def _write_npc_spawns(self) -> None:
        """Write NPC spawns as SPAWN_AREA / MONSTER nodes (convention).

        NPCs in OTBM are encoded using the same SPAWN_AREA structure
        with the NPC name as the monster name and an empty spawn file.
        """
        m = self.map_data
        if not m.npc_spawns:
            return
        self._start_node(NodeType.SPAWNS)
        for npc in m.npc_spawns:
            self._start_node(NodeType.SPAWN_AREA)
            self._u16(npc.x)
            self._u16(npc.y)
            self._escaped_byte(npc.z)
            self._u32(1)  # radius
            self._start_node(NodeType.MONSTER)
            self._string(npc.npc_name)
            self._u16(0)
            self._u16(0)
            self._string("")
            self._end_node()
            self._end_node()
        self._end_node()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def write(self) -> bytes:
        """Serialise the map and return raw bytes."""
        self._buf = bytearray()
        self._buf.extend(OTBM_MAGIC)

        self._start_node(NodeType.ROOTV1)
        self._write_header()

        # MAP_DATA child
        self._start_node(NodeType.MAP_DATA)
        self._raw_byte(Attr.DESCRIPTION)
        self._string(self.map_data.description)

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
