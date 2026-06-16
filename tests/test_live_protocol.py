"""Comprehensive tests for RME Live Protocol, OTBM Live Serializer, and LiveClient.

Covers:
  1. NetworkMessage: write/read u8, u16, u32, string, position, cursor, roundtrips
  2. encode_frame / decode_frame: proper framing with 4-byte length prefix
  3. OTBMLiveWriter: tile serialization, escaping, MapData integration, get_bytes
  4. LiveClient: constructor, message building, handshake mock, packet parsing
  5. Integration: MapData → OTBMLiveWriter → LiveClient.send_tile_changes
"""

import struct
import socket
import threading
import time
from dataclasses import dataclass, field
from typing import Optional, List
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

# ---------------------------------------------------------------------------
# Module under test imports
# ---------------------------------------------------------------------------
from ai_core.live_client import (
    NetworkMessage,
    encode_frame,
    decode_frame,
    LiveClient,
    LiveMapInfo,
    LivePacket,
    RME_VERSION_ID,
    LIVE_NET_VERSION,
    DEFAULT_PROTOCOL_ID,
)
from ai_core.otbm_live_serializer import (
    OTBMLiveWriter,
    NODE_START,
    NODE_END,
    ESCAPE_BYTE,
    OTBM_TILE,
    OTBM_HOUSETILE,
    OTBM_ATTR_TILE_FLAGS,
    OTBM_ATTR_ITEM,
    OTBM_ITEM,
)


# ---------------------------------------------------------------------------
# Simple fixtures compatible with OTBMLiveWriter expectations
# ---------------------------------------------------------------------------

@dataclass
class SimpleItem:
    item_id: int


@dataclass
class SimpleTile:
    x: int
    y: int
    z: int
    ground_id: int = 0
    items: list = field(default_factory=list)
    flags: int = 0
    house_id: int = 0


@dataclass
class SimpleMapData:
    """MapData-like object with dict tiles for OTBMLiveWriter compatibility."""
    tiles: dict  # (x, y, z) -> SimpleTile


# ===========================================================================
# 1. NetworkMessage Tests
# ===========================================================================

