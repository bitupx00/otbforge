/*!
OTBForge OTBM — OTBM v2/v3 binary format reader and writer.

This crate provides `OTBMWriter` (serialises `MapData` → `Vec<u8>`) and
`OTBMReader` (parses `&[u8]` → `MapData`).  The wire format matches the
Python implementation in `ai_core/otbm_writer.py`.
*/

use std::collections::BTreeMap;

use otbforge_models::*;
use thiserror::Error;

// ---------------------------------------------------------------------------
// Errors
// ---------------------------------------------------------------------------

/// Errors that can occur during OTBM read/write operations.
#[derive(Debug, Error)]
pub enum OtbmError {
    #[error("IO error: {0}")]
    Io(#[from] std::io::Error),

    #[error("invalid magic bytes: expected OTBM, got {0:#04x?}")]
    InvalidMagic(Vec<u8>),

    #[error("unexpected end of data at offset {offset}, need {need} byte(s)")]
    UnexpectedEof { offset: usize, need: usize },

    #[error("unexpected node type {0:#04x} at offset {1}")]
    UnexpectedNodeType(u8, usize),

    #[error("unexpected attribute {0:#04x} at offset {1}")]
    UnexpectedAttribute(u8, usize),

    #[error("invalid escape sequence at offset {0}")]
    InvalidEscape(usize),

    #[error("invalid OTBM version: {0}")]
    InvalidVersion(u32),

    #[error("duplicate tile at ({1}, {2}, {3})")]
    DuplicateTile(usize, u16, u16, u8),

    #[error("house tile without house id at ({1}, {2}, {3})")]
    HouseTileNoId(usize, u16, u16, u8),

    #[error("node nesting too deep at offset {0}")]
    NestingTooDeep(usize),

    #[error("unknown node type {0:#04x} at offset {1}")]
    UnknownNodeType(u8, usize),

    #[error("unknown attribute {0:#04x} at offset {1}")]
    UnknownAttribute(u8, usize),

    #[error("general parse error at offset {offset}: {message}")]
    ParseError { offset: usize, message: String },
}

// ---------------------------------------------------------------------------
// BinaryWriter — internal helper for wire format
// ---------------------------------------------------------------------------

/// Low-level binary writer that handles escaping for the OTBM wire format.
///
/// Every multi-byte field escapes bytes ≥ 0xFD with a 0xFD prefix.
struct BinaryWriter {
    buf: Vec<u8>,
}

impl BinaryWriter {
    fn new() -> Self {
        Self { buf: Vec::new() }
    }

    /// Write an unescaped byte (for control / attribute tags).
    fn raw_byte(&mut self, value: u8) {
        self.buf.push(value);
    }

    /// Write one byte with proper escaping.
    fn escaped_byte(&mut self, value: u8) {
        if value >= ESCAPE_THRESHOLD {
            self.buf.push(ESCAPE);
        }
        self.buf.push(value);
    }

    /// Write raw bytes with each byte individually escaped.
    fn escaped_bytes(&mut self, data: &[u8]) {
        for &b in data {
            self.escaped_byte(b);
        }
    }

    /// Write u16 little-endian with per-byte escaping.
    fn u16(&mut self, value: u16) {
        self.escaped_bytes(&value.to_le_bytes());
    }

    /// Write u32 little-endian with per-byte escaping.
    fn u32(&mut self, value: u32) {
        self.escaped_bytes(&value.to_le_bytes());
    }

    /// Write a length-prefixed UTF-8 string (u16 length + escaped bytes).
    fn string(&mut self, s: &str) {
        let encoded = s.as_bytes();
        self.u16(encoded.len() as u16);
        self.escaped_bytes(encoded);
    }

    /// Write a node start marker (0xFE + type byte).
    fn start_node(&mut self, node_type: NodeType) {
        self.buf.push(NODE_START);
        self.raw_byte(node_type as u8);
    }

    /// Write a node end marker (0xFF).
    fn end_node(&mut self) {
        self.buf.push(NODE_END);
    }

    /// Consume the buffer.
    fn into_bytes(self) -> Vec<u8> {
        self.buf
    }
}

// ---------------------------------------------------------------------------
// BinaryReader — internal helper for wire format
// ---------------------------------------------------------------------------

/// Low-level binary reader that handles escaping for the OTBM wire format.
struct BinaryReader<'a> {
    data: &'a [u8],
    pos: usize,
}

impl<'a> BinaryReader<'a> {
    fn new(data: &'a [u8]) -> Self {
        Self { data, pos: 0 }
    }

    fn offset(&self) -> usize {
        self.pos
    }

    fn remaining(&self) -> usize {
        self.data.len().saturating_sub(self.pos)
    }

    fn check(&self, need: usize) -> Result<(), OtbmError> {
        if self.remaining() < need {
            Err(OtbmError::UnexpectedEof {
                offset: self.pos,
                need,
            })
        } else {
            Ok(())
        }
    }

    /// Read one unescaped byte.
    fn raw_byte(&mut self) -> Result<u8, OtbmError> {
        self.check(1)?;
        let b = self.data[self.pos];
        self.pos += 1;
        Ok(b)
    }

    /// Read one escaped byte (handles 0xFD escape prefix).
    fn escaped_byte(&mut self) -> Result<u8, OtbmError> {
        self.check(1)?;
        let b = self.data[self.pos];
        self.pos += 1;
        if b == ESCAPE {
            self.check(1)?;
            let escaped = self.data[self.pos];
            self.pos += 1;
            if escaped < ESCAPE_THRESHOLD {
                return Err(OtbmError::InvalidEscape(self.pos - 2));
            }
            Ok(escaped)
        } else {
            Ok(b)
        }
    }

    /// Read escaped bytes of the given length.
    fn escaped_bytes(&mut self, len: usize) -> Result<Vec<u8>, OtbmError> {
        let mut result = Vec::with_capacity(len);
        for _ in 0..len {
            result.push(self.escaped_byte()?);
        }
        Ok(result)
    }

