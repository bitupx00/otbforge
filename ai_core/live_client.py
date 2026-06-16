"""RME Live Protocol — Wire format for Remere's Map Editor Live networking.

Protocol specs (reverse-engineered from RME Redux source):
  Frame:  [4B uint32 LE payload_size][payload bytes]
  String: [2B uint16 LE length][utf8 bytes]
  Position: [2B x][2B y][1B z]
  Cursor: [4B id][1B r][1B g][1B b][1B a][Position]

Handshake:
  Client → HELLO_FROM_CLIENT (0x10): rme_version(4) + net_version(4) + protocol_id(4) + name(str) + password(str)
  Server → PACKET_ACCEPTED_CLIENT (0x82) or PACKET_KICK (0x81) + msg(str)
  Client → PACKET_READY_CLIENT (0x11)
  Server → PACKET_HELLO_FROM_SERVER (0x80): map_name(str) + width(u16) + height(u16)

Tile Changes (client → server):
  PACKET_CHANGE_LIST (0x21): binary_node_data(str) — OTBM serialized tiles

Chat:
  PACKET_CLIENT_TALK (0x30): message(str)
  PACKET_SERVER_TALK (0x84): speaker(str) + message(str)

Operations:
  PACKET_START_OPERATION (0x92): operation_name(str)
  PACKET_UPDATE_OPERATION (0x93): percent(u32)

Nodes (server → client):
  PACKET_NODE (0x90): node_index(u32) + floor_bits(u16) + [floor data...]

Version constants for RME Redux 4.1.2:
  __RME_VERSION_ID__ = MAKE_VERSION_ID(4, 1, 2) = 40102000
  __LIVE_NET_VERSION__ = 5
"""

import struct
import socket
import threading
import time
import logging
from enum import IntEnum
from dataclasses import dataclass, field
from typing import Callable, Optional, List, Tuple

logger = logging.getLogger(__name__)


# ─── Constants ───────────────────────────────────────────────────────────────

# RME Redux 4.1.2 version IDs
RME_VERSION_MAJOR = 4
RME_VERSION_MINOR = 1
RME_SUBVERSION = 2
RME_VERSION_ID = RME_VERSION_MAJOR * 10000000 + RME_VERSION_MINOR * 100000 + RME_SUBVERSION * 1000  # 40102000
LIVE_NET_VERSION = 5

# Default protocol version (client version / OTB version)
DEFAULT_PROTOCOL_ID = 1210  # Common Tibia client version


class LivePacket(IntEnum):
    # Client → Server
    HELLO_FROM_CLIENT = 0x10
    READY_CLIENT = 0x11
    REQUEST_NODES = 0x20
    CHANGE_LIST = 0x21
    ADD_HOUSE = 0x23
    EDIT_HOUSE = 0x24
    REMOVE_HOUSE = 0x25
    CLIENT_TALK = 0x30
    CLIENT_UPDATE_CURSOR = 0x31

    # Server → Client
    HELLO_FROM_SERVER = 0x80
    KICK = 0x81
    ACCEPTED_CLIENT = 0x82
    CHANGE_CLIENT_VERSION = 0x83
    SERVER_TALK = 0x84
    NODE = 0x90
    CURSOR_UPDATE = 0x91
    START_OPERATION = 0x92
    UPDATE_OPERATION = 0x93
    CHAT_MESSAGE = 0x94


# ─── NetworkMessage ──────────────────────────────────────────────────────────