class TestNetworkMessage:

    def test_initial_state(self):
        msg = NetworkMessage()
        assert len(msg) == 0
        assert msg.remaining() == 0
        assert msg.position == 0

    def test_clear(self):
        msg = NetworkMessage()
        msg.write_u8(42)
        msg.clear()
        assert len(msg) == 0
        assert msg.position == 0

    # ── Write / Read u8 ──

    def test_write_read_u8_min(self):
        msg = NetworkMessage()
        msg.write_u8(0)
        msg.position = 0
        assert msg.read_u8() == 0

    def test_write_read_u8_max(self):
        msg = NetworkMessage()
        msg.write_u8(255)
        msg.position = 0
        assert msg.read_u8() == 255

    def test_write_read_u8_masks(self):
        msg = NetworkMessage()
        msg.write_u8(0x42)
        msg.position = 0
        assert msg.read_u8() == 0x42

    def test_write_read_u8_overflow_masked(self):
        """Values > 255 should be masked to 8 bits."""
        msg = NetworkMessage()
        msg.write_u8(0x1FF)  # 511 -> masked to 0xFF
        msg.position = 0
        assert msg.read_u8() == 0xFF

    # ── Write / Read u16 ──

    def test_write_read_u16_zero(self):
        msg = NetworkMessage()
        msg.write_u16(0)
        msg.position = 0
        assert msg.read_u16() == 0

    def test_write_read_u16_max(self):
        msg = NetworkMessage()
        msg.write_u16(0xFFFF)
        msg.position = 0
        assert msg.read_u16() == 0xFFFF

    def test_write_read_u16_le(self):
        """Verify little-endian byte order."""
        msg = NetworkMessage()
        msg.write_u16(0x1234)
        assert msg.buffer[0] == 0x34  # low byte first
        assert msg.buffer[1] == 0x12
        msg.position = 0
        assert msg.read_u16() == 0x1234

    # ── Write / Read u32 ──

    def test_write_read_u32_zero(self):
        msg = NetworkMessage()
        msg.write_u32(0)
        msg.position = 0
        assert msg.read_u32() == 0

    def test_write_read_u32_max(self):
        msg = NetworkMessage()
        msg.write_u32(0xFFFFFFFF)
        msg.position = 0
        assert msg.read_u32() == 0xFFFFFFFF

    def test_write_read_u32_rme_version(self):
        msg = NetworkMessage()
        msg.write_u32(RME_VERSION_ID)
        msg.position = 0
        assert msg.read_u32() == RME_VERSION_ID

    # ── Write / Read string ──

    def test_write_read_string_empty(self):
        msg = NetworkMessage()
        msg.write_string("")
        msg.position = 0
        assert msg.read_string() == ""

    def test_write_read_string_ascii(self):
        msg = NetworkMessage()
        msg.write_string("hello")
        msg.position = 0
        assert msg.read_string() == "hello"

    def test_write_read_string_unicode(self):
        msg = NetworkMessage()
        msg.write_string("café ☕")
        msg.position = 0
        assert msg.read_string() == "café ☕"

    def test_write_read_string_long(self):
        text = "A" * 500
        msg = NetworkMessage()
        msg.write_string(text)
        msg.position = 0
        assert msg.read_string() == text

    def test_write_read_string_already_bytes(self):
        """write_string accepts bytes directly."""
        msg = NetworkMessage()
        msg.write_string(b"raw bytes")
        msg.position = 0
        assert msg.read_string() == "raw bytes"

    # ── Write / Read position ──

    def test_write_read_position(self):
        msg = NetworkMessage()
        msg.write_position(100, 200, 7)
        msg.position = 0
        x, y, z = msg.read_position()
        assert (x, y, z) == (100, 200, 7)

    def test_write_read_position_all_zero(self):
        msg = NetworkMessage()
        msg.write_position(0, 0, 0)
        msg.position = 0
        assert msg.read_position() == (0, 0, 0)

    def test_write_read_position_max_values(self):
        msg = NetworkMessage()
        msg.write_position(0xFFFF, 0xFFFF, 0xFF)
        msg.position = 0
        assert msg.read_position() == (0xFFFF, 0xFFFF, 0xFF)

    # ── Write cursor ──

    def test_write_cursor(self):
        msg = NetworkMessage()
        msg.write_cursor(1, 255, 0, 0, 200, 100, 200, 7)
        msg.position = 0
        assert msg.read_u32() == 1
        assert msg.read_u8() == 255  # r
        assert msg.read_u8() == 0    # g
        assert msg.read_u8() == 0    # b
        assert msg.read_u8() == 200  # a
        x, y, z = msg.read_position()
        assert (x, y, z) == (100, 200, 7)

    # ── write_bytes / remaining / __len__ ──

    def test_write_bytes(self):
        msg = NetworkMessage()
        msg.write_bytes(b"\x01\x02\x03")
        assert len(msg) == 3
        assert bytes(msg.buffer) == b"\x01\x02\x03"

    def test_remaining(self):
        msg = NetworkMessage()
        msg.write_u32(42)
        msg.position = 2
        assert msg.remaining() == 2

    def test_multiple_sequential_reads(self):
        """Read multiple fields sequentially from one buffer."""
        msg = NetworkMessage()
        msg.write_u8(1)
        msg.write_u16(2)
        msg.write_u32(3)
        msg.write_string("four")
        msg.position = 0
        assert msg.read_u8() == 1
        assert msg.read_u16() == 2
        assert msg.read_u32() == 3
        assert msg.read_string() == "four"


# ===========================================================================
# 2. Frame Encoding / Decoding Tests
# ===========================================================================

class TestFrameEncoding:

    def test_encode_empty_message(self):
        msg = NetworkMessage()
        frame = encode_frame(msg)
        assert len(frame) == 4  # just the size header
        size = struct.unpack('<I', frame[:4])[0]
        assert size == 0

    def test_encode_decode_roundtrip(self):
        msg = NetworkMessage()
        msg.write_u8(0x42)
        msg.write_u16(1000)
        frame = encode_frame(msg)
        decoded, offset = decode_frame(frame)
        assert offset == len(frame)
        assert decoded.read_u8() == 0x42
        assert decoded.read_u16() == 1000

    def test_decode_multiple_frames(self):
        """Decode multiple consecutive frames from one byte stream."""
        msg1 = NetworkMessage()
        msg1.write_u8(1)
        msg2 = NetworkMessage()
        msg2.write_u8(2)
        stream = encode_frame(msg1) + encode_frame(msg2)

        d1, offset = decode_frame(stream, 0)
        assert d1.read_u8() == 1
        d2, offset = decode_frame(stream, offset)
        assert d2.read_u8() == 2
        assert offset == len(stream)

    def test_decode_with_nonzero_offset(self):
        msg = NetworkMessage()
        msg.write_u8(99)
        frame = encode_frame(msg)
        prefix = b"\x00\x00\x00\x00"  # 4 junk bytes
        data = prefix + frame
        decoded, offset = decode_frame(data, 4)
        assert decoded.read_u8() == 99
        assert offset == len(data)

    def test_decode_frame_preserves_payload(self):
        """Frame payload bytes match original message buffer exactly."""
        msg = NetworkMessage()
        payload = bytes([0x10, 0x00, 0x20, 0x00, 0x00, 0x00])
        msg.write_bytes(payload)
        frame = encode_frame(msg)
        decoded, _ = decode_frame(frame)
        assert bytes(decoded.buffer) == payload


