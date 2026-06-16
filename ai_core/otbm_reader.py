"""
OTBM Binary Reader.

Parses an OTBM v2 binary file/stream and reconstructs a MapData object.
"""

from __future__ import annotations

import struct
from typing import List, Optional, Tuple

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

# Sentinel returned when reading past the node boundary
_NODE_END_SENTINEL = object()


class OTBMReader:
    """Reads OTBM v2 binary format."""

    def __init__(self, data: bytes):
        self._data = data
        self._pos = 0

    # ------------------------------------------------------------------
    # Low-level read helpers
    # ------------------------------------------------------------------

    def _raw_byte(self) -> int:
        b = self._data[self._pos]
        self._pos += 1
        return b

    def _eof(self) -> bool:
        return self._pos >= len(self._data)

    def _peek(self) -> int:
        return self._data[self._pos]

    def _escaped_byte(self):
        """Read a potentially-escaped byte. Returns None at EOF, or _NODE_END_SENTINEL at node boundary."""
        if self._eof():
            return None
        b = self._raw_byte()
        if b == ESCAPE:
            if self._eof():
                return None
            return self._raw_byte()
        if b == NODE_END:
            return _NODE_END_SENTINEL
        return b

    def _u16(self):
        lo = self._escaped_byte()
        if lo is _NODE_END_SENTINEL or lo is None:
            return _NODE_END_SENTINEL
        hi = self._escaped_byte()
        if hi is _NODE_END_SENTINEL or hi is None:
            return _NODE_END_SENTINEL
        return (hi << 8) | lo

    def _u32(self):
        b0 = self._escaped_byte()
        if b0 is _NODE_END_SENTINEL or b0 is None:
            return _NODE_END_SENTINEL
        b1 = self._escaped_byte()
        if b1 is _NODE_END_SENTINEL or b1 is None:
            return _NODE_END_SENTINEL
        b2 = self._escaped_byte()
        if b2 is _NODE_END_SENTINEL or b2 is None:
            return _NODE_END_SENTINEL
        b3 = self._escaped_byte()
        if b3 is _NODE_END_SENTINEL or b3 is None:
            return _NODE_END_SENTINEL
        return (b3 << 24) | (b2 << 16) | (b1 << 8) | b0

    def _string(self) -> Optional[str]:
        length = self._u16()
        if length is _NODE_END_SENTINEL:
            return None
        buf = []
        for _ in range(length):
            ch = self._escaped_byte()
            if ch is _NODE_END_SENTINEL or ch is None:
                return None
            buf.append(ch)
        return bytes(buf).decode("utf-8", errors="replace")

    # ------------------------------------------------------------------
    # Node navigation
    # ------------------------------------------------------------------

    def _enter_node(self) -> Optional[int]:
        """Expect NODE_START + type byte. Returns node type or None."""
        if self._eof():
            return None
        b = self._raw_byte()
        if b != NODE_START:
            return None
        return self._raw_byte()

    def _at_node_end(self) -> bool:
        if self._eof():
            return True
        return self._peek() == NODE_END

    def _skip_node_end(self) -> None:
        """Consume a NODE_END byte if we're at one."""
        if not self._eof() and self._peek() == NODE_END:
            self._raw_byte()

    # ------------------------------------------------------------------
    # Item reading
    # ------------------------------------------------------------------

    def _read_item_compact(self) -> Optional[ItemData]:
        """Read a compact item (u16 id after ATTR_ITEM attribute)."""
        item_id = self._u16()
        if item_id is _NODE_END_SENTINEL:
            return None
        return ItemData(id=item_id)

    def _read_item_node(self) -> Optional[ItemData]:
        """Read a full ITEM node (type byte already consumed by caller).

        Reads attributes and child ITEM nodes. Leaves cursor at NODE_END.
        """
        item_id = self._u16()
        if item_id is _NODE_END_SENTINEL:
            return None
        item = ItemData(id=item_id)
        # Read attributes until node boundary or child node
        while not self._at_node_end() and not self._eof():
            if self._peek() == NODE_START:
                break  # child node begins; stop reading attributes
            attr_byte = self._escaped_byte()
            if attr_byte is _NODE_END_SENTINEL or attr_byte is None:
                break
            self._read_item_attr(item, attr_byte)
        # Read child ITEM nodes (containers)
        while not self._at_node_end() and not self._eof():
            child_type = self._enter_node()
            if child_type is None:
                break
            if child_type == NodeType.ITEM:
                child = self._read_item_node()
                if child is not None:
                    item.children.append(child)
                self._skip_node_end()  # consume child ITEM node end
            else:
                break
        return item

    def _read_item_attr(self, item: ItemData, attr: int) -> None:
        if attr == Attr.COUNT:
            v = self._escaped_byte()
            if v is not _NODE_END_SENTINEL and v is not None:
                item.count = v
        elif attr == Attr.ACTION_ID:
            v = self._u16()
            if v is not _NODE_END_SENTINEL:
                item.action_id = v
        elif attr == Attr.UNIQUE_ID:
            v = self._u16()
            if v is not _NODE_END_SENTINEL:
                item.unique_id = v
        elif attr == Attr.TEXT:
            v = self._string()
            if v is not None:
                item.text = v
        elif attr == Attr.DESC:
            v = self._string()
            if v is not None:
                item.description = v
        elif attr == Attr.CHARGES:
            v = self._u16()
            if v is not _NODE_END_SENTINEL:
                item.charges = v
        elif attr == Attr.HOUSEDOORID:
            v = self._escaped_byte()
            if v is not _NODE_END_SENTINEL and v is not None:
                item.house_door_id = v
        elif attr == Attr.DEPOT_ID:
            v = self._u16()
            if v is not _NODE_END_SENTINEL:
                item.depot_id = v
        elif attr == Attr.TELE_DEST:
            x = self._u16()
            y = self._u16()
            z = self._escaped_byte()
            if (x is not _NODE_END_SENTINEL
                    and y is not _NODE_END_SENTINEL
                    and z is not _NODE_END_SENTINEL):
                item.teleport_dest = Position(x=x, y=y, z=z)
        # else: unknown attr — no generic skip possible; stop reading attrs

    # ------------------------------------------------------------------
    # Tile reading
    # ------------------------------------------------------------------

    def _read_tile(self, base_x: int, base_y: int, node_type: int) -> Optional[TileData]:
        """Read tile content (type byte already consumed). Leaves cursor at NODE_END."""
        x_off = self._escaped_byte()
        if x_off is _NODE_END_SENTINEL or x_off is None:
            return None
        y_off = self._escaped_byte()
        if y_off is _NODE_END_SENTINEL or y_off is None:
            return None

        house_id = 0
        if node_type == NodeType.HOUSETILE:
            hid = self._u32()
            if hid is _NODE_END_SENTINEL:
                return None
            house_id = hid

        tile = TileData(x=base_x + x_off, y=base_y + y_off, z=0, house_id=house_id)

        # Read tile-level attributes
        while not self._at_node_end() and not self._eof():
            if self._peek() == NODE_START:
                break  # child ITEM node begins; stop reading attributes
            attr_byte = self._escaped_byte()
            if attr_byte is _NODE_END_SENTINEL or attr_byte is None:
                break
            if attr_byte == Attr.TILE_FLAGS:
                v = self._u32()
                if v is not _NODE_END_SENTINEL:
                    tile.flags = v
            elif attr_byte == Attr.ITEM:
                ground = self._read_item_compact()
                if ground is not None:
                    tile.ground_id = ground.id
            else:
                break  # unknown tile attr

        # Read child ITEM nodes (stacked items)
        while not self._at_node_end() and not self._eof():
            child_type = self._enter_node()
            if child_type is None:
                break
            if child_type == NodeType.ITEM:
                item = self._read_item_node()
                if item is not None:
                    tile.items.append(item)
                self._skip_node_end()  # consume ITEM node end
            else:
                break

        return tile

    def _read_tile_area(self) -> Optional[List[TileData]]:
        """Read TILE_AREA children. Leaves cursor at TILE_AREA's NODE_END."""
        bx = self._u16()
        if bx is _NODE_END_SENTINEL:
            return None
        by = self._u16()
        if by is _NODE_END_SENTINEL:
            return None
        bz = self._escaped_byte()
        if bz is _NODE_END_SENTINEL or bz is None:
            return None

        tiles: List[TileData] = []
        while not self._at_node_end() and not self._eof():
            tile_type = self._enter_node()
            if tile_type is None:
                break
            if tile_type in (NodeType.TILE, NodeType.HOUSETILE):
                tile = self._read_tile(bx, by, tile_type)
                if tile is not None:
                    tile.z = bz
                    tiles.append(tile)
                self._skip_node_end()  # consume tile NODE_END
            else:
                # Unexpected node — skip to its end
                while not self._at_node_end() and not self._eof():
                    self._escaped_byte()
                self._skip_node_end()
        return tiles

    # ------------------------------------------------------------------
    # Towns
    # ------------------------------------------------------------------

    def _read_towns(self) -> List[TownData]:
        """Read TOWNS children. Leaves cursor at TOWNS's NODE_END."""
        towns: List[TownData] = []
        while not self._at_node_end() and not self._eof():
            t = self._enter_node()
            if t is None:
                break
            if t != NodeType.TOWN:
                # skip unexpected
                while not self._at_node_end() and not self._eof():
                    self._escaped_byte()
                self._skip_node_end()
                continue
            tid = self._u32()
            if tid is _NODE_END_SENTINEL:
                break
            tname = self._string()
            if tname is None:
                break
            tx = self._u16()
            if tx is _NODE_END_SENTINEL:
                break
            ty = self._u16()
            if ty is _NODE_END_SENTINEL:
                break
            tz = self._escaped_byte()
            if tz is _NODE_END_SENTINEL or tz is None:
                break
            towns.append(TownData(id=tid, name=tname, temple=Position(x=tx, y=ty, z=tz)))
            self._skip_node_end()  # consume TOWN NODE_END
        return towns

    # ------------------------------------------------------------------
    # Waypoints
    # ------------------------------------------------------------------

    def _read_waypoints(self) -> List[WaypointData]:
        """Read WAYPOINTS children. Leaves cursor at WAYPOINTS's NODE_END."""
        wps: List[WaypointData] = []
        while not self._at_node_end() and not self._eof():
            t = self._enter_node()
            if t is None:
                break
            if t != NodeType.WAYPOINT:
                while not self._at_node_end() and not self._eof():
                    self._escaped_byte()
                self._skip_node_end()
                continue
            name = self._string()
            if name is None:
                break
            wx = self._u16()
            if wx is _NODE_END_SENTINEL:
                break
            wy = self._u16()
            if wy is _NODE_END_SENTINEL:
                break
            wz = self._escaped_byte()
            if wz is _NODE_END_SENTINEL or wz is None:
                break
            wps.append(WaypointData(name=name, pos=Position(x=wx, y=wy, z=wz)))
            self._skip_node_end()
        return wps

    # ------------------------------------------------------------------
    # Spawns
    # ------------------------------------------------------------------

    def _read_spawns(self) -> List[SpawnData]:
        """Read SPAWNS children. Leaves cursor at SPAWNS's NODE_END."""
        spawns: List[SpawnData] = []
        while not self._at_node_end() and not self._eof():
            t = self._enter_node()
            if t is None:
                break
            if t != NodeType.SPAWN_AREA:
                while not self._at_node_end() and not self._eof():
                    self._escaped_byte()
                self._skip_node_end()
                continue
            sx = self._u16()
            if sx is _NODE_END_SENTINEL:
                break
            sy = self._u16()
            if sy is _NODE_END_SENTINEL:
                break
            sz = self._escaped_byte()
            if sz is _NODE_END_SENTINEL or sz is None:
                break
            sr = self._u32()
            if sr is _NODE_END_SENTINEL:
                break
            monsters: List[Tuple[str, int, int]] = []
            while not self._at_node_end() and not self._eof():
                mt = self._enter_node()
                if mt is None:
                    break
                if mt != NodeType.MONSTER:
                    while not self._at_node_end() and not self._eof():
                        self._escaped_byte()
                    self._skip_node_end()
                    continue
                mname = self._string()
                if mname is None:
                    break
                mox = self._u16()
                if mox is _NODE_END_SENTINEL:
                    break
                moy = self._u16()
                if moy is _NODE_END_SENTINEL:
                    break
                _spawn_file = self._string()  # ignored
                monsters.append((mname, mox, moy))
                self._skip_node_end()  # consume MONSTER NODE_END
            spawns.append(SpawnData(x=sx, y=sy, z=sz, radius=sr, monsters=monsters))
            self._skip_node_end()  # consume SPAWN_AREA NODE_END
        return spawns

    # ------------------------------------------------------------------
    # Map data child dispatcher
    # ------------------------------------------------------------------

    def _read_map_data_children(self, map_data: MapData) -> None:
        """Read all children of the MAP_DATA node."""
        while not self._at_node_end() and not self._eof():
            next_byte = self._peek()
            if next_byte != NODE_START:
                # Raw attribute byte (DESCRIPTION, EXT_SPAWN_FILE, etc.)
                attr_byte = self._escaped_byte()
                if attr_byte is _NODE_END_SENTINEL or attr_byte is None:
                    break
                if attr_byte == Attr.DESCRIPTION:
                    v = self._string()
                    if v is not None:
                        map_data.description = v
                elif attr_byte == Attr.EXT_SPAWN_FILE:
                    self._string()  # skip
                elif attr_byte == Attr.EXT_HOUSE_FILE:
                    self._string()  # skip
                continue

            # Child node
            child_type = self._enter_node()
            if child_type is None:
                break

            if child_type == NodeType.TILE_AREA:
                tiles = self._read_tile_area()
                if tiles:
                    map_data.tiles.extend(tiles)
            elif child_type == NodeType.TOWNS:
                map_data.towns = self._read_towns()
            elif child_type == NodeType.WAYPOINTS:
                map_data.waypoints = self._read_waypoints()
            elif child_type == NodeType.SPAWNS:
                map_data.spawns = self._read_spawns()
            else:
                # Unknown child — skip to its NODE_END
                while not self._at_node_end() and not self._eof():
                    self._escaped_byte()

            self._skip_node_end()  # consume child node's NODE_END

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def read(self) -> MapData:
        """Parse the full OTBM stream and return a MapData."""
        # Magic
        if self._data[:4] != OTBM_MAGIC:
            raise ValueError("Invalid OTBM magic bytes")
        self._pos = 4

        # Root node
        root_type = self._enter_node()
        if root_type != NodeType.ROOTV1:
            raise ValueError(f"Expected ROOTV1 node, got {root_type}")

        map_data = MapData()

        # Header
        v = self._u32()
        if v is _NODE_END_SENTINEL:
            raise ValueError("Missing version")
        map_data.otbm_version = v

        w = self._u16()
        if w is _NODE_END_SENTINEL:
            raise ValueError("Missing width")
        map_data.width = w

        h = self._u16()
        if h is _NODE_END_SENTINEL:
            raise ValueError("Missing height")
        map_data.height = h

        major = self._u32()
        if major is _NODE_END_SENTINEL:
            raise ValueError("Missing OTB major version")
        map_data.otb_major_version = major

        minor = self._u32()
        if minor is _NODE_END_SENTINEL:
            raise ValueError("Missing OTB minor version")
        map_data.otb_minor_version = minor

        # MAP_DATA child
        md_type = self._enter_node()
        if md_type != NodeType.MAP_DATA:
            raise ValueError(f"Expected MAP_DATA node, got {md_type}")

        self._read_map_data_children(map_data)

        return map_data

    @classmethod
    def from_file(cls, path: str) -> MapData:
        with open(path, "rb") as f:
            return cls(f.read()).read()
