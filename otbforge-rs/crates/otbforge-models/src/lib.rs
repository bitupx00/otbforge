/*!
OTBForge Models — Core data types for OTBM map representation.

This crate defines all data structures used throughout OTBForge, mirroring the
Python `ai_core/models.py` types. Every type implements `Clone`, `Debug`,
`PartialEq`, and serde's `Serialize`/`Deserialize`. Display implementations
provide human-readable output suitable for logging and CLI display.
*/

use std::collections::HashMap;
use std::fmt;

use serde::{Deserialize, Serialize};

// ---------------------------------------------------------------------------
// File signature & wire constants
// ---------------------------------------------------------------------------

/// OTBM magic bytes: `b"OTBM"`
pub const OTBM_MAGIC: &[u8; 4] = b"OTBM";

/// Node start marker byte.
pub const NODE_START: u8 = 0xFE;

/// Node end marker byte.
pub const NODE_END: u8 = 0xFF;

/// Escape prefix byte.
pub const ESCAPE: u8 = 0xFD;

/// Bytes with value >= this threshold need the ESCAPE prefix on the wire.
pub const ESCAPE_THRESHOLD: u8 = 0xFD;

// ---------------------------------------------------------------------------
// OTBM Node Types
// ---------------------------------------------------------------------------

/// OTBM node type identifiers.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[repr(u8)]
pub enum NodeType {
    RootV1 = 1,
    MapData = 2,
    ItemDef = 3,
    TileArea = 4,
    Tile = 5,
    Item = 6,
    TileSquare = 7,
    TileRef = 8,
    Spawns = 9,
    SpawnArea = 10,
    Monster = 11,
    Towns = 12,
    Town = 13,
    HouseTile = 14,
    Waypoints = 15,
    Waypoint = 16,
}

impl TryFrom<u8> for NodeType {
    type Error = u8;
    fn try_from(value: u8) -> Result<Self, Self::Error> {
        match value {
            1 => Ok(Self::RootV1),
            2 => Ok(Self::MapData),
            3 => Ok(Self::ItemDef),
            4 => Ok(Self::TileArea),
            5 => Ok(Self::Tile),
            6 => Ok(Self::Item),
            7 => Ok(Self::TileSquare),
            8 => Ok(Self::TileRef),
            9 => Ok(Self::Spawns),
            10 => Ok(Self::SpawnArea),
            11 => Ok(Self::Monster),
            12 => Ok(Self::Towns),
            13 => Ok(Self::Town),
            14 => Ok(Self::HouseTile),
            15 => Ok(Self::Waypoints),
            16 => Ok(Self::Waypoint),
            other => Err(other),
        }
    }
}

// ---------------------------------------------------------------------------
// OTBM Attribute IDs
// ---------------------------------------------------------------------------

/// OTBM attribute identifiers.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[repr(u8)]
pub enum Attr {
    Description = 1,
    ExtFile = 2,
    TileFlags = 3,
    ActionId = 4,
    UniqueId = 5,
    Text = 6,
    Desc = 7,
    TeleDest = 8,
    Item = 9,
    DepotId = 10,
    ExtSpawnFile = 11,
    RuneCharges = 12,
    ExtHouseFile = 13,
    Housedoorid = 14,
    Count = 15,
    Duration = 16,
    DecayingState = 17,
    Writtendate = 18,
    Writtenby = 19,
    Sleeperguid = 20,
    Sleepstart = 21,
    Charges = 22,
    ExtSpawnNpcFile = 23,
    Podiumoutfit = 40,
    Tier = 41,
    AttributeMap = 128,
}

impl TryFrom<u8> for Attr {
    type Error = u8;
    fn try_from(value: u8) -> Result<Self, Self::Error> {
        match value {
            1 => Ok(Self::Description),
            2 => Ok(Self::ExtFile),
            3 => Ok(Self::TileFlags),
            4 => Ok(Self::ActionId),
            5 => Ok(Self::UniqueId),
            6 => Ok(Self::Text),
            7 => Ok(Self::Desc),
            8 => Ok(Self::TeleDest),
            9 => Ok(Self::Item),
            10 => Ok(Self::DepotId),
            11 => Ok(Self::ExtSpawnFile),
            12 => Ok(Self::RuneCharges),
            13 => Ok(Self::ExtHouseFile),
            14 => Ok(Self::Housedoorid),
            15 => Ok(Self::Count),
            16 => Ok(Self::Duration),
            17 => Ok(Self::DecayingState),
            18 => Ok(Self::Writtendate),
            19 => Ok(Self::Writtenby),
            20 => Ok(Self::Sleeperguid),
            21 => Ok(Self::Sleepstart),
            22 => Ok(Self::Charges),
            23 => Ok(Self::ExtSpawnNpcFile),
            40 => Ok(Self::Podiumoutfit),
            41 => Ok(Self::Tier),
            128 => Ok(Self::AttributeMap),
            other => Err(other),
        }
    }
}

// ---------------------------------------------------------------------------
// Tile Flags (bitfield)
// ---------------------------------------------------------------------------