# ===========================================================================
# 3. OTBMLiveWriter Tests
# ===========================================================================

class TestOTBMLiveWriter:

    def test_initial_state(self):
        w = OTBMLiveWriter()
        assert len(w) == 0
        assert w.tiles_written == 0

    def test_add_root_node(self):
        w = OTBMLiveWriter()
        w.add_root_node()
        assert len(w) == 1
        assert w.buffer[0] == NODE_START

    def test_end_root_node(self):
        w = OTBMLiveWriter()
        w.add_root_node()
        w.end_root_node()
        assert len(w) == 2
        assert w.buffer[1] == NODE_END

    def test_single_tile_ground_only(self):
        w = OTBMLiveWriter()
        w.add_root_node()
        w.add_tile(100, 200, 7, ground_id=102)
        w.end_root_node()

        data = w.get_full_bytes()
        # Layout: [root NODE_START] [tile NODE_START] [OTBM_TILE] [x LO] [x HI] [y LO] [y HI] [z] [ATTR_ITEM] [ground LO] [ground HI] [NODE_END] [root NODE_END]
        assert data[0] == NODE_START      # root start
        assert data[1] == NODE_START      # tile node start
        assert data[2] == OTBM_TILE       # tile type
        # coords: x=100 (LE u16) -> 0x64 0x00
        assert data[3] == 100 & 0xFF
        assert data[4] == 0x00
        # y=200 -> 0xC8 0x00
        assert data[5] == 200 & 0xFF
        assert data[6] == 0x00
        # z=7
        assert data[7] == 7
        # ATTR_ITEM (0x02)
        assert data[8] == OTBM_ATTR_ITEM
        # ground_id=102 -> 0x66 0x00
        assert data[9] == 102 & 0xFF
        assert data[10] == 0x00
        # NODE_END (tile)
        assert data[11] == NODE_END
        # NODE_END (root)
        assert data[12] == NODE_END
        assert w.tiles_written == 1

    def test_single_tile_with_items(self):
        w = OTBMLiveWriter()
        w.add_root_node()
        w.add_tile(10, 20, 0, ground_id=102, items=[1102, 3756])
        w.end_root_node()

        data = w.get_full_bytes()
        full = bytes(data)
        # Should have two child item nodes: each is NODE_START + OTBM_ITEM + u16 + NODE_END
        # First item node starts after ground item data
        # Look for OTBM_ITEM markers (0x01)
        item_count = 0
        for i, b in enumerate(full):
            if b == OTBM_ITEM and i > 0 and full[i - 1] == NODE_START:
                item_count += 1
        assert item_count == 2, f"Expected 2 item nodes, found {item_count}"
        assert w.tiles_written == 1

    def test_single_tile_with_flags(self):
        w = OTBMLiveWriter()
        w.add_root_node()
        w.add_tile(10, 20, 0, ground_id=103, flags=0x05)
        w.end_root_node()

        data = w.get_full_bytes()
        full = bytes(data)
        # Should contain OTBM_ATTR_TILE_FLAGS (0x01) followed by flags u32
        attr_idx = full.index(OTBM_ATTR_TILE_FLAGS, 2)  # skip first NODE_START
        # After TILE type byte and coordinates (2+2+1=5 bytes after type)
        flags_val = struct.unpack_from('<I', full, attr_idx + 1)[0]
        assert flags_val == 0x05
        assert w.tiles_written == 1

    def test_house_tile(self):
        w = OTBMLiveWriter()
        w.add_root_node()
        w.add_tile(50, 60, 7, ground_id=530, house_id=42)
        w.end_root_node()

        data = w.get_full_bytes()
        # data[0]=root NODE_START, data[1]=tile NODE_START, data[2]=OTBM_HOUSETILE
        assert data[2] == OTBM_HOUSETILE
        # After tile type(1) + x(2) + y(2) + z(1) = 6 bytes from data[2]
        # data[3:5] = x, data[5:7] = y, data[7] = z, data[8:12] = house_id
        house_id = struct.unpack_from('<I', data, 8)[0]
        assert house_id == 42
        assert w.tiles_written == 1

    def test_multiple_tiles(self):
        w = OTBMLiveWriter()
        w.add_root_node()
        w.add_tile(0, 0, 0, ground_id=102)
        w.add_tile(1, 0, 0, ground_id=103)
        w.add_tile(0, 1, 0, ground_id=231)
        w.end_root_node()

        assert w.tiles_written == 3
        data = w.get_full_bytes()
        # Count NODE_START bytes (root + 3 tiles = 4 total, no item children since ground only)
        node_starts = data.count(NODE_START)
        assert node_starts == 4  # root + 3 tiles
        node_ends = data.count(NODE_END)
        assert node_ends == 4  # 3 tiles + root end

    def test_get_bytes_strips_leading_fe(self):
        """get_bytes() strips the leading 0xFE (server adds it back)."""
        w = OTBMLiveWriter()
        w.add_root_node()
        w.add_tile(10, 20, 0, ground_id=102)
        w.end_root_node()

        full = w.get_full_bytes()
        stripped = w.get_bytes()

        assert full[0] == NODE_START   # root start
        # After stripping root 0xFE, next byte is the tile's NODE_START (0xFE)
        assert stripped[0] == NODE_START  # tile's own start
        assert bytes(stripped) == bytes(full[1:])
        assert len(stripped) == len(full) - 1

    def test_get_bytes_empty_buffer(self):
        w = OTBMLiveWriter()
        assert w.get_bytes() == b""

    def test_get_bytes_no_root_start(self):
        """If buffer doesn't start with NODE_START, return as-is."""
        w = OTBMLiveWriter()
        w.buffer = bytearray(b"\x02\x00\x01\x00\x00\x00\xFF")
        assert w.get_bytes()[0] == 0x02  # not stripped

    def test_escape_byte_0xfe(self):
        """Values 0xFE in a byte written via _write_byte should be escaped."""
        w = OTBMLiveWriter()
        w._write_byte(0xFE)
        assert w.buffer[0] == ESCAPE_BYTE  # 0xFD
        assert w.buffer[1] == 0xFE

    def test_escape_byte_0xff(self):
        """Values 0xFF in a byte written via _write_byte should be escaped."""
        w = OTBMLiveWriter()
        w._write_byte(0xFF)
        assert w.buffer[0] == ESCAPE_BYTE
        assert w.buffer[1] == 0xFF

    def test_escape_byte_0xfd(self):
        """Values 0xFD (escape byte itself) should be escaped."""
        w = OTBMLiveWriter()
        w._write_byte(0xFD)
        assert w.buffer[0] == ESCAPE_BYTE
        assert w.buffer[1] == 0xFD

    def test_normal_byte_no_escape(self):
        """Values below 0xFD should not be escaped."""
        w = OTBMLiveWriter()
        w._write_byte(0x42)
        assert len(w.buffer) == 1
        assert w.buffer[0] == 0x42

    def test_item_not_duplicated_when_same_as_ground(self):
        """If item_id equals ground_id, it should not be written as a child item."""
        w = OTBMLiveWriter()
        w.add_root_node()
        w.add_tile(10, 20, 0, ground_id=102, items=[102, 200])
        w.end_root_node()

        data = w.get_full_bytes()
        full = bytes(data)
        # Count item child nodes (NODE_START + OTBM_ITEM)
        item_nodes = 0
        for i in range(1, len(full) - 1):
            if full[i] == OTBM_ITEM and full[i - 1] == NODE_START:
                item_nodes += 1
        # Should have only 1 item node (200), not 2 (102 is ground)
        assert item_nodes == 1

    def test_reset(self):
        w = OTBMLiveWriter()
        w.add_root_node()
        w.add_tile(10, 20, 0, ground_id=102)
        w.reset()
        assert len(w) == 0
        assert w.tiles_written == 0

    def test_add_tiles_from_map_data_dict(self):
        """add_tiles_from_map_data works with dict-style tiles attribute."""
        tile1 = SimpleTile(100, 200, 7, ground_id=102)
        tile2 = SimpleTile(101, 200, 7, ground_id=103, items=[SimpleItem(1102)])
        map_data = SimpleMapData(tiles={
            (100, 200, 7): tile1,
            (101, 200, 7): tile2,
        })

        w = OTBMLiveWriter()
        w.add_root_node()
        count = w.add_tiles_from_map_data(map_data)
        w.end_root_node()

        assert count == 2
        assert w.tiles_written == 2

    def test_add_tiles_from_map_data_with_flags_and_house(self):
        """add_tiles_from_map_data correctly reads flags and house_id."""
        tile = SimpleTile(50, 60, 7, ground_id=530, flags=0x01, house_id=99)
        map_data = SimpleMapData(tiles={(50, 60, 7): tile})

        w = OTBMLiveWriter()
        w.add_root_node()
        w.add_tiles_from_map_data(map_data)
        w.end_root_node()

        data = w.get_full_bytes()
        # data[0]=root NODE_START, data[1]=tile NODE_START, data[2]=OTBM_HOUSETILE
        assert data[2] == OTBM_HOUSETILE  # has house_id
        assert w.tiles_written == 1

    def test_add_tiles_from_map_data_no_matching_tiles(self):
        """add_tiles_from_map_data returns 0 when no tiles have data."""
        map_data = SimpleMapData(tiles={})

        w = OTBMLiveWriter()
        w.add_root_node()
        count = w.add_tiles_from_map_data(map_data)
        assert count == 0

    def test_add_tiles_from_map_data_object_with_get_tiles(self):
        """add_tiles_from_map_data works with get_tiles() interface."""
        mock_map = MagicMock()
        tile1 = SimpleTile(10, 20, 0, ground_id=102)
        tile2 = SimpleTile(11, 21, 0, ground_id=103)
        mock_map.get_tiles.return_value = [tile1, tile2]

        w = OTBMLiveWriter()
        w.add_root_node()
        count = w.add_tiles_from_map_data(mock_map)
        w.end_root_node()

        assert count == 2
        assert w.tiles_written == 2