    /// Read u16 little-endian from escaped bytes.
    fn read_u16(&mut self) -> Result<u16, OtbmError> {
        let bytes = self.escaped_bytes(2)?;
        Ok(u16::from_le_bytes([bytes[0], bytes[1]]))
    }

    /// Read u32 little-endian from escaped bytes.
    fn read_u32(&mut self) -> Result<u32, OtbmError> {
        let bytes = self.escaped_bytes(4)?;
        Ok(u32::from_le_bytes([bytes[0], bytes[1], bytes[2], bytes[3]]))
    }

    /// Read a length-prefixed UTF-8 string.
    fn read_string(&mut self) -> Result<String, OtbmError> {
        let len = self.read_u16()? as usize;
        let bytes = self.escaped_bytes(len)?;
        String::from_utf8(bytes).map_err(|e| OtbmError::ParseError {
            offset: self.pos,
            message: format!("invalid UTF-8: {}", e),
        })
    }

    /// Peek at the next byte without consuming.
    fn peek(&self) -> Result<u8, OtbmError> {
        self.check(1)?;
        Ok(self.data[self.pos])
    }

    /// Check if we're at a node start marker.
    fn is_node_start(&self) -> Result<bool, OtbmError> {
        Ok(self.peek()? == NODE_START)
    }

    /// Read a node start, returning the node type.
    fn read_node_start(&mut self) -> Result<NodeType, OtbmError> {
        let marker = self.raw_byte()?;
        if marker != NODE_START {
            return Err(OtbmError::UnexpectedNodeType(marker, self.pos));
        }
        let type_byte = self.raw_byte()?;
        NodeType::try_from(type_byte).map_err(|_| OtbmError::UnknownNodeType(type_byte, self.pos))
    }

    /// Read a node end marker.
    fn read_node_end(&mut self) -> Result<(), OtbmError> {
        let marker = self.raw_byte()?;
        if marker != NODE_END {
            return Err(OtbmError::ParseError {
                offset: self.pos,
                message: format!("expected NODE_END (0xFF), got {:#04x}", marker),
            });
        }
        Ok(())
    }

    /// Check if at node end.
    fn is_node_end(&self) -> Result<bool, OtbmError> {
        Ok(self.peek()? == NODE_END)
    }
}

// TryFrom<u8> for NodeType lives in otbforge-models (orphan rule)

// ---------------------------------------------------------------------------
// OTBMWriter
// ---------------------------------------------------------------------------

/// Serialises a `MapData` into OTBM v2 or v3 binary format.
///
/// Usage:
/// ```ignore
/// let writer = OTBMWriter::new(&map_data);
/// let bytes = writer.write();
/// ```
pub struct OTBMWriter<'a> {
    map_data: &'a MapData,
}

impl<'a> OTBMWriter<'a> {
    /// Create a new writer for the given map data.
    pub fn new(map_data: &'a MapData) -> Self {
        Self { map_data }
    }

    // ----- Item attribute writing -----

    fn write_item_attributes(w: &mut BinaryWriter, item: &ItemData) {
        if item.count > 0 {
            w.raw_byte(Attr::Count as u8);
            w.escaped_byte(item.count);
        }
        if item.action_id > 0 {
            w.raw_byte(Attr::ActionId as u8);
            w.u16(item.action_id);
        }
        if item.unique_id > 0 {
            w.raw_byte(Attr::UniqueId as u8);
            w.u16(item.unique_id);
        }
        if !item.text.is_empty() {
            w.raw_byte(Attr::Text as u8);
            w.string(&item.text);
        }
        if !item.description.is_empty() {
            w.raw_byte(Attr::Desc as u8);
            w.string(&item.description);
        }
        if item.charges > 0 {
            w.raw_byte(Attr::Charges as u8);
            w.u16(item.charges);
        }
        if item.rune_charges > 0 {
            w.raw_byte(Attr::RuneCharges as u8);
            w.escaped_byte(item.rune_charges);
        }
        if item.house_door_id > 0 {
            w.raw_byte(Attr::Housedoorid as u8);
            w.escaped_byte(item.house_door_id);
        }
        if item.depot_id > 0 {
            w.raw_byte(Attr::DepotId as u8);
            w.u16(item.depot_id);
        }
        if let Some(ref dest) = item.teleport_dest {
            w.raw_byte(Attr::TeleDest as u8);
            w.u16(dest.x);
            w.u16(dest.y);
            w.escaped_byte(dest.z);
        }
        if item.duration > 0 {
            w.raw_byte(Attr::Duration as u8);
            w.u32(item.duration);
        }
        if item.decay_state > 0 {
            w.raw_byte(Attr::DecayingState as u8);
            w.escaped_byte(item.decay_state);
        }
        if item.written_date > 0 {
            w.raw_byte(Attr::Writtendate as u8);
            w.u32(item.written_date);
        }
        if !item.written_by.is_empty() {
            w.raw_byte(Attr::Writtenby as u8);
            w.string(&item.written_by);
        }
        if item.sleeper_guid > 0 {
            w.raw_byte(Attr::Sleeperguid as u8);
            w.u32(item.sleeper_guid);
        }
        if item.sleep_start > 0 {
            w.raw_byte(Attr::Sleepstart as u8);
            w.u32(item.sleep_start);
        }
    }

    fn write_item_compact(w: &mut BinaryWriter, item: &ItemData) {
        w.raw_byte(Attr::Item as u8);
        w.u16(item.id);
    }

    fn write_item_node(w: &mut BinaryWriter, item: &ItemData) {
        w.start_node(NodeType::Item);
        w.u16(item.id);
        Self::write_item_attributes(w, item);
        for child in &item.children {
            Self::write_item_node(w, child);
        }
        w.end_node();
    }

    // ----- Tile writing -----