bitflags::bitflags! {
    /// Tile flags bitfield, matching the Python `TileFlag` IntFlag.
    ///
    /// These flags are stored as a `u32` in the OTBM binary format.
    #[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
    #[serde(transparent)]
    pub struct TileFlags: u32 {
        /// No flags set.
        const NONE              = 0;
        /// Protection zone — PvP disabled.
        const PROTECTIONZONE    = 1 << 0;
        /// No-summon monster zone.
        const NOSUMMON_MONSTERZONE = 1 << 1;
        /// No-PvP zone.
        const NOPVPZONE         = 1 << 2;
        /// No-logout zone.
        const NOLOGOUTZONE      = 1 << 3;
        /// PvP zone.
        const PVPZONE           = 1 << 4;
        /// No house tile.
        const NOHOUSETILE       = 1 << 5;
        /// Refresh (dynamic / no-save).
        const REFRESH           = 1 << 6;
        /// No-save zone.
        const NOSAVEZONE        = 1 << 7;
        /// Has custom light.
        const HASLIGHT          = 1 << 8;
    }
}

/// Backward-compatible alias.
pub type TileFlag = TileFlags;

impl Default for TileFlags {
    fn default() -> Self {
        Self::NONE
    }
}

impl fmt::Display for TileFlags {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        if self.is_empty() {
            write!(f, "NONE")
        } else {
            let mut parts = Vec::new();
            if self.contains(Self::PROTECTIONZONE) {
                parts.push("PROTECTIONZONE");
            }
            if self.contains(Self::NOSUMMON_MONSTERZONE) {
                parts.push("NOSUMMON_MONSTERZONE");
            }
            if self.contains(Self::NOPVPZONE) {
                parts.push("NOPVPZONE");
            }
            if self.contains(Self::NOLOGOUTZONE) {
                parts.push("NOLOGOUTZONE");
            }
            if self.contains(Self::PVPZONE) {
                parts.push("PVPZONE");
            }
            if self.contains(Self::NOHOUSETILE) {
                parts.push("NOHOUSETILE");
            }
            if self.contains(Self::REFRESH) {
                parts.push("REFRESH");
            }
            if self.contains(Self::NOSAVEZONE) {
                parts.push("NOSAVEZONE");
            }
            if self.contains(Self::HASLIGHT) {
                parts.push("HASLIGHT");
            }
            write!(f, "{}", parts.join("|"))
        }
    }
}

// ---------------------------------------------------------------------------
// Well-known Tile IDs (Tibia 8.0 client)
// ---------------------------------------------------------------------------

/// Well-known ground/item IDs from the Tibia 8.0 client.
pub mod tiles {
    pub const GRASS: u16 = 102;
    pub const DIRT: u16 = 103;
    pub const SAND: u16 = 231;
    pub const WATER: u16 = 490;
    pub const LAVA: u16 = 5967;
    pub const SNOW: u16 = 7731;
    pub const ROCK: u16 = 3638;
    pub const STONE: u16 = 3326;
    pub const STONE_WALL: u16 = 1102;
    pub const BRICK: u16 = 1060;
    pub const WOOD: u16 = 1018;
    pub const FLOOR_WOOD: u16 = 530;
    pub const CARPET_RED: u16 = 5565;
    pub const CLOSED_DOOR: u16 = 5121;
    pub const OPEN_DOOR: u16 = 5122;
    pub const TREE_MIN: u16 = 2700;
    pub const TREE_MAX: u16 = 2708;
    pub const BUSH_1: u16 = 2767;
    pub const BUSH_2: u16 = 2768;
    pub const FLOWER_MIN: u16 = 2740;
    pub const FLOWER_MAX: u16 = 2743;
    pub const CHEST: u16 = 3756;
    pub const DRAWER: u16 = 3757;
    pub const STONE_STAIRS: u16 = 433;
    pub const TELEPORT: u16 = 1387;
}

// ---------------------------------------------------------------------------
// OtbVersion
// ---------------------------------------------------------------------------

/// OTB version preset (major, minor).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub struct OtbVersion {
    pub major: u32,
    pub minor: u32,
}

impl OtbVersion {
    /// Tibia 7.6–8.x (OTBM v2).
    pub const V2_7: Self = Self { major: 2, minor: 7 };
    /// Tibia 10+ (OTBM v3).
    pub const V3_12: Self = Self { major: 3, minor: 12 };
}

impl fmt::Display for OtbVersion {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "OtbVersion(major={}, minor={})", self.major, self.minor)
    }
}

// ===========================================================================
// Data types
// ===========================================================================

/// A 3-D map position (x, y, z).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub struct Position {
    pub x: u16,
    pub y: u16,
    pub z: u8,
}

impl Default for Position {
    fn default() -> Self {
        Self { x: 0, y: 0, z: 0 }
    }
}

impl fmt::Display for Position {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "Position({}, {}, {})", self.x, self.y, self.z)
    }
}

impl Position {
    /// Create a new position.
    pub const fn new(x: u16, y: u16, z: u8) -> Self {
        Self { x, y, z }
    }

    /// Validate that coordinates are within typical OTBM bounds.
    pub fn validate(&self) -> Result<(), String> {
        if self.z > 15 {
            return Err(format!("z out of range: {}", self.z));
        }
        Ok(())
    }
}

// ---------------------------------------------------------------------------

/// A monster entry within a spawn, with name and offset from spawn center.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct MonsterEntry {
    pub name: String,
    pub offset_x: u16,
    pub offset_y: u16,
}

