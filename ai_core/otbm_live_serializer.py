"""OTBM Live Serializer — Serialize MapData tiles for RME Live Protocol.

The Live protocol uses PACKET_CHANGE_LIST which contains OTBM binary tile nodes.
The format differs from a full OTBM file: it's just a flat list of tile nodes
(with x, y, z coordinates), wrapped in an OTBM node structure.

Wire format for PACKET_CHANGE_LIST:
  The server reads it with parseReceiveChanges which:
  1. Reads a string containing OTBM node data (minus the first START_NODE byte)
  2. Parses each child node as a tile (OTBM_TILE or OTBM_HOUSETILE)

So we need to write tiles as:
  [root START_NODE (0xFE)]
    [tile1 START_NODE (0xFE)]
      [OTBM_TILE byte]
      [x u16][y u16][z u8]
      [attributes...]
    [tile1 END_NODE (0xFF)]
    [tile2 START_NODE (0xFE)]
    ...
  [root END_NODE (0xFF)]

  Then we strip the leading 0xFE (the server adds it back).
"""

import struct
from typing import List, Optional, Tuple
from dataclasses import dataclass

# OTBM constants
NODE_START = 0xFE
NODE_END = 0xFF
ESCAPE_BYTE = 0xFD

OTBM_TILE = 0x02
OTBM_HOUSETILE = 0x03
OTBM_ATTR_TILE_FLAGS = 0x01
OTBM_ATTR_ITEM = 0x02
OTBM_ITEM = 0x01


class OTBMLiveWriter:
    """Serialize tiles for the RME Live protocol PACKET_CHANGE_LIST."""

    def __init__(self):
        self.buffer = bytearray()
        self.tiles_written = 0

    def _write_byte(self, b: int):
        if b == NODE_START or b == NODE_END or b == ESCAPE_BYTE:
            self.buffer.append(ESCAPE_BYTE)
        self.buffer.append(b)

    def _write_u16(self, value: int):
        self._write_byte(value & 0xFF)
        self._write_byte((value >> 8) & 0xFF)

    def _write_u32(self, value: int):
        self._write_byte(value & 0xFF)
        self._write_byte((value >> 8) & 0xFF)
        self._write_byte((value >> 16) & 0xFF)
        self._write_byte((value >> 24) & 0xFF)

    def add_root_node(self):
        """Start root node."""
        self.buffer.append(NODE_START)

    def end_root_node(self):
        """End root node."""
        self.buffer.append(NODE_END)

    def add_tile(self, x: int, y: int, z: int, ground_id: Optional[int] = None,
                 items: Optional[List[int]] = None, flags: int = 0,
                 house_id: Optional[int] = None):
        """Add a tile node.

        Args:
            x, y, z: Tile position
            ground_id: Ground item ID (optional)
            items: List of item IDs to place on tile (optional)
            flags: Tile flags (bitfield)
            house_id: House ID if this is a house tile (optional)
        """
        items = items or []

        # Start tile node
        self.buffer.append(NODE_START)

        if house_id is not None:
            self._write_byte(OTBM_HOUSETILE)
        else:
            self._write_byte(OTBM_TILE)

        # Position (always included in live tile nodes)
        self._write_u16(x)
        self._write_u16(y)
        self._write_byte(z)

        # House ID
        if house_id is not None:
            self._write_u32(house_id)

        # Tile flags
        if flags:
            self._write_byte(OTBM_ATTR_TILE_FLAGS)
            self._write_u32(flags)

        # Ground item (compact format: ATTR_ITEM + item_id u16)
        if ground_id is not None:
            self._write_byte(OTBM_ATTR_ITEM)
            self._write_u16(ground_id)

        # Other items (as child nodes: OTBM_ITEM + item_id u16)
        for item_id in items:
            if item_id != ground_id:  # Don't duplicate ground
                self.buffer.append(NODE_START)
                self._write_byte(OTBM_ITEM)
                self._write_u16(item_id)
                self.buffer.append(NODE_END)

        # End tile node
        self.buffer.append(NODE_END)
        self.tiles_written += 1

    def add_tiles_from_map_data(self, map_data) -> int:
        """Add all tiles from a MapData object.

        Args:
            map_data: MapData from ai_core.models

        Returns:
            Number of tiles written
        """
        if hasattr(map_data, 'tiles') and isinstance(map_data.tiles, dict):
            for key, tile in map_data.tiles.items():
                if isinstance(key, tuple):
                    x, y, z = key
                elif hasattr(tile, 'x'):
                    x, y, z = tile.x, tile.y, tile.z
                else:
                    continue

                ground_id = None
                items = []

                if hasattr(tile, 'ground_id') and tile.ground_id:
                    ground_id = tile.ground_id

                if hasattr(tile, 'items') and tile.items:
                    items = [item.item_id if hasattr(item, 'item_id') else item
                            for item in tile.items]

                house_id = getattr(tile, 'house_id', None)
                flags = getattr(tile, 'flags', 0) or 0

                if ground_id or items or house_id:
                    self.add_tile(x, y, z, ground_id, items, flags, house_id)
        elif hasattr(map_data, 'get_tiles'):
            for tile in map_data.get_tiles():
                x = tile.x
                y = tile.y
                z = tile.z
                ground_id = getattr(tile, 'ground_id', None)
                items = [i.item_id if hasattr(i, 'item_id') else i
                        for i in getattr(tile, 'items', [])]
                house_id = getattr(tile, 'house_id', None)
                flags = getattr(tile, 'flags', 0) or 0
                if ground_id or items or house_id:
                    self.add_tile(x, y, z, ground_id, items, flags, house_id)

        return self.tiles_written

    def get_bytes(self) -> bytes:
        """Get the serialized OTBM node data.

        For the live protocol, we strip the first byte (root NODE_START)
        because the server prepends it back in parseReceiveChanges.
        """
        # The root node should already be written
        # We need to strip the leading 0xFE since the server adds it back
        # But keep everything else including the trailing 0xFF
        if self.buffer and self.buffer[0] == NODE_START:
            return bytes(self.buffer[1:])
        return bytes(self.buffer)

    def get_full_bytes(self) -> bytes:
        """Get full OTBM node data including root start byte."""
        return bytes(self.buffer)

    def reset(self):
        self.buffer = bytearray()
        self.tiles_written = 0

    def __len__(self):
        return len(self.buffer)