    fn write_tile(w: &mut BinaryWriter, tile: &TileData, base_x: u16, base_y: u16) {
        let is_house = tile.house_id > 0;
        w.start_node(if is_house {
            NodeType::HouseTile
        } else {
            NodeType::Tile
        });

        w.escaped_byte((tile.x - base_x) as u8);
        w.escaped_byte((tile.y - base_y) as u8);

        if is_house {
            w.u32(tile.house_id);
        }

        if !tile.flags.is_empty() {
            w.raw_byte(Attr::TileFlags as u8);
            w.u32(tile.flags.bits());
        }

        // Ground item — compact
        if tile.ground_id > 0 {
            Self::write_item_compact(w, &ItemData::new(tile.ground_id));
        }

        // Stacked / container items — full nodes
        for item in &tile.items {
            Self::write_item_node(w, item);
        }

        w.end_node();
    }

    // ----- Tile areas (256×256 chunks per Z) -----

    fn write_tile_areas(w: &mut BinaryWriter, map: &MapData) {
        // Group tiles by (bx, by, z) where bx = x & 0xFF00, by = y & 0xFF00
        let mut areas: BTreeMap<(u16, u16, u8), Vec<&TileData>> = BTreeMap::new();
        for tile in &map.tiles {
            let bx = tile.x & 0xFF00;
            let by = tile.y & 0xFF00;
            areas.entry((bx, by, tile.z)).or_default().push(tile);
        }

        for (&(bx, by, z), tiles) in &areas {
            w.start_node(NodeType::TileArea);
            w.u16(bx);
            w.u16(by);
            w.escaped_byte(z);
            for tile in tiles {
                Self::write_tile(w, tile, bx, by);
            }
            w.end_node();
        }
    }

    // ----- Towns -----

    fn write_towns(w: &mut BinaryWriter, map: &MapData) {
        w.start_node(NodeType::Towns);
        for town in &map.towns {
            w.start_node(NodeType::Town);
            w.u32(town.id);
            w.string(&town.name);
            w.u16(town.temple.x);
            w.u16(town.temple.y);
            w.escaped_byte(town.temple.z);
            w.end_node();
        }
        w.end_node();
    }

    // ----- Waypoints -----

    fn write_waypoints(w: &mut BinaryWriter, map: &MapData) {
        if map.waypoints.is_empty() {
            return;
        }
        w.start_node(NodeType::Waypoints);
        for wp in &map.waypoints {
            w.start_node(NodeType::Waypoint);
            w.string(&wp.name);
            w.u16(wp.pos.x);
            w.u16(wp.pos.y);
            w.escaped_byte(wp.pos.z);
            w.end_node();
        }
        w.end_node();
    }

    // ----- Spawns -----

    fn write_spawns(w: &mut BinaryWriter, map: &MapData) {
        if map.spawns.is_empty() {
            return;
        }
        w.start_node(NodeType::Spawns);
        for spawn in &map.spawns {
            w.start_node(NodeType::SpawnArea);
            w.u16(spawn.x);
            w.u16(spawn.y);
            w.escaped_byte(spawn.z);
            w.u32(spawn.radius);
            for monster in &spawn.monsters {
                w.start_node(NodeType::Monster);
                w.string(&monster.name);
                w.u16(monster.offset_x);
                w.u16(monster.offset_y);
                w.string(""); // spawn name (empty in OTBM)
                w.end_node();
            }
            w.end_node();
        }
        w.end_node();
    }

    // ----- NPC Spawns -----

    fn write_npc_spawns(w: &mut BinaryWriter, map: &MapData) {
        if map.npc_spawns.is_empty() {
            return;
        }
        // NPCs are encoded as SPAWN_AREA / MONSTER nodes (OTBM convention)
        w.start_node(NodeType::Spawns);
        for npc in &map.npc_spawns {
            w.start_node(NodeType::SpawnArea);
            w.u16(npc.x);
            w.u16(npc.y);
            w.escaped_byte(npc.z);
            w.u32(1); // radius
            w.start_node(NodeType::Monster);
            w.string(&npc.npc_name);
            w.u16(0); // offset x
            w.u16(0); // offset y
            w.string(""); // spawn name
            w.end_node();
            w.end_node();
        }
        w.end_node();
    }

    // ----- External file attributes -----

    fn write_ext_files(w: &mut BinaryWriter, map: &MapData) {
        if !map.ext_spawn_file.is_empty() {
            w.raw_byte(Attr::ExtSpawnFile as u8);
            w.string(&map.ext_spawn_file);
        }
        if !map.ext_house_file.is_empty() {
            w.raw_byte(Attr::ExtHouseFile as u8);
            w.string(&map.ext_house_file);
        }
        if !map.ext_spawn_npc_file.is_empty() {
            w.raw_byte(Attr::ExtSpawnNpcFile as u8);
            w.string(&map.ext_spawn_npc_file);
        }
    }

    // ----- Public API -----

    /// Serialise the map and return raw bytes.
    pub fn write(&self) -> Vec<u8> {
        let mut w = BinaryWriter::new();

        // Magic
        w.buf.extend_from_slice(OTBM_MAGIC);

        // Root node
        w.start_node(NodeType::RootV1);

        // Header
        w.u32(self.map_data.otbm_version);
        w.u16(self.map_data.width);
        w.u16(self.map_data.height);
        w.u32(self.map_data.otb_major_version);
        w.u32(self.map_data.otb_minor_version);

        // MAP_DATA child
        w.start_node(NodeType::MapData);

        // Description
        w.raw_byte(Attr::Description as u8);
        w.string(&self.map_data.description);

        // External file refs
        Self::write_ext_files(&mut w, self.map_data);

        // Content
        Self::write_tile_areas(&mut w, self.map_data);
        Self::write_towns(&mut w, self.map_data);
        Self::write_waypoints(&mut w, self.map_data);
        Self::write_spawns(&mut w, self.map_data);
        Self::write_npc_spawns(&mut w, self.map_data);

        w.end_node(); // MAP_DATA
        w.end_node(); // ROOTV1

        w.into_bytes()
    }