impl fmt::Display for MonsterEntry {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{} (+{}, +{})", self.name, self.offset_x, self.offset_y)
    }
}

// ---------------------------------------------------------------------------

/// An item on a tile, or inside a container.
///
/// Matches the Python `ItemData` dataclass.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ItemData {
    /// Item type ID (OTB item ID).
    pub id: u16,
    /// Stack count / subtype (0 = not set).
    pub count: u8,
    /// Action ID for action items.
    pub action_id: u16,
    /// Unique ID for unique items.
    pub unique_id: u16,
    /// Text attribute.
    pub text: String,
    /// Description attribute.
    pub description: String,
    /// Charges (for chargeable items).
    pub charges: u16,
    /// House door ID.
    pub house_door_id: u8,
    /// Depot ID.
    pub depot_id: u16,
    /// Teleport destination (if this is a teleport).
    pub teleport_dest: Option<Position>,
    /// Duration in milliseconds (v2+).
    pub duration: u32,
    /// Decay state: 0=default, 1=decaying, 2=stopped.
    pub decay_state: u8,
    /// Written date (unix timestamp).
    pub written_date: u32,
    /// Written by (player name).
    pub written_by: String,
    /// Rune charges.
    pub rune_charges: u8,
    /// Sleeper GUID (beds).
    pub sleeper_guid: u32,
    /// Sleep start timestamp.
    pub sleep_start: u32,
    /// Child items (for containers).
    pub children: Vec<ItemData>,
}

impl Default for ItemData {
    fn default() -> Self {
        Self::new(0)
    }
}

impl ItemData {
    /// Create a new item with the given ID and defaults for everything else.
    pub fn new(id: u16) -> Self {
        Self {
            id,
            count: 0,
            action_id: 0,
            unique_id: 0,
            text: String::new(),
            description: String::new(),
            charges: 0,
            house_door_id: 0,
            depot_id: 0,
            teleport_dest: None,
            duration: 0,
            decay_state: 0,
            written_date: 0,
            written_by: String::new(),
            rune_charges: 0,
            sleeper_guid: 0,
            sleep_start: 0,
            children: Vec::new(),
        }
    }

    /// Builder: set count.
    pub fn with_count(mut self, count: u8) -> Self {
        self.count = count;
        self
    }

    /// Builder: set action_id.
    pub fn with_action_id(mut self, action_id: u16) -> Self {
        self.action_id = action_id;
        self
    }

    /// Builder: set unique_id.
    pub fn with_unique_id(mut self, unique_id: u16) -> Self {
        self.unique_id = unique_id;
        self
    }

    /// Builder: set text.
    pub fn with_text(mut self, text: impl Into<String>) -> Self {
        self.text = text.into();
        self
    }

    /// Builder: set description.
    pub fn with_description(mut self, desc: impl Into<String>) -> Self {
        self.description = desc.into();
        self
    }

    /// Builder: set charges.
    pub fn with_charges(mut self, charges: u16) -> Self {
        self.charges = charges;
        self
    }

    /// Builder: add a child item (for containers).
    pub fn with_child(mut self, child: ItemData) -> Self {
        self.children.push(child);
        self
    }

    /// Returns `true` if this item has children.
    pub fn has_children(&self) -> bool {
        !self.children.is_empty()
    }

    /// Compute maximum nesting depth of children tree.
    pub fn container_depth(&self) -> usize {
        if self.children.is_empty() {
            0
        } else {
            1 + self.children.iter().map(|c| c.container_depth()).max().unwrap_or(0)
        }
    }

    /// Validate item fields.
    pub fn validate(&self) -> Result<(), String> {
        if self.id == 0 {
            return Err(format!("item id out of range: {}", self.id));
        }
        if let Some(ref dest) = self.teleport_dest {
            dest.validate()?;
        }
        Ok(())
    }
}

impl fmt::Display for ItemData {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "ItemData(id={}", self.id)?;
        let mut extras = Vec::new();
        if self.count != 0 {
            extras.push(format!("count={}", self.count));
        }
        if self.action_id != 0 {
            extras.push(format!("action_id={}", self.action_id));
        }
        if self.unique_id != 0 {
            extras.push(format!("unique_id={}", self.unique_id));
        }
        if !self.text.is_empty() {
            extras.push(format!("text={:?}", self.text));
        }
        if !self.description.is_empty() {
            extras.push(format!("desc={:?}", self.description));
        }
        if self.charges != 0 {
            extras.push(format!("charges={}", self.charges));
        }
        if self.house_door_id != 0 {
            extras.push(format!("door_id={}", self.house_door_id));
        }
        if self.depot_id != 0 {
            extras.push(format!("depot={}", self.depot_id));
        }
        if let Some(ref dest) = self.teleport_dest {
            extras.push(format!("tele_dest={}", dest));
        }
        if self.duration != 0 {
            extras.push(format!("duration={}", self.duration));
        }
        if !self.children.is_empty() {
            extras.push(format!("children={}", self.children.len()));
        }
        if !extras.is_empty() {
            write!(f, ", {}", extras.join(", "))?;
        }
        write!(f, ")")
    }
}

// ---------------------------------------------------------------------------