class NetworkMessage:
    """Binary message builder/reader matching RME's NetworkMessage class."""

    def __init__(self):
        self.buffer = bytearray()
        self.position = 0

    def clear(self):
        self.buffer = bytearray()
        self.position = 0

    # ── Write methods ──

    def write_u8(self, value: int):
        self.buffer.extend(struct.pack('<B', value & 0xFF))

    def write_u16(self, value: int):
        self.buffer.extend(struct.pack('<H', value & 0xFFFF))

    def write_u32(self, value: int):
        self.buffer.extend(struct.pack('<I', value & 0xFFFFFFFF))

    def write_string(self, value: str):
        encoded = value.encode('utf-8') if isinstance(value, str) else value
        self.write_u16(len(encoded))
        self.buffer.extend(encoded)

    def write_position(self, x: int, y: int, z: int):
        self.write_u16(x)
        self.write_u16(y)
        self.write_u8(z)

    def write_cursor(self, cursor_id: int, r: int, g: int, b: int, a: int, x: int, y: int, z: int):
        self.write_u32(cursor_id)
        self.write_u8(r)
        self.write_u8(g)
        self.write_u8(b)
        self.write_u8(a)
        self.write_position(x, y, z)

    def write_bytes(self, data: bytes):
        self.buffer.extend(data)

    # ── Read methods ──

    def read_u8(self) -> int:
        val = struct.unpack_from('<B', self.buffer, self.position)[0]
        self.position += 1
        return val

    def read_u16(self) -> int:
        val = struct.unpack_from('<H', self.buffer, self.position)[0]
        self.position += 2
        return val

    def read_u32(self) -> int:
        val = struct.unpack_from('<I', self.buffer, self.position)[0]
        self.position += 4
        return val

    def read_string(self) -> str:
        length = self.read_u16()
        data = self.buffer[self.position:self.position + length]
        self.position += length
        return data.decode('utf-8', errors='replace')

    def read_position(self) -> Tuple[int, int, int]:
        x = self.read_u16()
        y = self.read_u16()
        z = self.read_u8()
        return (x, y, z)

    def remaining(self) -> int:
        return len(self.buffer) - self.position

    def __len__(self) -> int:
        return len(self.buffer)


# ─── Frame encoding ─────────────────────────────────────────────────────────

def encode_frame(message: NetworkMessage) -> bytes:
    """Encode a NetworkMessage into a TCP frame: [4B size][payload]."""
    size = len(message)
    return struct.pack('<I', size) + bytes(message.buffer)


def decode_frame(data: bytes, offset: int = 0) -> Tuple[NetworkMessage, int]:
    """Decode a TCP frame into a NetworkMessage. Returns (message, new_offset)."""
    size = struct.unpack_from('<I', data, offset)[0]
    offset += 4
    msg = NetworkMessage()
    msg.buffer = bytearray(data[offset:offset + size])
    msg.position = 0
    return msg, offset + size


# ─── LiveClient ──────────────────────────────────────────────────────────────

@dataclass
class LiveMapInfo:
    """Map info received from server after handshake."""
    name: str = ""
    width: int = 0
    height: int = 0