    /// Write the map to a file, return byte count.
    pub fn save(&self, path: &std::path::Path) -> Result<usize, OtbmError> {
        let data = self.write();
        std::fs::write(path, &data)?;
        Ok(data.len())
    }
}

// ---------------------------------------------------------------------------
// OTBMReader
// ---------------------------------------------------------------------------

/// Parses OTBM v2/v3 binary data into a `MapData`.
///
/// Usage:
/// ```ignore
/// let reader = OTBMReader::new(&bytes)?;
/// let map_data = reader.read()?;
/// ```
pub struct OTBMReader<'a> {
    reader: BinaryReader<'a>,
}

impl<'a> OTBMReader<'a> {
    /// Create a new reader for the given byte slice.
    pub fn new(data: &'a [u8]) -> Result<Self, OtbmError> {
        // Validate magic
        if data.len() < 4 || &data[0..4] != OTBM_MAGIC {
            let got = data.get(0..4).unwrap_or(&[]).to_vec();
            return Err(OtbmError::InvalidMagic(got));
        }
        // Skip past magic
        let reader = BinaryReader::new(&data[4..]);
        Ok(Self { reader })
    }

    // ----- Item parsing -----

    fn parse_item(&mut self) -> Result<ItemData, OtbmError> {
        let node_type = self.reader.read_node_start()?;
        if node_type != NodeType::Item {
            return Err(OtbmError::UnexpectedNodeType(
                node_type as u8,
                self.reader.offset(),
            ));
        }

        let id = self.reader.read_u16()?;
        let mut item = ItemData::new(id);

        // Parse attributes and children until NODE_END
        while !self.reader.is_node_end()? {
            let attr = self.reader.raw_byte()?;
            let attr_enum = Attr::try_from(attr);

            match attr_enum {
                Ok(Attr::Count) => item.count = self.reader.escaped_byte()?,
                Ok(Attr::ActionId) => item.action_id = self.reader.read_u16()?,
                Ok(Attr::UniqueId) => item.unique_id = self.reader.read_u16()?,
                Ok(Attr::Text) => item.text = self.reader.read_string()?,
                Ok(Attr::Desc) => item.description = self.reader.read_string()?,
                Ok(Attr::Charges) => item.charges = self.reader.read_u16()?,
                Ok(Attr::RuneCharges) => item.rune_charges = self.reader.escaped_byte()?,
                Ok(Attr::Housedoorid) => item.house_door_id = self.reader.escaped_byte()?,
                Ok(Attr::DepotId) => item.depot_id = self.reader.read_u16()?,
                Ok(Attr::TeleDest) => {
                    let x = self.reader.read_u16()?;
                    let y = self.reader.read_u16()?;
                    let z = self.reader.escaped_byte()?;
                    item.teleport_dest = Some(Position::new(x, y, z));
                }
                Ok(Attr::Duration) => item.duration = self.reader.read_u32()?,
                Ok(Attr::DecayingState) => item.decay_state = self.reader.escaped_byte()?,
                Ok(Attr::Writtendate) => item.written_date = self.reader.read_u32()?,
                Ok(Attr::Writtenby) => item.written_by = self.reader.read_string()?,
                Ok(Attr::Sleeperguid) => item.sleeper_guid = self.reader.read_u32()?,
                Ok(Attr::Sleepstart) => item.sleep_start = self.reader.read_u32()?,
                _ if attr == NODE_START => {
                    // Child item node — put back and parse recursively
                    self.reader.pos -= 1;
                    let child = self.parse_item()?;
                    item.children.push(child);
                }
                Ok(other) => {
                    // Skip unknown attribute types that we recognise but don't handle
                    return Err(OtbmError::UnknownAttribute(
                        attr,
                        self.reader.offset(),
                    ));
                }
                Err(_) => {
                    return Err(OtbmError::UnknownAttribute(
                        attr,
                        self.reader.offset(),
                    ));
                }
            }
        }

        self.reader.read_node_end()?;
        Ok(item)
    }

    // ----- Tile parsing -----

    fn parse_tile(&mut self, base_x: u16, base_y: u16) -> Result<TileData, OtbmError> {
        let node_type = self.reader.read_node_start()?;
        let is_house = match node_type {
            NodeType::Tile => false,
            NodeType::HouseTile => true,
            other => {
                return Err(OtbmError::UnexpectedNodeType(
                    other as u8,
                    self.reader.offset(),
                ));
            }
        };

        let local_x = self.reader.escaped_byte()?;
        let local_y = self.reader.escaped_byte()?;
        let x = base_x.wrapping_add(local_x as u16);
        let y = base_y.wrapping_add(local_y as u16);

        let mut house_id: u32 = 0;
        if is_house {
            house_id = self.reader.read_u32()?;
        }

        let mut flags = TileFlags::NONE;
        let mut ground_id: u16 = 0;
        let mut items: Vec<ItemData> = Vec::new();

        while !self.reader.is_node_end()? {
            let attr = self.reader.raw_byte()?;

            match attr {
                a if a == Attr::TileFlags as u8 => {
                    flags = TileFlags::from_bits_truncate(self.reader.read_u32()?);
                }
                a if a == Attr::Item as u8 => {
                    // Compact ground item
                    ground_id = self.reader.read_u16()?;
                }
                _ if attr == NODE_START => {
                    // Full item node — put back and parse
                    self.reader.pos -= 1;
                    let item = self.parse_item()?;
                    items.push(item);
                }
                other => {
                    return Err(OtbmError::UnknownAttribute(
                        other,
                        self.reader.offset(),
                    ));
                }
            }
        }

        self.reader.read_node_end()?;
        Ok(TileData {
            x,
            y,
            z: 0, // will be set by caller from TILE_AREA z
            ground_id,
            items,
            flags,
            house_id,
        })
    }

    // ----- Public API -----