/// A single map tile.
///
/// Matches the Python `TileData` dataclass.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct TileData {
    pub x: u16,
    pub y: u16,
    pub z: u8,
    /// Ground item type ID (0 = no ground).
    pub ground_id: u16,
    /// Items on the tile (excluding ground).
    pub items: Vec<ItemData>,
    /// Tile flags.
    pub flags: TileFlags,
    /// House ID (0 = not a house tile).
    pub house_id: u32,
}

impl TileData {
    /// Create a new tile.
    pub fn new(x: u16, y: u16, z: u8, ground_id: u16) -> Self {
        Self {
            x,
            y,
            z,
            ground_id,
            items: Vec::new(),
            flags: TileFlags::NONE,
            house_id: 0,
        }
    }

    /// Builder: add an item to the tile, returning `&mut self` for chaining.
    pub fn with_item(mut self, item: ItemData) -> Self {
        self.items.push(item);
        self
    }

    /// Builder: set tile flags.
    pub fn with_flags(mut self, flags: TileFlags) -> Self {
        self.flags = flags;
        self
    }

    /// Builder: set house ID.
    pub fn with_house_id(mut self, house_id: u32) -> Self {
        self.house_id = house_id;
        self
    }

    /// Validate tile fields.
    pub fn validate(&self) -> Result<(), String> {
        if self.z > 15 {
            return Err(format!("tile z out of range: {}", self.z));
        }
        for item in &self.items {
            item.validate()?;
        }
        Ok(())
    }
}

impl fmt::Display for TileData {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        let mut parts = Vec::new();
        if !self.flags.is_empty() {
            parts.push(format!("flags={:#x}", self.flags.bits()));
        }
        if self.house_id != 0 {
            parts.push(format!("house={}", self.house_id));
        }
        if !self.items.is_empty() {
            parts.push(format!("items={}", self.items.len()));
        }
        if parts.is_empty() {
            write!(
                f,
                "TileData({}, {}, {}, ground={})",
                self.x, self.y, self.z, self.ground_id
            )
        } else {
            write!(
                f,
                "TileData({}, {}, {}, ground={}, {})",
                self.x, self.y, self.z, self.ground_id, parts.join(", ")
            )
        }
    }
}

// ---------------------------------------------------------------------------

/// A town with a temple position (spawn point).
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct TownData {
    /// Town ID.
    pub id: u32,
    /// Town name.
    pub name: String,
    /// Temple position.
    pub temple: Position,
}

impl TownData {
    /// Create a new town.
    pub fn new(id: u32, name: impl Into<String>, temple: Position) -> Self {
        Self {
            id,
            name: name.into(),
            temple,
        }
    }

    /// Validate town fields.
    pub fn validate(&self) -> Result<(), String> {
        if self.id == 0 {
            return Err(format!("town id must be > 0: {}", self.id));
        }
        self.temple.validate()
    }
}

impl fmt::Display for TownData {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(
            f,
            "TownData(id={}, name={:?}, temple={})",
            self.id, self.name, self.temple
        )
    }
}

// ---------------------------------------------------------------------------

/// A named waypoint on the map.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct WaypointData {
    /// Waypoint name.
    pub name: String,
    /// Waypoint position.
    pub pos: Position,
}

impl WaypointData {
    /// Create a new waypoint.
    pub fn new(name: impl Into<String>, pos: Position) -> Self {
        Self {
            name: name.into(),
            pos,
        }
    }

    /// Validate waypoint fields.
    pub fn validate(&self) -> Result<(), String> {
        if self.name.is_empty() {
            return Err("waypoint name must not be empty".into());
        }
        self.pos.validate()
    }
}

impl fmt::Display for WaypointData {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "WaypointData(name={:?}, pos={})", self.name, self.pos)
    }
}

// ---------------------------------------------------------------------------

/// Monster spawn point (centre + radius + monster list).
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct SpawnData {
    /// Center X coordinate.
    pub x: u16,
    /// Center Y coordinate.
    pub y: u16,
    /// Center Z coordinate.
    pub z: u8,
    /// Spawn radius.
    pub radius: u32,
    /// Monsters at this spawn.
    pub monsters: Vec<MonsterEntry>,
}

impl SpawnData {
    /// Create a new spawn.
    pub fn new(x: u16, y: u16, z: u8, radius: u32) -> Self {
        Self {
            x,
            y,
            z,
            radius,
            monsters: Vec::new(),
        }
    }

    /// Builder: add a monster to the spawn.
    pub fn with_monster(mut self, name: impl Into<String>, ox: u16, oy: u16) -> Self {
        self.monsters.push(MonsterEntry {
            name: name.into(),
            offset_x: ox,
            offset_y: oy,
        });
        self
    }

    /// Validate spawn fields.
    pub fn validate(&self) -> Result<(), String> {
        if self.z > 15 {
            return Err(format!("spawn z out of range: {}", self.z));
        }
        Ok(())
    }
}

impl fmt::Display for SpawnData {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(
            f,
            "SpawnData({}, {}, {}, radius={}, monsters={})",
            self.x,
            self.y,
            self.z,
            self.radius,
            self.monsters.len()
        )
    }
}

// ---------------------------------------------------------------------------

/// NPC spawn point.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct NPCSpawnData {
    /// Center X coordinate.
    pub x: u16,
    /// Center Y coordinate.
    pub y: u16,
    /// Center Z coordinate.
    pub z: u8,
    /// NPC creature name.
    pub npc_name: String,
    /// Direction: 0=South, 1=East, 2=North, 3=West.
    pub direction: u8,
}