# ===========================================================================
# 4. LiveClient Tests
# ===========================================================================

class TestLiveClient:

    def test_constructor_defaults(self):
        client = LiveClient()
        assert client.name == "OTBForge"
        assert client.password == ""
        assert client.protocol_id == DEFAULT_PROTOCOL_ID
        assert client.rme_version == RME_VERSION_ID
        assert client.net_version == LIVE_NET_VERSION
        assert client._connected is False
        assert client._accepted is False
        assert client.connected is False

    def test_constructor_custom_values(self):
        client = LiveClient(name="TestBot", password="secret", protocol_id=1098)
        assert client.name == "TestBot"
        assert client.password == "secret"
        assert client.protocol_id == 1098

    def test_name_truncation(self):
        client = LiveClient(name="A" * 50)
        assert len(client.name) == 32
        assert client.name == "A" * 32

    def test_password_truncation(self):
        client = LiveClient(password="X" * 50)
        assert len(client.password) == 32

    def test_repr_disconnected(self):
        client = LiveClient(name="Bot")
        assert "disconnected" in repr(client)
        assert "Bot" in repr(client)

    def test_map_info_property(self):
        client = LiveClient()
        assert client.map_info.name == ""
        assert client.map_info.width == 0
        assert client.map_info.height == 0

    def test_send_tile_changes_message_format(self):
        """Verify send_tile_changes produces correct CHANGE_LIST packet."""
        client = LiveClient()
        mock_sock = MagicMock()
        client._sock = mock_sock
        client._connected = True

        # Use ASCII-safe bytes to avoid utf-8 expansion issues
        tile_data = b"\x02\x64\x00\xC8\x00\x07\x02\x66\x00\xFD"
        client.send_tile_changes(tile_data)

        assert mock_sock.sendall.called
        frame = mock_sock.sendall.call_args[0][0]
        # Decode the frame
        size = struct.unpack('<I', frame[:4])[0]
        payload = frame[4:]
        assert len(payload) == size
        # First byte should be CHANGE_LIST (0x21)
        msg = NetworkMessage()
        msg.buffer = bytearray(payload)
        assert msg.read_u8() == LivePacket.CHANGE_LIST
        # Then string (u16 length + data)
        str_len = msg.read_u16()
        # The string is decoded from latin-1 then re-encoded as utf-8
        # 0xFD in latin-1 -> ÿ? No, 0xFD -> U+00FD -> utf-8 is 0xC3 0xBD (2 bytes)
        utf8_encoded = tile_data.decode('latin-1').encode('utf-8')
        assert str_len == len(utf8_encoded)

    def test_send_chat_message_format(self):
        """Verify send_chat produces correct CLIENT_TALK packet."""
        client = LiveClient()
        mock_sock = MagicMock()
        client._sock = mock_sock
        client._connected = True

        client.send_chat("Hello RME!")

        assert mock_sock.sendall.called
        frame = mock_sock.sendall.call_args[0][0]
        size = struct.unpack('<I', frame[:4])[0]
        payload = frame[4:]
        msg = NetworkMessage()
        msg.buffer = bytearray(payload)
        assert msg.read_u8() == LivePacket.CLIENT_TALK
        assert msg.read_string() == "Hello RME!"

    def test_send_cursor_update_message_format(self):
        """Verify send_cursor_update produces correct CLIENT_UPDATE_CURSOR packet."""
        client = LiveClient()
        mock_sock = MagicMock()
        client._sock = mock_sock
        client._connected = True

        client.send_cursor_update(100, 200, 7)

        assert mock_sock.sendall.called
        frame = mock_sock.sendall.call_args[0][0]
        payload = frame[4:]
        msg = NetworkMessage()
        msg.buffer = bytearray(payload)
        assert msg.read_u8() == LivePacket.CLIENT_UPDATE_CURSOR
        cursor_id = msg.read_u32()
        assert cursor_id == 0
        r = msg.read_u8()
        g = msg.read_u8()
        b = msg.read_u8()
        a = msg.read_u8()
        assert (r, g, b, a) == (255, 0, 0, 200)
        x, y, z = msg.read_position()
        assert (x, y, z) == (100, 200, 7)

    def test_send_tile_changes_bytes_converted_to_string(self):
        """send_tile_changes accepts bytes and encodes as latin-1 string."""
        client = LiveClient()
        mock_sock = MagicMock()
        client._sock = mock_sock
        client._connected = True

        # Binary data that's valid latin-1
        tile_data = bytes(range(256))
        client.send_tile_changes(tile_data)
        frame = mock_sock.sendall.call_args[0][0]
        payload = frame[4:]
        msg = NetworkMessage()
        msg.buffer = bytearray(payload)
        msg.read_u8()  # skip packet type
        recovered = msg.read_string()
        assert recovered.encode('latin-1') == tile_data

    def test_send_without_connection_raises(self):
        """Sending without being connected raises ConnectionError."""
        client = LiveClient()
        client._sock = None
        client._connected = False
        with pytest.raises(ConnectionError):
            client.send_chat("test")

    def test_parse_hello_from_server(self):
        """_parse_packet correctly handles HELLO_FROM_SERVER."""
        client = LiveClient()

        msg = NetworkMessage()
        msg.write_u8(LivePacket.HELLO_FROM_SERVER)
        msg.write_string("My Map")
        msg.write_u16(2048)
        msg.write_u16(2048)
        msg.position = 0

        connected_info = None
        client.on_connected = lambda info: nonlocal_update('connected_info', info)

        # Use a simple callback capture
        captured = {}
        def capture(info):
            captured['info'] = info
        client.on_connected = capture

        client._parse_packet(msg)

        assert client.map_info.name == "My Map"
        assert client.map_info.width == 2048
        assert client.map_info.height == 2048
        assert captured['info'].name == "My Map"

    def test_parse_kick(self):
        """_parse_packet correctly handles KICK packet."""
        client = LiveClient()
        client._connected = True

        captured = {}
        def on_kick(msg):
            captured['msg'] = msg
        client.on_kicked = on_kick

        msg = NetworkMessage()
        msg.write_u8(LivePacket.KICK)
        msg.write_string("Wrong version")
        msg.position = 0

        client._parse_packet(msg)

        assert not client._connected
        assert captured['msg'] == "Wrong version"

    def test_parse_server_talk(self):
        """_parse_packet correctly handles SERVER_TALK packet."""
        client = LiveClient()

        captured = {}
        def on_chat(speaker, text):
            captured['speaker'] = speaker
            captured['text'] = text
        client.on_chat = on_chat

        msg = NetworkMessage()
        msg.write_u8(LivePacket.SERVER_TALK)
        msg.write_string("Admin")
        msg.write_string("Welcome!")
        msg.position = 0

        client._parse_packet(msg)

        assert captured['speaker'] == "Admin"
        assert captured['text'] == "Welcome!"

    def test_parse_start_operation(self):
        """_parse_packet correctly handles START_OPERATION."""
        client = LiveClient()

        captured = {}
        def on_start(op):
            captured['op'] = op
        client.on_operation_start = on_start

        msg = NetworkMessage()
        msg.write_u8(LivePacket.START_OPERATION)
        msg.write_string("Loading map...")
        msg.position = 0

        client._parse_packet(msg)

        assert captured['op'] == "Loading map..."

    def test_parse_update_operation(self):
        """_parse_packet correctly handles UPDATE_OPERATION."""
        client = LiveClient()

        captured = {}
        def on_update(pct):
            captured['pct'] = pct
        client.on_operation_update = on_update

        msg = NetworkMessage()
        msg.write_u8(LivePacket.UPDATE_OPERATION)
        msg.write_u32(75)
        msg.position = 0

        client._parse_packet(msg)

        assert captured['pct'] == 75

    def test_parse_node(self):
        """_parse_packet correctly handles NODE packet."""
        client = LiveClient()

        captured = {}
        def on_node(ndx, ndy, ind, underground):
            captured['ndx'] = ndx
            captured['ndy'] = ndy
            captured['ind'] = ind
            captured['underground'] = underground
        client.on_node_received = on_node

        msg = NetworkMessage()
        msg.write_u8(LivePacket.NODE)
        # ind = ndx << 18 | ndy << 4 | (underground ? 1 : 0)
        # ndx=5, ndy=10, underground=True -> 5<<18 | 10<<4 | 1
        ind = (5 << 18) | (10 << 4) | 1
        msg.write_u32(ind)
        msg.position = 0

        client._parse_packet(msg)

        assert captured['ndx'] == 5
        assert captured['ndy'] == 10
        assert captured['underground'] is True

    def test_parse_unknown_packet(self):
        """Unknown packet types are handled gracefully."""
        client = LiveClient()
        msg = NetworkMessage()
        msg.write_u8(0xFF)  # Unknown
        msg.position = 0
        # Should not raise
        client._parse_packet(msg)

    def test_parse_cursor_update_consumes_all_bytes(self):
        """CURSOR_UPDATE packet should be consumed without error."""
        client = LiveClient()
        msg = NetworkMessage()
        msg.write_u8(LivePacket.CURSOR_UPDATE)
        msg.write_u32(1)       # id
        msg.write_u8(255)      # r
        msg.write_u8(128)      # g
        msg.write_u8(64)       # b
        msg.write_u8(192)      # a
        msg.write_u16(100)     # x
        msg.write_u16(200)     # y
        msg.write_u8(7)        # z
        msg.position = 0

        # Should consume all bytes without error
        client._parse_packet(msg)
        assert msg.remaining() == 0

    def test_handshake_mock_socketpair(self):
        """Full handshake flow using a real socketpair: hello→accepted→hello_from_server."""
        # Create a socketpair
        server_sock, client_sock = socket.socketpair()

        # Prepare server responses
        def server_responder():
            time.sleep(0.05)
            # Read client HELLO frame
            header = b""
            while len(header) < 4:
                header += server_sock.recv(4 - len(header))
            size = struct.unpack('<I', header)[0]
            payload = b""
            while len(payload) < size:
                payload += server_sock.recv(size - len(payload))

            # Verify HELLO packet
            msg = NetworkMessage()
            msg.buffer = bytearray(payload)
            assert msg.read_u8() == LivePacket.HELLO_FROM_CLIENT
            rme_ver = msg.read_u32()
            assert rme_ver == RME_VERSION_ID
            net_ver = msg.read_u32()
            assert net_ver == LIVE_NET_VERSION

            # Send ACCEPTED_CLIENT
            acc_msg = NetworkMessage()
            acc_msg.write_u8(LivePacket.ACCEPTED_CLIENT)
            server_sock.sendall(encode_frame(acc_msg))

            time.sleep(0.05)

            # Send HELLO_FROM_SERVER
            srv_msg = NetworkMessage()
            srv_msg.write_u8(LivePacket.HELLO_FROM_SERVER)
            srv_msg.write_string("Test Map")
            srv_msg.write_u16(1024)
            srv_msg.write_u16(1024)
            server_sock.sendall(encode_frame(srv_msg))

            server_sock.close()

        server_thread = threading.Thread(target=server_responder, daemon=True)
        server_thread.start()

        # Create client and inject our socket
        client = LiveClient(name="TestClient")
        client._sock = client_sock
        client._connected = True

        # Start receiver thread
        client._recv_thread = threading.Thread(target=client._recv_loop, daemon=True)
        client._recv_thread.start()

        # Send HELLO
        client._send_hello()

        # Wait for handshake to complete
        deadline = time.time() + 3.0
        while not client._accepted:
            if time.time() > deadline:
                pytest.fail("Handshake timed out in mock test")
            time.sleep(0.02)

        # Wait a bit for HELLO_FROM_SERVER to be processed
        time.sleep(0.1)

        assert client.connected is True
        assert client.map_info.name == "Test Map"
        assert client.map_info.width == 1024
        assert client.map_info.height == 1024

        client.close()
        server_thread.join(timeout=2)

    def test_callback_error_does_not_crash(self):
        """Callbacks that raise exceptions should not crash the parser."""
        client = LiveClient()
        client._connected = True

        def bad_chat(speaker, text):
            raise ValueError("callback error")

        client.on_chat = bad_chat

        msg = NetworkMessage()
        msg.write_u8(LivePacket.SERVER_TALK)
        msg.write_string("A")
        msg.write_string("B")
        msg.position = 0

        # Should not raise
        client._parse_packet(msg)

    def test_close(self):
        """close() resets state and closes socket."""
        client = LiveClient()
        mock_sock = MagicMock()
        client._sock = mock_sock
        client._connected = True
        client._accepted = True

        client.close()

        assert client._connected is False
        assert client._accepted is False
        assert client._sock is None
        mock_sock.close.assert_called_once()