    /// Parse the OTBM data into a `MapData`.
    pub fn read(&mut self) -> Result<MapData, OtbmError> {
        // Root node
        let root_type = self.reader.read_node_start()?;
        if root_type != NodeType::RootV1 {
            return Err(OtbmError::UnexpectedNodeType(
                root_type as u8,
                self.reader.offset(),
            ));
        }

        // Header
        let otbm_version = self.reader.read_u32()?;
        let width = self.reader.read_u16()?;
        let height = self.reader.read_u16()?;
        let otb_major_version = self.reader.read_u32()?;
        let otb_minor_version = self.reader.read_u32()?;

        if !(1..=3).contains(&otbm_version) {
            return Err(OtbmError::InvalidVersion(otbm_version));
        }

        let mut map = MapData {
            width,
            height,
            otbm_version,
            otb_major_version,
            otb_minor_version,
            ..MapData::new()
        };

        // MAP_DATA child
        let map_data_type = self.reader.read_node_start()?;
        if map_data_type != NodeType::MapData {
            return Err(OtbmError::UnexpectedNodeType(
                map_data_type as u8,
                self.reader.offset(),
            ));
        }

        // Parse MAP_DATA contents (description, ext files, tile areas, towns, etc.)
        while !self.reader.is_node_end()? {
            let attr_or_node = self.reader.peek()?;

            if attr_or_node == NODE_START {
                // It's a child node
                let child_type = self.reader.read_node_start()?;

                match child_type {
                    NodeType::TileArea => {
                        let base_x = self.reader.read_u16()?;
                        let base_y = self.reader.read_u16()?;
                        let z = self.reader.escaped_byte()?;

                        // Parse tiles in this area
                        while !self.reader.is_node_end()? {
                            if self.reader.peek()? == NODE_START {
                                let peek_type = NodeType::try_from(self.reader.data[self.reader.pos + 1]);
                                if let Ok(NodeType::Tile) | Ok(NodeType::HouseTile) = peek_type {
                                    let mut tile = self.parse_tile(base_x, base_y)?;
                                    tile.z = z;
                                    map.tiles.push(tile);
                                } else {
                                    // Skip unknown node
                                    self.reader.read_node_start()?;
                                    self.skip_node()?;
                                }
                            } else {
                                // Skip unknown attribute-like byte
                                self.reader.raw_byte()?;
                            }
                        }
                        self.reader.read_node_end()?;
                    }
                    NodeType::Towns => {
                        while !self.reader.is_node_end()? {
                            if self.reader.is_node_start()? {
                                let town_type = self.reader.read_node_start()?;
                                if town_type != NodeType::Town {
                                    return Err(OtbmError::UnexpectedNodeType(
                                        town_type as u8,
                                        self.reader.offset(),
                                    ));
                                }
                                let id = self.reader.read_u32()?;
                                let name = self.reader.read_string()?;
                                let tx = self.reader.read_u16()?;
                                let ty = self.reader.read_u16()?;
                                let tz = self.reader.escaped_byte()?;
                                map.towns.push(TownData::new(
                                    id,
                                    name,
                                    Position::new(tx, ty, tz),
                                ));
                                self.reader.read_node_end()?;
                            } else {
                                self.reader.raw_byte()?;
                            }
                        }
                        self.reader.read_node_end()?;
                    }
                    NodeType::Waypoints => {
                        while !self.reader.is_node_end()? {
                            if self.reader.is_node_start()? {
                                let wp_type = self.reader.read_node_start()?;
                                if wp_type != NodeType::Waypoint {
                                    return Err(OtbmError::UnexpectedNodeType(
                                        wp_type as u8,
                                        self.reader.offset(),
                                    ));
                                }
                                let name = self.reader.read_string()?;
                                let wx = self.reader.read_u16()?;
                                let wy = self.reader.read_u16()?;
                                let wz = self.reader.escaped_byte()?;
                                map.waypoints.push(WaypointData::new(
                                    name,
                                    Position::new(wx, wy, wz),
                                ));
                                self.reader.read_node_end()?;
                            } else {
                                self.reader.raw_byte()?;
                            }
                        }
                        self.reader.read_node_end()?;
                    }
                    NodeType::Spawns => {
                        while !self.reader.is_node_end()? {
                            if self.reader.is_node_start()? {
                                let spawn_type = self.reader.read_node_start()?;
                                if spawn_type != NodeType::SpawnArea {
                                    self.skip_node()?;
                                    continue;
                                }

                                let sx = self.reader.read_u16()?;
                                let sy = self.reader.read_u16()?;
                                let sz = self.reader.escaped_byte()?;
                                let radius = self.reader.read_u32()?;

                                let mut spawn = SpawnData::new(sx, sy, sz, radius);

                                // Parse monsters
                                while !self.reader.is_node_end()? {
                                    if self.reader.is_node_start()? {
                                        let monster_type = self.reader.read_node_start()?;
                                        if monster_type != NodeType::Monster {
                                            self.skip_node()?;
                                            continue;
                                        }
                                        let name = self.reader.read_string()?;
                                        let ox = self.reader.read_u16()?;
                                        let oy = self.reader.read_u16()?;
                                        let _spawn_name = self.reader.read_string()?;
                                        spawn.monsters.push(MonsterEntry {
                                            name,
                                            offset_x: ox,
                                            offset_y: oy,
                                        });
                                        self.reader.read_node_end()?;
                                    } else {
                                        self.reader.raw_byte()?;
                                    }
                                }
                                self.reader.read_node_end()?;
                                map.spawns.push(spawn);
                            } else {
                                self.reader.raw_byte()?;
                            }
                        }
                        self.reader.read_node_end()?;
                    }
                    other => {
                        // Skip unknown top-level nodes
                        self.skip_node()?;
                    }
                }
            } else {
                // Attribute on MAP_DATA
                let attr = self.reader.raw_byte()?;
                match attr {
                    a if a == Attr::Description as u8 => {
                        map.description = self.reader.read_string()?;
                    }
                    a if a == Attr::ExtSpawnFile as u8 => {
                        map.ext_spawn_file = self.reader.read_string()?;
                    }
                    a if a == Attr::ExtHouseFile as u8 => {
                        map.ext_house_file = self.reader.read_string()?;
                    }
                    a if a == Attr::ExtSpawnNpcFile as u8 => {
                        map.ext_spawn_npc_file = self.reader.read_string()?;
                    }
                    other => {
                        return Err(OtbmError::UnknownAttribute(
                            other,
                            self.reader.offset(),
                        ));
                    }
                }
            }
        }

        self.reader.read_node_end()?; // MAP_DATA
        self.reader.read_node_end()?; // ROOTV1

        Ok(map)
    }