impl NPCSpawnData {
    /// Create a new NPC spawn.
    pub fn new(x: u16, y: u16, z: u8, npc_name: impl Into<String>) -> Self {
        Self {
            x,
            y,
            z,
            npc_name: npc_name.into(),
            direction: 0,
        }
    }

    /// Validate NPC spawn fields.
    pub fn validate(&self) -> Result<(), String> {
        if self.z > 15 {
            return Err(format!("npc spawn z out of range: {}", self.z));
        }
        if self.npc_name.is_empty() {
            return Err("npc name must not be empty".into());
        }
        Ok(())
    }
}

impl fmt::Display for NPCSpawnData {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(
            f,
            "NPCSpawnData({}, {}, {}, npc={:?})",
            self.x, self.y, self.z, self.npc_name
        )
    }
}

// ---------------------------------------------------------------------------

/// A house definition (tiles + name + rent).
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct HouseData {
    /// House ID.
    pub id: u32,
    /// House name.
    pub name: String,
    /// Rent (in gold).
    pub rent: u32,
    /// Town ID this house belongs to.
    pub town_id: u32,
    /// House size (in tiles).
    pub size: u32,
    /// House tile coordinates (encoded).
    pub tile_ids: Vec<u32>,
}

impl HouseData {
    /// Create a new house.
    pub fn new(id: u32, name: impl Into<String>, town_id: u32) -> Self {
        Self {
            id,
            name: name.into(),
            rent: 0,
            town_id,
            size: 0,
            tile_ids: Vec::new(),
        }
    }

    /// Builder: set rent.
    pub fn with_rent(mut self, rent: u32) -> Self {
        self.rent = rent;
        self
    }

    /// Builder: set size.
    pub fn with_size(mut self, size: u32) -> Self {
        self.size = size;
        self
    }

    /// Validate house fields.
    pub fn validate(&self) -> Result<(), String> {
        if self.id == 0 {
            return Err(format!("house id must be > 0: {}", self.id));
        }
        Ok(())
    }
}

impl fmt::Display for HouseData {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(
            f,
            "HouseData(id={}, name={:?}, town={}, tiles={})",
            self.id,
            self.name,
            self.town_id,
            self.tile_ids.len()
        )
    }
}

// ---------------------------------------------------------------------------

/// Top-level map container.
///
/// Matches the Python `MapData` dataclass with builder methods.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct MapData {
    /// Map width in tiles.
    pub width: u16,
    /// Map height in tiles.
    pub height: u16,
    /// Map description string.
    pub description: String,
    /// OTBM format version (2 or 3).
    pub otbm_version: u32,
    /// OTB major version (2 for 7.6–8.x, 3 for 10+).
    pub otb_major_version: u32,
    /// OTB minor version (e.g. 7 or 12).
    pub otb_minor_version: u32,
    /// All tiles on the map.
    pub tiles: Vec<TileData>,
    /// Towns.
    pub towns: Vec<TownData>,
    /// Waypoints.
    pub waypoints: Vec<WaypointData>,
    /// Monster spawns.
    pub spawns: Vec<SpawnData>,
    /// NPC spawns.
    pub npc_spawns: Vec<NPCSpawnData>,
    /// Houses.
    pub houses: Vec<HouseData>,
    /// External spawn file reference.
    pub ext_spawn_file: String,
    /// External house file reference.
    pub ext_house_file: String,
    /// External NPC spawn file reference.
    pub ext_spawn_npc_file: String,
}

impl Default for MapData {
    fn default() -> Self {
        Self::new()
    }
}

impl MapData {
    /// Create a new map with default settings (2048x2048, OTBM v2).
    pub fn new() -> Self {
        Self {
            width: 2048,
            height: 2048,
            description: String::from("Generated Map"),
            otbm_version: 2,
            otb_major_version: 2,
            otb_minor_version: 7,
            tiles: Vec::new(),
            towns: Vec::new(),
            waypoints: Vec::new(),
            spawns: Vec::new(),
            npc_spawns: Vec::new(),
            houses: Vec::new(),
            ext_spawn_file: String::new(),
            ext_house_file: String::new(),
            ext_spawn_npc_file: String::new(),
        }
    }

    /// Create a new map with the given dimensions.
    pub fn with_dimensions(width: u16, height: u16) -> Self {
        Self {
            width,
            height,
            ..Self::new()
        }
    }

    /// Create a map configured for OTBM v3.
    pub fn new_v3() -> Self {
        Self {
            otbm_version: 3,
            otb_major_version: 3,
            otb_minor_version: 12,
            ..Self::new()
        }
    }

    // ----- Builder methods -----

    /// Create and append a tile, returning a mutable reference for chaining.
    pub fn add_tile(
        &mut self,
        x: u16,
        y: u16,
        z: u8,
        ground_id: u16,
    ) -> &mut TileData {
        self.tiles.push(TileData::new(x, y, z, ground_id));
        self.tiles.last_mut().unwrap()
    }

    /// Add a tile with full options, returning a mutable reference.
    pub fn add_tile_full(
        &mut self,
        x: u16,
        y: u16,
        z: u8,
        ground_id: u16,
        flags: TileFlags,
        house_id: u32,
    ) -> &mut TileData {
        self.tiles.push(TileData {
            x,
            y,
            z,
            ground_id,
            items: Vec::new(),
            flags,
            house_id,
        });
        self.tiles.last_mut().unwrap()
    }