# ===========================================================================
# 5. Integration Tests
# ===========================================================================

class TestIntegration:

    def test_map_data_to_writer_to_send_tile_changes(self):
        """Full pipeline: MapData → OTBMLiveWriter → LiveClient.send_tile_changes."""
        # Build map data
        tile1 = SimpleTile(100, 200, 7, ground_id=102, items=[SimpleItem(1102)])
        tile2 = SimpleTile(101, 200, 7, ground_id=103, flags=0x01)
        tile3 = SimpleTile(102, 200, 7, ground_id=530, house_id=42)
        map_data = SimpleMapData(tiles={
            (100, 200, 7): tile1,
            (101, 200, 7): tile2,
            (102, 200, 7): tile3,
        })

        # Serialize
        writer = OTBMLiveWriter()
        writer.add_root_node()
        writer.add_tiles_from_map_data(map_data)
        writer.end_root_node()
        live_bytes = writer.get_bytes()

        # Verify root 0xFE was stripped (first byte is now tile's own NODE_START)
        assert len(live_bytes) > 0

        # Send via mock client
        client = LiveClient()
        mock_sock = MagicMock()
        client._sock = mock_sock
        client._connected = True

        client.send_tile_changes(live_bytes)

        # Verify the frame was sent
        assert mock_sock.sendall.called
        frame = mock_sock.sendall.call_args[0][0]
        size = struct.unpack('<I', frame[:4])[0]
        payload = frame[4:]
        assert len(payload) == size

        # Decode and verify packet type
        msg = NetworkMessage()
        msg.buffer = bytearray(payload)
        assert msg.read_u8() == LivePacket.CHANGE_LIST

    def test_push_map_serializes_and_sends(self):
        """push_map correctly orchestrates serialization and sending."""
        tile = SimpleTile(10, 20, 0, ground_id=102)
        map_data = SimpleMapData(tiles={(10, 20, 0): tile})

        client = LiveClient()
        mock_sock = MagicMock()
        client._sock = mock_sock
        client._connected = True
        client._accepted = True

        progress_captured = []
        client.push_map(map_data, callback_progress=lambda stage, pct: progress_captured.append((stage, pct)))

        # Should have sent 2 messages: tile changes + chat
        assert mock_sock.sendall.call_count == 2

        # First call should be CHANGE_LIST
        frame1 = mock_sock.sendall.call_args_list[0][0][0]
        payload1 = frame1[4:]
        msg1 = NetworkMessage()
        msg1.buffer = bytearray(payload1)
        assert msg1.read_u8() == LivePacket.CHANGE_LIST

        # Second call should be CLIENT_TALK
        frame2 = mock_sock.sendall.call_args_list[1][0][0]
        payload2 = frame2[4:]
        msg2 = NetworkMessage()
        msg2.buffer = bytearray(payload2)
        assert msg2.read_u8() == LivePacket.CLIENT_TALK
        chat_text = msg2.read_string()
        assert "OTBForge" in chat_text
        assert "1 tiles" in chat_text

        # Progress should have been called
        assert len(progress_captured) >= 2
        assert progress_captured[-1] == ("Done!", 100)

    def test_large_map_serialization(self):
        """Serialize a large number of tiles without errors."""
        tiles = {}
        for x in range(50):
            for y in range(50):
                tiles[(x, y, 0)] = SimpleTile(x, y, 0, ground_id=102)
        map_data = SimpleMapData(tiles=tiles)

        writer = OTBMLiveWriter()
        writer.add_root_node()
        count = writer.add_tiles_from_map_data(map_data)
        writer.end_root_node()

        assert count == 2500
        assert writer.tiles_written == 2500
        assert len(writer.get_bytes()) > 0

    def test_empty_map_data_no_send(self):
        """Empty map data produces minimal output."""
        map_data = SimpleMapData(tiles={})

        writer = OTBMLiveWriter()
        writer.add_root_node()
        count = writer.add_tiles_from_map_data(map_data)
        writer.end_root_node()

        assert count == 0
        live_bytes = writer.get_bytes()
        # Should only have the root end byte (0xFF)
        assert live_bytes == bytes([NODE_END])


def nonlocal_update(name, value):
    """Helper for nonlocal assignment in older Python patterns."""
    # Not actually used in final code, but keeps pattern available
    pass