    /// Skip an already-started node (reader has consumed the NODE_START + type byte).
    fn skip_node(&mut self) -> Result<(), OtbmError> {
        let mut depth = 1u32;
        while depth > 0 {
            let b = self.reader.raw_byte()?;
            match b {
                NODE_START => {
                    self.reader.raw_byte()?; // skip type byte
                    depth += 1;
                }
                NODE_END => {
                    depth -= 1;
                }
                _ => {}
            }
        }
        Ok(())
    }
}

// TryFrom<u8> for Attr lives in otbforge-models (orphan rule)

// ---------------------------------------------------------------------------
// Convenience functions
// ---------------------------------------------------------------------------

/// Serialise a `MapData` to OTBM bytes.
pub fn write_otbm(map: &MapData) -> Vec<u8> {
    OTBMWriter::new(map).write()
}

/// Parse OTBM bytes into a `MapData`.
pub fn read_otbm(data: &[u8]) -> Result<MapData, OtbmError> {
    let mut reader = OTBMReader::new(data)?;
    reader.read()
}

// ===========================================================================
// Tests
// ===========================================================================

#[cfg(test)]
mod tests {
    use super::*;

    // ----- Roundtrip tests -----

    #[test]
    fn test_roundtrip_empty_map() {
        let map = MapData::with_dimensions(256, 256);
        let bytes = write_otbm(&map);
        let parsed = read_otbm(&bytes).unwrap();
        assert_eq!(parsed.width, 256);
        assert_eq!(parsed.height, 256);
        assert_eq!(parsed.description, "Generated Map");
        assert_eq!(parsed.otbm_version, 2);
        assert_eq!(parsed.otb_major_version, 2);
        assert_eq!(parsed.otb_minor_version, 7);
    }

    #[test]
    fn test_roundtrip_with_tiles() {
        let mut map = MapData::with_dimensions(512, 512);
        map.add_tile(100, 200, 7, tiles::GRASS);
        map.add_tile(101, 200, 7, tiles::DIRT);

        let bytes = write_otbm(&map);
        let parsed = read_otbm(&bytes).unwrap();
        assert_eq!(parsed.tiles.len(), 2);
        assert_eq!(parsed.tiles[0].x, 100);
        assert_eq!(parsed.tiles[0].y, 200);
        assert_eq!(parsed.tiles[0].z, 7);
        assert_eq!(parsed.tiles[0].ground_id, tiles::GRASS);
        assert_eq!(parsed.tiles[1].ground_id, tiles::DIRT);
    }

    #[test]
    fn test_roundtrip_with_towns() {
        let mut map = MapData::with_dimensions(512, 512);
        map.add_town(1, "Thais", Position::new(100, 200, 7));
        map.add_town(2, "Carlin", Position::new(300, 400, 7));

        let bytes = write_otbm(&map);
        let parsed = read_otbm(&bytes).unwrap();
        assert_eq!(parsed.towns.len(), 2);
        assert_eq!(parsed.towns[0].id, 1);
        assert_eq!(parsed.towns[0].name, "Thais");
        assert_eq!(parsed.towns[1].name, "Carlin");
    }

    #[test]
    fn test_roundtrip_with_waypoints() {
        let mut map = MapData::with_dimensions(512, 512);
        map.add_waypoint("Temple", Position::new(100, 200, 7));
        map.add_waypoint("Depot", Position::new(150, 250, 7));

        let bytes = write_otbm(&map);
        let parsed = read_otbm(&bytes).unwrap();
        assert_eq!(parsed.waypoints.len(), 2);
        assert_eq!(parsed.waypoints[0].name, "Temple");
    }

    #[test]
    fn test_roundtrip_with_spawns() {
        let mut map = MapData::with_dimensions(512, 512);
        map.add_spawn(100, 200, 7, 10);
        map.spawns[0].monsters.push(MonsterEntry {
            name: "Rat".into(),
            offset_x: 1,
            offset_y: 2,
        });

        let bytes = write_otbm(&map);
        let parsed = read_otbm(&bytes).unwrap();
        assert_eq!(parsed.spawns.len(), 1);
        assert_eq!(parsed.spawns[0].radius, 10);
        assert_eq!(parsed.spawns[0].monsters.len(), 1);
        assert_eq!(parsed.spawns[0].monsters[0].name, "Rat");
        assert_eq!(parsed.spawns[0].monsters[0].offset_x, 1);
        assert_eq!(parsed.spawns[0].monsters[0].offset_y, 2);
    }

    #[test]
    fn test_roundtrip_with_npc_spawns() {
        let mut map = MapData::with_dimensions(512, 512);
        map.add_npc_spawn(100, 200, 7, "The Guide");

        let bytes = write_otbm(&map);
        let parsed = read_otbm(&bytes).unwrap();
        // NPC spawns are read back as regular spawns (MONSTER convention)
        assert_eq!(parsed.spawns.len(), 1);
        assert_eq!(parsed.spawns[0].monsters[0].name, "The Guide");
    }

    #[test]
    fn test_roundtrip_house_tile() {
        let mut map = MapData::with_dimensions(512, 512);
        map.add_tile_full(50, 60, 7, tiles::FLOOR_WOOD, TileFlags::NONE, 42);

        let bytes = write_otbm(&map);
        let parsed = read_otbm(&bytes).unwrap();
        assert_eq!(parsed.tiles.len(), 1);
        assert_eq!(parsed.tiles[0].house_id, 42);
        assert_eq!(parsed.tiles[0].ground_id, tiles::FLOOR_WOOD);
    }