    /// Add an item to an existing tile (or create one if it doesn't exist).
    pub fn add_item(&mut self, x: u16, y: u16, z: u8, item: ItemData) {
        for tile in &mut self.tiles {
            if tile.x == x && tile.y == y && tile.z == z {
                tile.items.push(item);
                return;
            }
        }
        let mut tile = TileData::new(x, y, z, 0);
        tile.items.push(item);
        self.tiles.push(tile);
    }

    /// Mark a tile as a house tile.
    pub fn set_house(&mut self, x: u16, y: u16, z: u8, house_id: u32, ground_id: u16) {
        for tile in &mut self.tiles {
            if tile.x == x && tile.y == y && tile.z == z {
                tile.house_id = house_id;
                if ground_id != 0 && tile.ground_id == 0 {
                    tile.ground_id = ground_id;
                }
                return;
            }
        }
        self.tiles.push(TileData {
            x,
            y,
            z,
            ground_id,
            items: Vec::new(),
            flags: TileFlags::NONE,
            house_id,
        });
    }

    /// Add a town and return a reference.
    pub fn add_town(&mut self, id: u32, name: impl Into<String>, temple: Position) -> &mut TownData {
        self.towns.push(TownData::new(id, name, temple));
        self.towns.last_mut().unwrap()
    }

    /// Add a waypoint and return a reference.
    pub fn add_waypoint(
        &mut self,
        name: impl Into<String>,
        pos: Position,
    ) -> &mut WaypointData {
        self.waypoints.push(WaypointData::new(name, pos));
        self.waypoints.last_mut().unwrap()
    }

    /// Add a spawn and return a reference.
    pub fn add_spawn(&mut self, x: u16, y: u16, z: u8, radius: u32) -> &mut SpawnData {
        self.spawns.push(SpawnData::new(x, y, z, radius));
        self.spawns.last_mut().unwrap()
    }

    /// Add an NPC spawn and return a reference.
    pub fn add_npc_spawn(
        &mut self,
        x: u16,
        y: u16,
        z: u8,
        npc_name: impl Into<String>,
    ) -> &mut NPCSpawnData {
        self.npc_spawns.push(NPCSpawnData::new(x, y, z, npc_name));
        self.npc_spawns.last_mut().unwrap()
    }

    /// Add a house and return a reference.
    pub fn add_house(
        &mut self,
        id: u32,
        name: impl Into<String>,
        town_id: u32,
    ) -> &mut HouseData {
        self.houses.push(HouseData::new(id, name, town_id));
        self.houses.last_mut().unwrap()
    }

    // ----- Stats -----

    /// Return a map of statistics about the map.
    pub fn stats(&self) -> HashMap<String, usize> {
        let total_items: usize = self.tiles.iter().map(|t| t.items.len()).sum();
        let ground_tiles = self.tiles.iter().filter(|t| t.ground_id > 0).count();
        let house_tiles = self.tiles.iter().filter(|t| t.house_id > 0).count();
        let z_levels = if self.tiles.is_empty() {
            0
        } else {
            self.tiles.iter().map(|t| t.z as usize).collect::<std::collections::HashSet<_>>().len()
        };

        let min_x = self.tiles.iter().map(|t| t.x).min().unwrap_or(0);
        let max_x = self.tiles.iter().map(|t| t.x).max().unwrap_or(0);
        let min_y = self.tiles.iter().map(|t| t.y).min().unwrap_or(0);
        let max_y = self.tiles.iter().map(|t| t.y).max().unwrap_or(0);

        let area_coverage = if self.tiles.is_empty() {
            0
        } else {
            (max_x as usize - min_x as usize + 1) * (max_y as usize - min_y as usize + 1)
        };

        let mut m = HashMap::new();
        m.insert("tiles".into(), self.tiles.len());
        m.insert("ground_tiles".into(), ground_tiles);
        m.insert("total_items".into(), total_items);
        m.insert("house_tiles".into(), house_tiles);
        m.insert("towns".into(), self.towns.len());
        m.insert("waypoints".into(), self.waypoints.len());
        m.insert("spawns".into(), self.spawns.len());
        m.insert("npc_spawns".into(), self.npc_spawns.len());
        m.insert("houses".into(), self.houses.len());
        m.insert("z_levels".into(), z_levels);
        m.insert("area_coverage".into(), area_coverage);
        m
    }

    /// Validate all fields.
    pub fn validate(&self) -> Result<(), String> {
        if !(1..=3).contains(&self.otbm_version) {
            return Err(format!("unsupported OTBM version: {}", self.otbm_version));
        }
        for t in &self.towns {
            t.validate()?;
        }
        for wp in &self.waypoints {
            wp.validate()?;
        }
        for t in &self.tiles {
            t.validate()?;
        }
        Ok(())
    }
}

impl fmt::Display for MapData {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(
            f,
            "MapData({}x{}, v{}, tiles={}, towns={}, waypoints={}, spawns={}, houses={})",
            self.width,
            self.height,
            self.otbm_version,
            self.tiles.len(),
            self.towns.len(),
            self.waypoints.len(),
            self.spawns.len(),
            self.houses.len()
        )
    }
}