class LiveClient:
    """Python client for RME Live Server protocol.

    Connects to a running RME Live Server and can:
    - Send tile changes (PACKET_CHANGE_LIST)
    - Send chat messages
    - Update cursor position
    - Receive server events via callbacks

    Usage:
        client = LiveClient("OTBForge")
        client.on_chat = lambda speaker, msg: print(f"[{speaker}] {msg}")
        client.on_operation_start = lambda op: print(f"Starting: {op}")
        client.on_operation_update = lambda pct: print(f"Progress: {pct}%")
        client.connect("localhost", 31313)
        # ... send tiles ...
        client.send_tile_changes(tile_data_bytes)
        client.close()
    """

    def __init__(self, name: str = "OTBForge", password: str = "",
                 protocol_id: int = DEFAULT_PROTOCOL_ID):
        self.name = name[:32]
        self.password = password[:32]
        self.protocol_id = protocol_id
        self.rme_version = RME_VERSION_ID
        self.net_version = LIVE_NET_VERSION

        self._sock: Optional[socket.socket] = None
        self._recv_thread: Optional[threading.Thread] = None
        self._connected = False
        self._accepted = False
        self._map_info = LiveMapInfo()
        self._lock = threading.Lock()
        self._recv_buffer = bytearray()

        # Callbacks
        self.on_chat: Optional[Callable[[str, str], None]] = None
        self.on_operation_start: Optional[Callable[[str], None]] = None
        self.on_operation_update: Optional[Callable[[int], None]] = None
        self.on_node_received: Optional[Callable[[int, int, int, bool], None]] = None
        self.on_kicked: Optional[Callable[[str], None]] = None
        self.on_connected: Optional[Callable[[LiveMapInfo], None]] = None
        self.on_disconnected: Optional[Callable[[str], None]] = None

    @property
    def connected(self) -> bool:
        return self._connected and self._accepted

    @property
    def map_info(self) -> LiveMapInfo:
        return self._map_info

    def connect(self, host: str, port: int = 31313, timeout: float = 10.0) -> bool:
        """Connect to RME Live Server and complete handshake."""
        try:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._sock.settimeout(timeout)
            self._sock.connect((host, port))
            self._sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            self._connected = True
            logger.info(f"Connected to {host}:{port}")
        except (socket.error, OSError) as e:
            logger.error(f"Connection failed: {e}")
            return False

        # Start receiver thread
        self._recv_thread = threading.Thread(target=self._recv_loop, daemon=True)
        self._recv_thread.start()

        # Send HELLO
        self._send_hello()

        # Wait for ACCEPTED or KICK (with timeout)
        deadline = time.time() + timeout
        while not self._accepted and self._connected:
            if time.time() > deadline:
                self.close()
                raise TimeoutError("Handshake timed out")
            time.sleep(0.05)

        return self._accepted

    def close(self):
        """Disconnect from server."""
        self._connected = False
        self._accepted = False
        if self._sock:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None
        if self._recv_thread:
            self._recv_thread.join(timeout=2)
            self._recv_thread = None
        logger.info("Disconnected")

    # ── Send methods ──

    def _send_message(self, msg: NetworkMessage):
        """Send a framed message to the server."""
        if not self._sock or not self._connected:
            raise ConnectionError("Not connected to server")
        with self._lock:
            frame = encode_frame(msg)
            self._sock.sendall(frame)

    def _send_hello(self):
        """Send HELLO_FROM_CLIENT packet."""
        msg = NetworkMessage()
        msg.write_u8(LivePacket.HELLO_FROM_CLIENT)
        msg.write_u32(self.rme_version)
        msg.write_u32(self.net_version)
        msg.write_u32(self.protocol_id)
        msg.write_string(self.name)
        msg.write_string(self.password)
        self._send_message(msg)

    def _send_ready(self):
        """Send READY_CLIENT packet."""
        msg = NetworkMessage()
        msg.write_u8(LivePacket.READY_CLIENT)
        self._send_message(msg)

    def send_tile_changes(self, otbm_tile_data: bytes):
        """Send tile changes to the server (PACKET_CHANGE_LIST).

        The otbm_tile_data should be a raw OTBM binary blob containing
        tile nodes (same format as sent by sendTile in C++).

        Each tile is serialized as:
          [OTBM_TILE/OTBM_HOUSETILE byte]
          [x u16][y u16][z u8]  (only for top-level, not for live nodes)
          [if house: house_id u32]
          [if flags: OTBM_ATTR_TILE_FLAGS byte + flags u32]
          [if ground: OTBM_ATTR_ITEM byte + item_id u16]
          [items: OTBM_ITEM byte + item_id u16 + ...]
        """
        msg = NetworkMessage()
        msg.write_u8(LivePacket.CHANGE_LIST)
        # String = u16 length + data
        msg.write_string(otbm_tile_data.decode('latin-1') if isinstance(otbm_tile_data, bytes) else otbm_tile_data)
        self._send_message(msg)

    def send_chat(self, message: str):
        """Send a chat message visible in RME's Live tab."""
        msg = NetworkMessage()
        msg.write_u8(LivePacket.CLIENT_TALK)
        msg.write_string(message)
        self._send_message(msg)

    def send_cursor_update(self, x: int, y: int, z: int):
        """Update cursor position visible to other Live users."""
        msg = NetworkMessage()
        msg.write_u8(LivePacket.CLIENT_UPDATE_CURSOR)
        # Cursor: id(4) + rgba(4) + Position(5)
        msg.write_u32(0)  # id will be set by server
        msg.write_u8(255)  # r
        msg.write_u8(0)    # g
        msg.write_u8(0)    # b
        msg.write_u8(200)  # a
        msg.write_position(x, y, z)
        self._send_message(msg)

    # ── Receive loop ──

    def _recv_loop(self):
        """Background thread that receives and dispatches packets."""
        while self._connected:
            try:
                # Read header (4 bytes)
                header = self._recv_exact(4)
                if not header:
                    break
                size = struct.unpack('<I', header)[0]

                # Read payload
                payload = self._recv_exact(size)
                if not payload:
                    break

                # Parse
                msg = NetworkMessage()
                msg.buffer = bytearray(payload)
                msg.position = 0
                self._parse_packet(msg)

            except (ConnectionError, OSError) as e:
                if self._connected:
                    logger.error(f"Receive error: {e}")
                    if self.on_disconnected:
                        try:
                            self.on_disconnected(str(e))
                        except Exception:
                            pass
                break

    def _recv_exact(self, n: int) -> Optional[bytes]:
        """Receive exactly n bytes from socket."""
        if not self._sock:
            return None
        data = bytearray()
        while len(data) < n:
            try:
                chunk = self._sock.recv(n - len(data))
                if not chunk:
                    return None
                data.extend(chunk)
            except socket.timeout:
                continue
            except OSError:
                return None
        return bytes(data)

    def _parse_packet(self, msg: NetworkMessage):
        """Parse and dispatch a received packet."""
        while msg.remaining() > 0:
            packet_type = msg.read_u8()

            if packet_type == LivePacket.HELLO_FROM_SERVER:
                self._map_info.name = msg.read_string()
                self._map_info.width = msg.read_u16()
                self._map_info.height = msg.read_u16()
                logger.info(f"Connected to map: {self._map_info.name} ({self._map_info.width}x{self._map_info.height})")
                if self.on_connected:
                    try:
                        self.on_connected(self._map_info)
                    except Exception as e:
                        logger.error(f"on_connected callback error: {e}")

            elif packet_type == LivePacket.KICK:
                kick_msg = msg.read_string()
                logger.warning(f"Kicked: {kick_msg}")
                self._connected = False
                if self.on_kicked:
                    try:
                        self.on_kicked(kick_msg)
                    except Exception:
                        pass

            elif packet_type == LivePacket.ACCEPTED_CLIENT:
                self._send_ready()
                self._accepted = True
                logger.info("Accepted by server")

            elif packet_type == LivePacket.CHANGE_CLIENT_VERSION:
                new_protocol = msg.read_u32()
                self.protocol_id = new_protocol
                logger.info(f"Server requested protocol version change to {new_protocol}")
                self._send_ready()

            elif packet_type == LivePacket.SERVER_TALK:
                speaker = msg.read_string()
                chat_msg = msg.read_string()
                logger.info(f"[{speaker}] {chat_msg}")
                if self.on_chat:
                    try:
                        self.on_chat(speaker, chat_msg)
                    except Exception:
                        pass

            elif packet_type == LivePacket.NODE:
                ind = msg.read_u32()
                ndx = ind >> 18
                ndy = (ind >> 4) & 0x3FFF
                underground = bool(ind & 1)
                if self.on_node_received:
                    try:
                        self.on_node_received(ndx, ndy, ind, underground)
                    except Exception:
                        pass

            elif packet_type == LivePacket.START_OPERATION:
                operation = msg.read_string()
                logger.info(f"Operation started: {operation}")
                if self.on_operation_start:
                    try:
                        self.on_operation_start(operation)
                    except Exception:
                        pass

            elif packet_type == LivePacket.UPDATE_OPERATION:
                percent = msg.read_u32()
                logger.info(f"Operation progress: {percent}%")
                if self.on_operation_update:
                    try:
                        self.on_operation_update(percent)
                    except Exception:
                        pass

            elif packet_type == LivePacket.CURSOR_UPDATE:
                # Skip cursor updates (just consume the bytes)
                msg.read_u32()  # id
                msg.read_u8()   # r
                msg.read_u8()   # g
                msg.read_u8()   # b
                msg.read_u8()   # a
                msg.read_u16()  # x
                msg.read_u16()  # y
                msg.read_u8()   # z

            else:
                logger.warning(f"Unknown packet type: 0x{packet_type:02X}")
                break

    # ── Convenience: generate and push ──

    def push_map(self, map_data, callback_progress=None):
        """Generate OTBM tile data from MapData and send as CHANGE_LIST.

        Converts the MapData tiles into OTBM live format and sends
        them in chunks to the server.

        Args:
            map_data: MapData object (has .tiles dict with (x,y,z) → tile)
            callback_progress: Optional callback(stage, percent) for progress
        """
        from .otbm_live_serializer import OTBMLiveWriter

        # Serialize all tiles as OTBM live node data
        writer = OTBMLiveWriter()
        writer.add_root_node()
        tile_count = writer.add_tiles_from_map_data(map_data)
        writer.end_root_node()

        live_bytes = writer.get_bytes()

        if callback_progress:
            callback_progress("Sending tiles...", 0)

        self.send_tile_changes(live_bytes)

        if callback_progress:
            callback_progress("Done!", 100)

        # Send chat message
        self.send_chat(f"[OTBForge] Map pushed: {tile_count} tiles, {len(live_bytes)} bytes")

    def __repr__(self):
        status = "connected" if self.connected else "disconnected"
        return f"<LiveClient name='{self.name}' {status}>"