    #[test]
    fn test_roundtrip_tile_flags() {
        let mut map = MapData::with_dimensions(512, 512);
        map.add_tile_full(
            100,
            200,
            7,
            tiles::GRASS,
            TileFlags::PROTECTIONZONE | TileFlags::NOPVPZONE,
            0,
        );

        let bytes = write_otbm(&map);
        let parsed = read_otbm(&bytes).unwrap();
        assert!(parsed.tiles[0]
            .flags
            .contains(TileFlags::PROTECTIONZONE));
        assert!(parsed.tiles[0].flags.contains(TileFlags::NOPVPZONE));
    }

    #[test]
    fn test_roundtrip_with_items() {
        let mut map = MapData::with_dimensions(512, 512);
        map.add_tile(100, 200, 7, tiles::GRASS);
        map.tiles[0]
            .items
            .push(ItemData::new(tiles::CHEST).with_count(5));

        let bytes = write_otbm(&map);
        let parsed = read_otbm(&bytes).unwrap();
        assert_eq!(parsed.tiles[0].items.len(), 1);
        assert_eq!(parsed.tiles[0].items[0].id, tiles::CHEST);
        assert_eq!(parsed.tiles[0].items[0].count, 5);
    }

    #[test]
    fn test_roundtrip_nested_items() {
        let mut map = MapData::with_dimensions(512, 512);
        map.add_tile(100, 200, 7, tiles::GRASS);
        let container = ItemData::new(tiles::CHEST).with_child(ItemData::new(2160).with_count(10));
        map.tiles[0].items.push(container);

        let bytes = write_otbm(&map);
        let parsed = read_otbm(&bytes).unwrap();
        assert_eq!(parsed.tiles[0].items.len(), 1);
        assert_eq!(parsed.tiles[0].items[0].children.len(), 1);
        assert_eq!(parsed.tiles[0].items[0].children[0].id, 2160);
        assert_eq!(parsed.tiles[0].items[0].children[0].count, 10);
    }

    #[test]
    fn test_roundtrip_v3() {
        let map = MapData::new_v3();
        let bytes = write_otbm(&map);
        let parsed = read_otbm(&bytes).unwrap();
        assert_eq!(parsed.otbm_version, 3);
        assert_eq!(parsed.otb_major_version, 3);
        assert_eq!(parsed.otb_minor_version, 12);
    }

    #[test]
    fn test_roundtrip_multiple_z_levels() {
        let mut map = MapData::with_dimensions(512, 512);
        map.add_tile(100, 200, 7, tiles::GRASS);
        map.add_tile(100, 200, 6, tiles::DIRT);
        map.add_tile(100, 200, 8, tiles::SAND);

        let bytes = write_otbm(&map);
        let parsed = read_otbm(&bytes).unwrap();
        assert_eq!(parsed.tiles.len(), 3);
        let mut zs: Vec<u8> = parsed.tiles.iter().map(|t| t.z).collect();
        zs.sort();
        assert_eq!(zs, vec![6, 7, 8]);
    }

    #[test]
    fn test_roundtrip_large_map() {
        let mut map = MapData::with_dimensions(2048, 2048);
        // Add tiles across different areas
        map.add_tile(10, 20, 7, tiles::GRASS);
        map.add_tile(300, 400, 7, tiles::GRASS);
        map.add_tile(1000, 1500, 7, tiles::DIRT);

        let bytes = write_otbm(&map);
        let parsed = read_otbm(&bytes).unwrap();
        assert_eq!(parsed.tiles.len(), 3);
    }

    // ----- Binary format tests -----

    #[test]
    fn test_magic_bytes() {
        let map = MapData::new();
        let bytes = write_otbm(&map);
        assert_eq!(&bytes[0..4], OTBM_MAGIC);
    }

    #[test]
    fn test_escaping_high_bytes() {
        // Verify that bytes >= 0xFD are properly escaped
        let mut map = MapData::with_dimensions(512, 512);
        // Put a tile at a position that will exercise high-byte escaping
        map.add_tile(0xFF, 0xFF, 7, tiles::GRASS);

        let bytes = write_otbm(&map);
        // Should not panic and should roundtrip
        let parsed = read_otbm(&bytes).unwrap();
        assert_eq!(parsed.tiles[0].x, 0xFF);
        assert_eq!(parsed.tiles[0].y, 0xFF);
    }

    // ----- Error tests -----

    #[test]
    fn test_invalid_magic() {
        let bad_data = vec![0x00, 0x00, 0x00, 0x00, 0x01, 0x01, 0x02, 0x02, 0xFF];
        let result = read_otbm(&bad_data);
        assert!(result.is_err());
        match result.unwrap_err() {
            OtbmError::InvalidMagic(_) => {}
            other => panic!("expected InvalidMagic, got {}", other),
        }
    }

    #[test]
    fn test_truncated_data() {
        let data = b"OTBM".to_vec();
        let result = read_otbm(&data);
        assert!(result.is_err());
    }

    #[test]
    fn test_empty_data() {
        let result = read_otbm(&[]);
        assert!(result.is_err());
    }

    // ----- BinaryWriter unit tests -----

    #[test]
    fn test_binary_writer_raw_byte() {
        let mut w = BinaryWriter::new();
        w.raw_byte(0x42);
        assert_eq!(w.into_bytes(), vec![0x42]);
    }

    #[test]
    fn test_binary_writer_escaped_byte_low() {
        let mut w = BinaryWriter::new();
        w.escaped_byte(0x42);
        assert_eq!(w.into_bytes(), vec![0x42]);
    }