// ===========================================================================
// Tests
// ===========================================================================

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_position_default() {
        let p = Position::default();
        assert_eq!(p, Position { x: 0, y: 0, z: 0 });
    }

    #[test]
    fn test_position_new() {
        let p = Position::new(100, 200, 7);
        assert_eq!(p.x, 100);
        assert_eq!(p.y, 200);
        assert_eq!(p.z, 7);
    }

    #[test]
    fn test_position_display() {
        let p = Position::new(10, 20, 7);
        assert_eq!(format!("{}", p), "Position(10, 20, 7)");
    }

    #[test]
    fn test_position_validate_ok() {
        let p = Position::new(1000, 2000, 15);
        assert!(p.validate().is_ok());
    }

    #[test]
    fn test_position_validate_fail() {
        let p = Position::new(1000, 2000, 16);
        assert!(p.validate().is_err());
    }

    #[test]
    fn test_tile_flags() {
        let f = TileFlags::PROTECTIONZONE | TileFlags::PVPZONE;
        assert_eq!(f.bits(), 0x01 | 0x10);
        assert!(f.contains(TileFlags::PROTECTIONZONE));
        assert!(!f.contains(TileFlags::NOPVPZONE));
    }

    #[test]
    fn test_tile_flags_display() {
        let f = TileFlags::PROTECTIONZONE | TileFlags::NOPVPZONE;
        assert_eq!(format!("{}", f), "PROTECTIONZONE|NOPVPZONE");
    }

    #[test]
    fn test_tile_flags_none_display() {
        assert_eq!(format!("{}", TileFlags::NONE), "NONE");
    }

    #[test]
    fn test_tile_flags_serde_roundtrip() {
        let f = TileFlags::PROTECTIONZONE | TileFlags::NOSAVEZONE;
        let json = serde_json::to_string(&f).unwrap();
        let back: TileFlags = serde_json::from_str(&json).unwrap();
        assert_eq!(f, back);
    }

    #[test]
    fn test_item_data_new() {
        let item = ItemData::new(102);
        assert_eq!(item.id, 102);
        assert_eq!(item.count, 0);
    }

    #[test]
    fn test_item_data_builder() {
        let item = ItemData::new(5121)
            .with_count(5)
            .with_action_id(100)
            .with_text("open sesame");
        assert_eq!(item.count, 5);
        assert_eq!(item.action_id, 100);
        assert_eq!(item.text, "open sesame");
    }

    #[test]
    fn test_item_data_children() {
        let item = ItemData::new(3756).with_child(ItemData::new(2160));
        assert!(item.has_children());
        assert_eq!(item.children.len(), 1);
        assert_eq!(item.container_depth(), 1);
    }

    #[test]
    fn test_item_data_nested_children() {
        let inner = ItemData::new(2160);
        let middle = ItemData::new(3756).with_child(inner);
        let outer = ItemData::new(3757).with_child(middle);
        assert_eq!(outer.container_depth(), 2);
    }

    #[test]
    fn test_item_data_display() {
        let item = ItemData::new(102).with_count(5);
        let s = format!("{}", item);
        assert!(s.contains("ItemData(id=102"));
        assert!(s.contains("count=5"));
    }

    #[test]
    fn test_item_data_validate_ok() {
        let item = ItemData::new(102);
        assert!(item.validate().is_ok());
    }

    #[test]
    fn test_item_data_validate_fail() {
        let item = ItemData::new(0);
        assert!(item.validate().is_err());
    }

    #[test]
    fn test_tile_data_new() {
        let tile = TileData::new(100, 200, 7, 102);
        assert_eq!(tile.x, 100);
        assert_eq!(tile.ground_id, 102);
        assert!(tile.items.is_empty());
    }

    #[test]
    fn test_tile_data_builder() {
        let tile = TileData::new(50, 60, 7, 103)
            .with_item(ItemData::new(5121))
            .with_flags(TileFlags::PROTECTIONZONE)
            .with_house_id(42);
        assert_eq!(tile.items.len(), 1);
        assert!(tile.flags.contains(TileFlags::PROTECTIONZONE));
        assert_eq!(tile.house_id, 42);
    }

    #[test]
    fn test_tile_data_display() {
        let tile = TileData::new(10, 20, 7, 102);
        assert!(format!("{}", tile).contains("ground=102"));
    }

    #[test]
    fn test_town_data() {
        let town = TownData::new(1, "Thais", Position::new(100, 200, 7));
        assert_eq!(town.id, 1);
        assert_eq!(town.name, "Thais");
        assert!(town.validate().is_ok());
    }

    #[test]
    fn test_town_data_validate_fail() {
        let town = TownData::new(0, "Bad", Position::default());
        assert!(town.validate().is_err());
    }

    #[test]
    fn test_waypoint_data() {
        let wp = WaypointData::new("Temple", Position::new(100, 200, 7));
        assert_eq!(wp.name, "Temple");
        assert!(wp.validate().is_ok());
    }

    #[test]
    fn test_spawn_data() {
        let spawn = SpawnData::new(100, 200, 7, 5)
            .with_monster("Rat", 1, 2);
        assert_eq!(spawn.radius, 5);
        assert_eq!(spawn.monsters.len(), 1);
        assert_eq!(spawn.monsters[0].name, "Rat");
    }

    #[test]
    fn test_npc_spawn_data() {
        let npc = NPCSpawnData::new(100, 200, 7, "The Guide");
        assert_eq!(npc.npc_name, "The Guide");
        assert!(npc.validate().is_ok());
    }

    #[test]
    fn test_house_data() {
        let house = HouseData::new(1, "Castle", 1).with_rent(1000).with_size(50);
        assert_eq!(house.rent, 1000);
        assert_eq!(house.size, 50);
        assert!(house.validate().is_ok());
    }

    #[test]
    fn test_house_data_validate_fail() {
        let house = HouseData::new(0, "Bad", 1);
        assert!(house.validate().is_err());
    }

    #[test]
    fn test_map_data_default() {
        let map = MapData::default();
        assert_eq!(map.width, 2048);
        assert_eq!(map.height, 2048);
        assert_eq!(map.otbm_version, 2);
        assert!(map.tiles.is_empty());
    }

    #[test]
    fn test_map_data_builder() {
        let mut map = MapData::with_dimensions(512, 512);
        map.add_tile(100, 200, 7, tiles::GRASS);
        map.add_town(1, "Thais", Position::new(100, 200, 7));
        map.add_waypoint("Home", Position::new(100, 200, 7));
        map.add_spawn(100, 200, 7, 10);
        map.add_npc_spawn(100, 200, 7, "Guide");
        map.add_house(1, "Castle", 1);

        assert_eq!(map.tiles.len(), 1);
        assert_eq!(map.towns.len(), 1);
        assert_eq!(map.waypoints.len(), 1);
        assert_eq!(map.spawns.len(), 1);
        assert_eq!(map.npc_spawns.len(), 1);
        assert_eq!(map.houses.len(), 1);
    }

    #[test]
    fn test_map_data_add_item_to_existing() {
        let mut map = MapData::new();
        map.add_tile(10, 20, 7, tiles::GRASS);
        map.add_item(10, 20, 7, ItemData::new(tiles::CHEST));

        // Should have been added to existing tile, not a new one
        assert_eq!(map.tiles.len(), 1);
        assert_eq!(map.tiles[0].items.len(), 1);
    }

    #[test]
    fn test_map_data_add_item_creates_tile() {
        let mut map = MapData::new();
        map.add_item(10, 20, 7, ItemData::new(tiles::CHEST));

        assert_eq!(map.tiles.len(), 1);
        assert_eq!(map.tiles[0].items.len(), 1);
        assert_eq!(map.tiles[0].ground_id, 0);
    }

    #[test]
    fn test_map_data_set_house() {
        let mut map = MapData::new();
        map.add_tile(10, 20, 7, tiles::FLOOR_WOOD);
        map.set_house(10, 20, 7, 42, 0);

        assert_eq!(map.tiles[0].house_id, 42);
    }

    #[test]
    fn test_map_data_stats() {
        let mut map = MapData::new();
        map.add_tile(10, 20, 7, tiles::GRASS);
        map.add_tile(11, 20, 7, tiles::GRASS);
        map.add_tile(10, 20, 8, tiles::DIRT);
        map.add_town(1, "Thais", Position::new(100, 200, 7));
        map.add_waypoint("WP1", Position::new(100, 200, 7));

        let stats = map.stats();
        assert_eq!(stats["tiles"], 3);
        assert_eq!(stats["ground_tiles"], 3);
        assert_eq!(stats["towns"], 1);
        assert_eq!(stats["waypoints"], 1);
        assert_eq!(stats["z_levels"], 2);
    }

    #[test]
    fn test_map_data_v3() {
        let map = MapData::new_v3();
        assert_eq!(map.otbm_version, 3);
        assert_eq!(map.otb_major_version, 3);
        assert_eq!(map.otb_minor_version, 12);
    }

    #[test]
    fn test_map_data_validate() {
        let mut map = MapData::new();
        map.add_tile(100, 200, 7, tiles::GRASS);
        assert!(map.validate().is_ok());
    }

    #[test]
    fn test_map_data_validate_bad_version() {
        let mut map = MapData::new();
        map.otbm_version = 99;
        assert!(map.validate().is_err());
    }

    #[test]
    fn test_map_data_display() {
        let map = MapData::new();
        let s = format!("{}", map);
        assert!(s.contains("MapData(2048x2048, v2"));
    }

    #[test]
    fn test_map_data_serde_roundtrip() {
        let mut map = MapData::with_dimensions(512, 512);
        map.description = "Test Map".into();
        map.add_tile(10, 20, 7, tiles::GRASS);

        let json = serde_json::to_string(&map).unwrap();
        let back: MapData = serde_json::from_str(&json).unwrap();
        assert_eq!(map, back);
    }

    #[test]
    fn test_constants() {
        assert_eq!(NODE_START, 0xFE);
        assert_eq!(NODE_END, 0xFF);
        assert_eq!(ESCAPE, 0xFD);
        assert_eq!(ESCAPE_THRESHOLD, 0xFD);
        assert_eq!(OTBM_MAGIC, b"OTBM");
    }

    #[test]
    fn test_otb_version() {
        assert_eq!(OtbVersion::V2_7, OtbVersion { major: 2, minor: 7 });
        assert_eq!(OtbVersion::V3_12, OtbVersion { major: 3, minor: 12 });
    }
}