    #[test]
    fn test_binary_writer_escaped_byte_high() {
        let mut w = BinaryWriter::new();
        w.escaped_byte(0xFE);
        assert_eq!(w.into_bytes(), vec![0xFD, 0xFE]);
    }

    #[test]
    fn test_binary_writer_escaped_byte_escape_itself() {
        let mut w = BinaryWriter::new();
        w.escaped_byte(0xFD);
        assert_eq!(w.into_bytes(), vec![0xFD, 0xFD]);
    }

    #[test]
    fn test_binary_writer_escaped_byte_0xff() {
        let mut w = BinaryWriter::new();
        w.escaped_byte(0xFF);
        assert_eq!(w.into_bytes(), vec![0xFD, 0xFF]);
    }

    #[test]
    fn test_binary_writer_u16() {
        let mut w = BinaryWriter::new();
        w.u16(0x0102);
        assert_eq!(w.into_bytes(), vec![0x02, 0x01]);
    }

    #[test]
    fn test_binary_writer_u16_high() {
        let mut w = BinaryWriter::new();
        w.u16(0xFEFF);
        // 0xFEFF in LE is [0xFF, 0xFE], both need escaping
        assert_eq!(w.into_bytes(), vec![0xFD, 0xFF, 0xFD, 0xFE]);
    }

    #[test]
    fn test_binary_writer_u32() {
        let mut w = BinaryWriter::new();
        w.u32(0x01020304);
        assert_eq!(w.into_bytes(), vec![0x04, 0x03, 0x02, 0x01]);
    }

    #[test]
    fn test_binary_writer_string() {
        let mut w = BinaryWriter::new();
        w.string("hi");
        // u16 len = 2, then 'h', 'i'
        assert_eq!(w.into_bytes(), vec![0x02, 0x00, b'h', b'i']);
    }

    #[test]
    fn test_binary_writer_string_empty() {
        let mut w = BinaryWriter::new();
        w.string("");
        assert_eq!(w.into_bytes(), vec![0x00, 0x00]);
    }

    #[test]
    fn test_binary_writer_node() {
        let mut w = BinaryWriter::new();
        w.start_node(NodeType::TileArea);
        w.end_node();
        assert_eq!(
            w.into_bytes(),
            vec![NODE_START, NodeType::TileArea as u8, NODE_END]
        );
    }

    // ----- BinaryReader unit tests -----

    #[test]
    fn test_binary_reader_raw_byte() {
        let mut r = BinaryReader::new(&[0x42, 0x43]);
        assert_eq!(r.raw_byte().unwrap(), 0x42);
        assert_eq!(r.raw_byte().unwrap(), 0x43);
    }

    #[test]
    fn test_binary_reader_escaped_byte_low() {
        let mut r = BinaryReader::new(&[0x42]);
        assert_eq!(r.escaped_byte().unwrap(), 0x42);
    }

    #[test]
    fn test_binary_reader_escaped_byte_high() {
        let mut r = BinaryReader::new(&[0xFD, 0xFE]);
        assert_eq!(r.escaped_byte().unwrap(), 0xFE);
    }

    #[test]
    fn test_binary_reader_u16() {
        let mut r = BinaryReader::new(&[0x02, 0x01]);
        assert_eq!(r.read_u16().unwrap(), 0x0102);
    }

    #[test]
    fn test_binary_reader_u32() {
        let mut r = BinaryReader::new(&[0x04, 0x03, 0x02, 0x01]);
        assert_eq!(r.read_u32().unwrap(), 0x01020304);
    }

    #[test]
    fn test_binary_reader_string() {
        let mut r = BinaryReader::new(&[0x02, 0x00, b'h', b'i']);
        assert_eq!(r.read_string().unwrap(), "hi");
    }

    #[test]
    fn test_binary_reader_string_empty() {
        let mut r = BinaryReader::new(&[0x00, 0x00]);
        assert_eq!(r.read_string().unwrap(), "");
    }

    // ----- Comprehensive roundtrip -----

    #[test]
    fn test_full_map_roundtrip() {
        let mut map = MapData::with_dimensions(1024, 1024);
        map.description = "Full Test Map".into();

        // Tiles with various properties
        map.add_tile_full(100, 200, 7, tiles::GRASS, TileFlags::PROTECTIONZONE, 0);
        map.add_tile_full(
            101,
            200,
            7,
            tiles::FLOOR_WOOD,
            TileFlags::NONE,
            1,
        );
        map.tiles[1].items.push(ItemData::new(tiles::CHEST).with_count(5));
        map.tiles[1].items[0].children.push(ItemData::new(2160).with_count(100));
        map.add_tile(102, 200, 7, tiles::DIRT);

        // Town
        map.add_town(1, "Thais", Position::new(100, 200, 7));

        // Waypoints
        map.add_waypoint("Temple", Position::new(100, 200, 7));
        map.add_waypoint("Depot", Position::new(150, 250, 7));

        // Spawns
        map.add_spawn(100, 200, 7, 15);
        map.spawns[0].monsters.push(MonsterEntry {
            name: "Rat".into(),
            offset_x: 1,
            offset_y: 0,
        });
        map.spawns[0].monsters.push(MonsterEntry {
            name: "Cave Rat".into(),
            offset_x: 2,
            offset_y: 3,
        });

        // NPC
        map.add_npc_spawn(100, 200, 7, "The Oracle");

        // External files
        map.ext_spawn_file = "map spawns.xml".into();

        let bytes = write_otbm(&map);
        let parsed = read_otbm(&bytes).unwrap();

        assert_eq!(parsed.width, 1024);
        assert_eq!(parsed.height, 1024);
        assert_eq!(parsed.description, "Full Test Map");
        assert_eq!(parsed.tiles.len(), 3);
        assert_eq!(parsed.towns.len(), 1);
        assert_eq!(parsed.waypoints.len(), 2);
        // spawns from NPCs are merged into regular spawns
        assert!(parsed.spawns.len() >= 1);
        assert_eq!(parsed.ext_spawn_file, "map spawns.xml");
    }
}
