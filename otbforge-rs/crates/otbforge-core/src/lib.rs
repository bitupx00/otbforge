/*!
OTBForge Core — High-level orchestration: validator, diff, stitcher, composer.

This crate provides:
- [`MapValidator`] — 13 integrity checks ported from the Python validator
- [`MapDiff`] — compare two `MapData` objects
- [`Stitcher`] — combine multiple maps into one
- [`RegionExtractor`] — extract sub-regions from a map
- [`MapComposer`] — orchestrate generators to build complete maps
*/

use std::collections::{HashMap, HashSet};

use otbforge_models::*;

// ===========================================================================
// MapValidator
// ===========================================================================

/// Severity of a validation finding.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Severity {
    Error,
    Warning,
    Info,
}

impl std::fmt::Display for Severity {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Severity::Error => write!(f, "error"),
            Severity::Warning => write!(f, "warning"),
            Severity::Info => write!(f, "info"),
        }
    }
}

/// A single validation finding.
#[derive(Debug, Clone)]
pub struct ValidationIssue {
    /// Severity level.
    pub severity: Severity,
    /// Category (e.g. "tiles", "spawns", "towns").
    pub category: String,
    /// Human-readable message.
    pub message: String,
    /// Position where the issue was found, if applicable.
    pub position: Option<(u16, u16, u8)>,
}

impl std::fmt::Display for ValidationIssue {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        if let Some((x, y, z)) = self.position {
            write!(
                f,
                "[{}] [{}] ({}, {}, {}): {}",
                self.severity, self.category, x, y, z, self.message
            )
        } else {
            write!(
                f,
                "[{}] [{}]: {}",
                self.severity, self.category, self.message
            )
        }
    }
}

/// Maximum reasonable map dimension (16-bit unsigned).
const MAX_DIM: u16 = 65535;

/// Maximum allowed container nesting depth.
const MAX_CONTAINER_DEPTH: usize = 3;

/// Stateless map validator with 13 integrity checks.
///
/// Ported from the Python `MapValidator` in `ai_core/map_validator.py`.
pub struct MapValidator;

impl MapValidator {
    /// Run all checks and return the combined list of issues.
    pub fn validate(map_data: &MapData) -> Vec<ValidationIssue> {
        let mut issues = Vec::new();
        issues.extend(Self::check_dimensions(map_data));
        issues.extend(Self::check_empty_map(map_data));
        issues.extend(Self::check_tiles_bounds(map_data));
        issues.extend(Self::check_ground_ids(map_data));
        issues.extend(Self::check_no_duplicate_tiles(map_data));
        issues.extend(Self::check_tile_items_valid(map_data));
        issues.extend(Self::check_container_depth(map_data));
        issues.extend(Self::check_house_tiles_valid(map_data));
        issues.extend(Self::check_spawns_bounds(map_data));
        issues.extend(Self::check_spawn_monsters(map_data));
        issues.extend(Self::check_towns_unique(map_data));
        issues.extend(Self::check_waypoints_unique(map_data));
        issues.extend(Self::check_npc_spawns_bounds(map_data));
        issues
    }

    /// 1. Check map dimensions are valid.
    pub fn check_dimensions(map_data: &MapData) -> Vec<ValidationIssue> {
        let mut issues = Vec::new();
        let w = map_data.width;
        let h = map_data.height;
        if w == 0 {
            issues.push(ValidationIssue {
                severity: Severity::Error,
                category: "dimensions".into(),
                message: format!("Map width must be > 0, got {}", w),
                position: None,
            });
        }
        if h == 0 {
            issues.push(ValidationIssue {
                severity: Severity::Error,
                category: "dimensions".into(),
                message: format!("Map height must be > 0, got {}", h),
                position: None,
            });
        }
        if w >= MAX_DIM {
            issues.push(ValidationIssue {
                severity: Severity::Error,
                category: "dimensions".into(),
                message: format!("Map width {} exceeds maximum {}", w, MAX_DIM),
                position: None,
            });
        }
        if h >= MAX_DIM {
            issues.push(ValidationIssue {
                severity: Severity::Error,
                category: "dimensions".into(),
                message: format!("Map height {} exceeds maximum {}", h, MAX_DIM),
                position: None,
            });
        }
        if w > 2048 || h > 2048 {
            if w < MAX_DIM && h < MAX_DIM {
                issues.push(ValidationIssue {
                    severity: Severity::Info,
                    category: "dimensions".into(),
                    message: format!("Large map dimensions: {}x{}", w, h),
                    position: None,
                });
            }
        }
        issues
    }

    /// 2. Check for empty map.
    pub fn check_empty_map(map_data: &MapData) -> Vec<ValidationIssue> {
        if map_data.tiles.is_empty()
            && map_data.spawns.is_empty()
            && map_data.npc_spawns.is_empty()
        {
            return vec![ValidationIssue {
                severity: Severity::Warning,
                category: "map".into(),
                message: "Map is empty (no tiles, spawns, or NPCs)".into(),
                position: None,
            }];
        }
        Vec::new()
    }

    /// 3. Check tiles are within map bounds.
    pub fn check_tiles_bounds(map_data: &MapData) -> Vec<ValidationIssue> {
        let mut issues = Vec::new();
        let w = map_data.width;
        let h = map_data.height;
        if w == 0 || h == 0 {
            return issues; // already flagged by check_dimensions
        }
        for tile in &map_data.tiles {
            if tile.x >= w || tile.y >= h {
                issues.push(ValidationIssue {
                    severity: Severity::Error,
                    category: "tiles".into(),
                    message: format!(
                        "Tile at ({}, {}, {}) is out of map bounds {}x{}",
                        tile.x, tile.y, tile.z, w, h
                    ),
                    position: Some((tile.x, tile.y, tile.z)),
                });
            }
        }
        issues
    }

    /// 4. Check all tiles have ground IDs > 0.
    pub fn check_ground_ids(map_data: &MapData) -> Vec<ValidationIssue> {
        let mut issues = Vec::new();
        for tile in &map_data.tiles {
            if tile.ground_id == 0 {
                issues.push(ValidationIssue {
                    severity: Severity::Warning,
                    category: "tiles".into(),
                    message: format!(
                        "Tile at ({}, {}, {}) has no ground (ground_id={})",
                        tile.x, tile.y, tile.z, tile.ground_id
                    ),
                    position: Some((tile.x, tile.y, tile.z)),
                });
            }
        }
        issues
    }

    /// 5. Check no duplicate tiles (same x, y, z).
    pub fn check_no_duplicate_tiles(map_data: &MapData) -> Vec<ValidationIssue> {
        let mut issues = Vec::new();
        let mut seen: HashMap<(u16, u16, u8), usize> = HashMap::new();
        for (idx, tile) in map_data.tiles.iter().enumerate() {
            let key = (tile.x, tile.y, tile.z);
            if let Some(&first_idx) = seen.get(&key) {
                issues.push(ValidationIssue {
                    severity: Severity::Error,
                    category: "tiles".into(),
                    message: format!(
                        "Duplicate tile at ({}, {}, {}) (first at index {})",
                        tile.x, tile.y, tile.z, first_idx
                    ),
                    position: Some((tile.x, tile.y, tile.z)),
                });
            } else {
                seen.insert(key, idx);
            }
        }
        issues
    }

    /// 6. Check tile items have valid IDs.
    pub fn check_tile_items_valid(map_data: &MapData) -> Vec<ValidationIssue> {
        let mut issues = Vec::new();
        for tile in &map_data.tiles {
            for item in &tile.items {
                if item.id == 0 {
                    issues.push(ValidationIssue {
                        severity: Severity::Error,
                        category: "items".into(),
                        message: format!(
                            "Item with invalid id=0 on tile ({}, {}, {})",
                            tile.x, tile.y, tile.z
                        ),
                        position: Some((tile.x, tile.y, tile.z)),
                    });
                }
            }
        }
        issues
    }

    /// 7. Check container nesting depth.
    pub fn check_container_depth(map_data: &MapData) -> Vec<ValidationIssue> {
        let mut issues = Vec::new();
        for tile in &map_data.tiles {
            for item in &tile.items {
                let depth = item.container_depth();
                if depth > MAX_CONTAINER_DEPTH {
                    issues.push(ValidationIssue {
                        severity: Severity::Warning,
                        category: "items".into(),
                        message: format!(
                            "Container nesting depth {} exceeds limit {} on tile ({}, {}, {})",
                            depth, MAX_CONTAINER_DEPTH, tile.x, tile.y, tile.z
                        ),
                        position: Some((tile.x, tile.y, tile.z)),
                    });
                }
            }
        }
        issues
    }

    /// 8. Check house tiles have at least one town defined.
    pub fn check_house_tiles_valid(map_data: &MapData) -> Vec<ValidationIssue> {
        let mut issues = Vec::new();
        let has_towns = !map_data.towns.is_empty();
        for tile in &map_data.tiles {
            if tile.house_id > 0 && !has_towns {
                issues.push(ValidationIssue {
                    severity: Severity::Warning,
                    category: "houses".into(),
                    message: format!(
                        "House tile at ({}, {}, {}) with house_id={} but no towns defined",
                        tile.x, tile.y, tile.z, tile.house_id
                    ),
                    position: Some((tile.x, tile.y, tile.z)),
                });
            }
        }
        issues
    }

    /// 9. Check spawns are within map bounds.
    pub fn check_spawns_bounds(map_data: &MapData) -> Vec<ValidationIssue> {
        let mut issues = Vec::new();
        let w = map_data.width;
        let h = map_data.height;
        if w == 0 || h == 0 {
            return issues;
        }
        for spawn in &map_data.spawns {
            if spawn.x >= w || spawn.y >= h {
                issues.push(ValidationIssue {
                    severity: Severity::Error,
                    category: "spawns".into(),
                    message: format!(
                        "Spawn at ({}, {}, {}) is out of map bounds {}x{}",
                        spawn.x, spawn.y, spawn.z, w, h
                    ),
                    position: Some((spawn.x, spawn.y, spawn.z)),
                });
            }
        }
        issues
    }

    /// 10. Check spawn monsters list is non-empty.
    pub fn check_spawn_monsters(map_data: &MapData) -> Vec<ValidationIssue> {
        let mut issues = Vec::new();
        for spawn in &map_data.spawns {
            if spawn.monsters.is_empty() {
                issues.push(ValidationIssue {
                    severity: Severity::Error,
                    category: "spawns".into(),
                    message: format!(
                        "Spawn at ({}, {}, {}) has no monsters assigned",
                        spawn.x, spawn.y, spawn.z
                    ),
                    position: Some((spawn.x, spawn.y, spawn.z)),
                });
            }
        }
        issues
    }

    /// 11. Check town IDs are unique.
    pub fn check_towns_unique(map_data: &MapData) -> Vec<ValidationIssue> {
        let mut issues = Vec::new();
        let mut id_counts: HashMap<u32, usize> = HashMap::new();
        for town in &map_data.towns {
            *id_counts.entry(town.id).or_insert(0) += 1;
        }
        for town in &map_data.towns {
            if id_counts[&town.id] > 1 {
                issues.push(ValidationIssue {
                    severity: Severity::Error,
                    category: "towns".into(),
                    message: format!(
                        "Duplicate town id={} (name={:?})",
                        town.id, town.name
                    ),
                    position: Some((town.temple.x, town.temple.y, town.temple.z)),
                });
            }
        }
        issues
    }

    /// 12. Check waypoint names are unique.
    pub fn check_waypoints_unique(map_data: &MapData) -> Vec<ValidationIssue> {
        let mut issues = Vec::new();
        let mut name_counts: HashMap<String, usize> = HashMap::new();
        for wp in &map_data.waypoints {
            *name_counts.entry(wp.name.clone()).or_insert(0) += 1;
        }
        for wp in &map_data.waypoints {
            if name_counts.get(&wp.name).copied().unwrap_or(0) > 1 {
                issues.push(ValidationIssue {
                    severity: Severity::Warning,
                    category: "waypoints".into(),
                    message: format!(
                        "Duplicate waypoint name={:?} at ({}, {}, {})",
                        wp.name, wp.pos.x, wp.pos.y, wp.pos.z
                    ),
                    position: Some((wp.pos.x, wp.pos.y, wp.pos.z)),
                });
            }
        }
        issues
    }

    /// 13. Check NPC spawns are within map bounds.
    pub fn check_npc_spawns_bounds(map_data: &MapData) -> Vec<ValidationIssue> {
        let mut issues = Vec::new();
        let w = map_data.width;
        let h = map_data.height;
        if w == 0 || h == 0 {
            return issues;
        }
        for npc in &map_data.npc_spawns {
            if npc.x >= w || npc.y >= h {
                issues.push(ValidationIssue {
                    severity: Severity::Error,
                    category: "npc_spawns".into(),
                    message: format!(
                        "NPC spawn for {:?} at ({}, {}, {}) is out of map bounds {}x{}",
                        npc.npc_name, npc.x, npc.y, npc.z, w, h
                    ),
                    position: Some((npc.x, npc.y, npc.z)),
                });
            }
        }
        issues
    }

    /// Return a summary: counts of errors, warnings, and info.
    pub fn summary(issues: &[ValidationIssue]) -> HashMap<&str, usize> {
        let mut m = HashMap::new();
        m.insert("errors", issues.iter().filter(|i| i.severity == Severity::Error).count());
        m.insert("warnings", issues.iter().filter(|i| i.severity == Severity::Warning).count());
        m.insert("info", issues.iter().filter(|i| i.severity == Severity::Info).count());
        m
    }

    /// Check if the map is valid (no errors).
    pub fn is_valid(map_data: &MapData) -> bool {
        let issues = Self::validate(map_data);
        !issues.iter().any(|i| i.severity == Severity::Error)
    }
}

// ===========================================================================
// MapDiff
// ===========================================================================

/// A difference between two maps.
#[derive(Debug, Clone)]
pub enum MapDifference {
    /// A tile exists in A but not in B.
    TileRemoved(TileData),
    /// A tile exists in B but not in A.
    TileAdded(TileData),
    /// A tile exists in both but has differences.
    TileChanged { pos: (u16, u16, u8), changes: Vec<String> },
    /// A town exists in A but not in B.
    TownRemoved(u32),
    /// A town exists in B but not in A.
    TownAdded(u32),
    /// A waypoint exists in A but not in B.
    WaypointRemoved(String),
    /// A waypoint exists in B but not in A.
    WaypointAdded(String),
    /// A spawn exists in A but not in B.
    SpawnRemoved((u16, u16, u8)),
    /// A spawn exists in B but not in A.
    SpawnAdded((u16, u16, u8)),
}

impl std::fmt::Display for MapDifference {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            MapDifference::TileRemoved(t) => write!(f, "Tile removed at ({}, {}, {})", t.x, t.y, t.z),
            MapDifference::TileAdded(t) => write!(f, "Tile added at ({}, {}, {})", t.x, t.y, t.z),
            MapDifference::TileChanged { pos, changes } => {
                write!(f, "Tile changed at {:?}: {}", pos, changes.join(", "))
            }
            MapDifference::TownRemoved(id) => write!(f, "Town {} removed", id),
            MapDifference::TownAdded(id) => write!(f, "Town {} added", id),
            MapDifference::WaypointRemoved(name) => write!(f, "Waypoint {:?} removed", name),
            MapDifference::WaypointAdded(name) => write!(f, "Waypoint {:?} added", name),
            MapDifference::SpawnRemoved(pos) => write!(f, "Spawn at {:?} removed", pos),
            MapDifference::SpawnAdded(pos) => write!(f, "Spawn at {:?} added", pos),
        }
    }
}

/// Compare two `MapData` objects and return a list of differences.
pub struct MapDiff;

impl MapDiff {
    /// Compare two maps and return all differences.
    pub fn diff(a: &MapData, b: &MapData) -> Vec<MapDifference> {
        let mut diffs = Vec::new();

        // Compare tiles
        let tiles_a: HashMap<(u16, u16, u8), &TileData> =
            a.tiles.iter().map(|t| ((t.x, t.y, t.z), t)).collect();
        let tiles_b: HashMap<(u16, u16, u8), &TileData> =
            b.tiles.iter().map(|t| ((t.x, t.y, t.z), t)).collect();

        for (pos, tile) in &tiles_a {
            if let Some(other) = tiles_b.get(pos) {
                let changes = Self::diff_tiles(tile, other);
                if !changes.is_empty() {
                    diffs.push(MapDifference::TileChanged {
                        pos: *pos,
                        changes,
                    });
                }
            } else {
                diffs.push(MapDifference::TileRemoved((*tile).clone()));
            }
        }
        for (pos, tile) in &tiles_b {
            if !tiles_a.contains_key(pos) {
                diffs.push(MapDifference::TileAdded((*tile).clone()));
            }
        }

        // Compare towns
        let towns_a: HashSet<u32> = a.towns.iter().map(|t| t.id).collect();
        let towns_b: HashSet<u32> = b.towns.iter().map(|t| t.id).collect();
        for id in &towns_a {
            if !towns_b.contains(id) {
                diffs.push(MapDifference::TownRemoved(*id));
            }
        }
        for id in &towns_b {
            if !towns_a.contains(id) {
                diffs.push(MapDifference::TownAdded(*id));
            }
        }

        // Compare waypoints
        let wp_a: HashSet<&str> = a.waypoints.iter().map(|w| w.name.as_str()).collect();
        let wp_b: HashSet<&str> = b.waypoints.iter().map(|w| w.name.as_str()).collect();
        for name in &wp_a {
            if !wp_b.contains(*name) {
                diffs.push(MapDifference::WaypointRemoved((*name).into()));
            }
        }
        for name in &wp_b {
            if !wp_a.contains(*name) {
                diffs.push(MapDifference::WaypointAdded((*name).into()));
            }
        }

        // Compare spawns
        let spawns_a: HashSet<(u16, u16, u8)> =
            a.spawns.iter().map(|s| (s.x, s.y, s.z)).collect();
        let spawns_b: HashSet<(u16, u16, u8)> =
            b.spawns.iter().map(|s| (s.x, s.y, s.z)).collect();
        for pos in &spawns_a {
            if !spawns_b.contains(pos) {
                diffs.push(MapDifference::SpawnRemoved(*pos));
            }
        }
        for pos in &spawns_b {
            if !spawns_a.contains(pos) {
                diffs.push(MapDifference::SpawnAdded(*pos));
            }
        }

        diffs
    }

    /// Diff two tiles, returning a list of human-readable change descriptions.
    fn diff_tiles(a: &TileData, b: &TileData) -> Vec<String> {
        let mut changes = Vec::new();
        if a.ground_id != b.ground_id {
            changes.push(format!("ground_id: {} → {}", a.ground_id, b.ground_id));
        }
        if a.flags != b.flags {
            changes.push(format!("flags: {:#x} → {:#x}", a.flags.bits(), b.flags.bits()));
        }
        if a.house_id != b.house_id {
            changes.push(format!("house_id: {} → {}", a.house_id, b.house_id));
        }
        if a.items.len() != b.items.len() {
            changes.push(format!("items count: {} → {}", a.items.len(), b.items.len()));
        } else {
            for (i, (ia, ib)) in a.items.iter().zip(b.items.iter()).enumerate() {
                if ia != ib {
                    changes.push(format!("item[{}] changed", i));
                }
            }
        }
        changes
    }
}

// ===========================================================================
// Stitcher
// ===========================================================================

/// Combines multiple `MapData` maps into one.
///
/// Handles tile deduplication, offset shifting, and merges towns, waypoints,
/// spawns, and NPC spawns.
pub struct Stitcher {
    /// Offset to apply to all tiles in stitched maps.
    pub offset_x: u16,
    /// Offset to apply to all tiles in stitched maps.
    pub offset_y: u16,
}

impl Stitcher {
    /// Create a new stitcher with the given offset.
    pub fn new(offset_x: u16, offset_y: u16) -> Self {
        Self { offset_x, offset_y }
    }

    /// Create a stitcher with no offset.
    pub fn identity() -> Self {
        Self {
            offset_x: 0,
            offset_y: 0,
        }
    }

    /// Stitch multiple maps into a single map.
    ///
    /// Each subsequent map is offset by `(offset_x, offset_y)` from the previous.
    pub fn stitch(&self, maps: &[&MapData]) -> MapData {
        if maps.is_empty() {
            return MapData::new();
        }

        // Use the first map's settings as base
        let base = &maps[0];
        let mut result = MapData {
            width: base.width,
            height: base.height,
            description: base.description.clone(),
            otbm_version: base.otbm_version,
            otb_major_version: base.otb_major_version,
            otb_minor_version: base.otb_minor_version,
            ..MapData::new()
        };

        let mut tile_positions: HashSet<(u16, u16, u8)> = HashSet::new();
        let mut next_offset_x: u16 = 0;
        let mut next_offset_y: u16 = 0;

        for (map_idx, map) in maps.iter().enumerate() {
            let ox = if map_idx == 0 {
                0
            } else {
                next_offset_x
            };
            let oy = if map_idx == 0 {
                0
            } else {
                next_offset_y
            };

            // Add tiles with offset
            for tile in &map.tiles {
                let nx = tile.x.wrapping_add(ox);
                let ny = tile.y.wrapping_add(oy);
                let pos = (nx, ny, tile.z);
                if tile_positions.insert(pos) {
                    result.tiles.push(TileData {
                        x: nx,
                        y: ny,
                        z: tile.z,
                        ground_id: tile.ground_id,
                        items: tile.items.clone(),
                        flags: tile.flags,
                        house_id: tile.house_id,
                    });
                }
            }

            // Merge towns (deduplicate by ID)
            let mut town_ids: HashSet<u32> =
                result.towns.iter().map(|t| t.id).collect();
            for town in &map.towns {
                if town_ids.insert(town.id) {
                    result.towns.push(town.clone());
                }
            }

            // Merge waypoints (deduplicate by name)
            let wp_names: HashSet<&str> =
                result.waypoints.iter().map(|w| w.name.as_str()).collect();
            let mut new_wps = Vec::new();
            for wp in &map.waypoints {
                if !wp_names.contains(wp.name.as_str()) {
                    let mut new_wp = wp.clone();
                    if map_idx > 0 {
                        new_wp.pos.x = new_wp.pos.x.wrapping_add(ox);
                        new_wp.pos.y = new_wp.pos.y.wrapping_add(oy);
                    }
                    new_wps.push(new_wp);
                }
            }
            result.waypoints.extend(new_wps);

            // Merge spawns
            for spawn in &map.spawns {
                let mut new_spawn = spawn.clone();
                if map_idx > 0 {
                    new_spawn.x = new_spawn.x.wrapping_add(ox);
                    new_spawn.y = new_spawn.y.wrapping_add(oy);
                }
                result.spawns.push(new_spawn);
            }

            // Merge NPC spawns
            for npc in &map.npc_spawns {
                let mut new_npc = npc.clone();
                if map_idx > 0 {
                    new_npc.x = new_npc.x.wrapping_add(ox);
                    new_npc.y = new_npc.y.wrapping_add(oy);
                }
                result.npc_spawns.push(new_npc);
            }

            // Update offset for next map
            next_offset_x = ox.wrapping_add(self.offset_x);
            next_offset_y = oy.wrapping_add(self.offset_y);
        }

        result
    }

    /// Stitch two maps together.
    pub fn stitch_two(a: &MapData, b: &MapData) -> MapData {
        Stitcher::new(0, 0).stitch(&[a, b])
    }
}

// ===========================================================================
// RegionExtractor
// ===========================================================================

/// Extracts sub-regions from a map.
pub struct RegionExtractor;

impl RegionExtractor {
    /// Extract a rectangular region from the map.
    ///
    /// Only tiles within the bounding box `[x1..=x2, y1..=y2, z1..=z2]` are
    /// included.  All towns, waypoints, spawns, and NPC spawns within the
    /// region are also extracted.
    pub fn extract_region(
        map: &MapData,
        x1: u16,
        y1: u16,
        z1: u8,
        x2: u16,
        y2: u16,
        z2: u8,
    ) -> MapData {
        let mut result = MapData::with_dimensions(
            x2.saturating_sub(x1).saturating_add(1),
            y2.saturating_sub(y1).saturating_add(1),
        );

        result.description = format!(
            "Region [{},{},{}] - [{},{},{}]",
            x1, y1, z1, x2, y2, z2
        );
        result.otbm_version = map.otbm_version;
        result.otb_major_version = map.otb_major_version;
        result.otb_minor_version = map.otb_minor_version;

        // Extract tiles
        for tile in &map.tiles {
            if tile.x >= x1 && tile.x <= x2 && tile.y >= y1 && tile.y <= y2 && tile.z >= z1 && tile.z <= z2
            {
                let mut new_tile = tile.clone();
                new_tile.x = new_tile.x.saturating_sub(x1);
                new_tile.y = new_tile.y.saturating_sub(y1);
                new_tile.z = new_tile.z.saturating_sub(z1);
                result.tiles.push(new_tile);
            }
        }

        // Extract towns
        for town in &map.towns {
            if town.temple.x >= x1
                && town.temple.x <= x2
                && town.temple.y >= y1
                && town.temple.y <= y2
                && town.temple.z >= z1
                && town.temple.z <= z2
            {
                let mut new_town = town.clone();
                new_town.temple.x = new_town.temple.x.saturating_sub(x1);
                new_town.temple.y = new_town.temple.y.saturating_sub(y1);
                new_town.temple.z = new_town.temple.z.saturating_sub(z1);
                result.towns.push(new_town);
            }
        }

        // Extract waypoints
        for wp in &map.waypoints {
            if wp.pos.x >= x1
                && wp.pos.x <= x2
                && wp.pos.y >= y1
                && wp.pos.y <= y2
                && wp.pos.z >= z1
                && wp.pos.z <= z2
            {
                let mut new_wp = wp.clone();
                new_wp.pos.x = new_wp.pos.x.saturating_sub(x1);
                new_wp.pos.y = new_wp.pos.y.saturating_sub(y1);
                new_wp.pos.z = new_wp.pos.z.saturating_sub(z1);
                result.waypoints.push(new_wp);
            }
        }

        // Extract spawns
        for spawn in &map.spawns {
            if spawn.x >= x1
                && spawn.x <= x2
                && spawn.y >= y1
                && spawn.y <= y2
                && spawn.z >= z1
                && spawn.z <= z2
            {
                let mut new_spawn = spawn.clone();
                new_spawn.x = new_spawn.x.saturating_sub(x1);
                new_spawn.y = new_spawn.y.saturating_sub(y1);
                new_spawn.z = new_spawn.z.saturating_sub(z1);
                result.spawns.push(new_spawn);
            }
        }

        // Extract NPC spawns
        for npc in &map.npc_spawns {
            if npc.x >= x1 && npc.x <= x2 && npc.y >= y1 && npc.y <= y2 && npc.z >= z1 && npc.z <= z2 {
                let mut new_npc = npc.clone();
                new_npc.x = new_npc.x.saturating_sub(x1);
                new_npc.y = new_npc.y.saturating_sub(y1);
                new_npc.z = new_npc.z.saturating_sub(z1);
                result.npc_spawns.push(new_npc);
            }
        }

        result
    }
}

// ===========================================================================
// MapComposer
// ===========================================================================

/// Orchestrates generators to build complete maps.
///
/// This is a high-level builder that can assemble a map from components like
/// terrain, structures, spawns, towns, etc.
pub struct MapComposer {
    map: MapData,
}

impl MapComposer {
    /// Create a new composer with a base map.
    pub fn new(map: MapData) -> Self {
        Self { map }
    }

    /// Create a new composer with default empty map settings.
    pub fn empty(width: u16, height: u16) -> Self {
        Self {
            map: MapData::with_dimensions(width, height),
        }
    }

    /// Create a composer for OTBM v3.
    pub fn empty_v3(width: u16, height: u16) -> Self {
        Self {
            map: MapData {
                width,
                height,
                ..MapData::new_v3()
            },
        }
    }

    /// Get a reference to the current map state.
    pub fn map(&self) -> &MapData {
        &self.map
    }

    /// Get a mutable reference to the current map state.
    pub fn map_mut(&mut self) -> &mut MapData {
        &mut self.map
    }

    /// Set the map description.
    pub fn with_description(mut self, desc: impl Into<String>) -> Self {
        self.map.description = desc.into();
        self
    }

    /// Add tiles from a tile iterator or slice.
    pub fn add_tiles(mut self, tiles: Vec<TileData>) -> Self {
        self.map.tiles.extend(tiles);
        self
    }

    /// Add a town.
    pub fn add_town(mut self, town: TownData) -> Self {
        self.map.towns.push(town);
        self
    }

    /// Add a waypoint.
    pub fn add_waypoint(mut self, wp: WaypointData) -> Self {
        self.map.waypoints.push(wp);
        self
    }

    /// Add a spawn.
    pub fn add_spawn(mut self, spawn: SpawnData) -> Self {
        self.map.spawns.push(spawn);
        self
    }

    /// Add an NPC spawn.
    pub fn add_npc_spawn(mut self, npc: NPCSpawnData) -> Self {
        self.map.npc_spawns.push(npc);
        self
    }

    /// Add a house.
    pub fn add_house(mut self, house: HouseData) -> Self {
        self.map.houses.push(house);
        self
    }

    /// Set external file references.
    pub fn with_ext_files(
        mut self,
        spawn: impl Into<String>,
        house: impl Into<String>,
        npc: impl Into<String>,
    ) -> Self {
        self.map.ext_spawn_file = spawn.into();
        self.map.ext_house_file = house.into();
        self.map.ext_spawn_npc_file = npc.into();
        self
    }

    /// Validate the current map state.
    pub fn validate(&self) -> Vec<ValidationIssue> {
        MapValidator::validate(&self.map)
    }

    /// Build and return the final map.
    pub fn build(self) -> MapData {
        self.map
    }

    /// Build, validate, and return the map. Returns `(map, issues)`.
    pub fn build_validated(self) -> (MapData, Vec<ValidationIssue>) {
        let issues = MapValidator::validate(&self.map);
        (self.map, issues)
    }

    /// Build the map and write it as OTBM bytes.
    pub fn build_otbm(self) -> Vec<u8> {
        otbforge_otbm::write_otbm(&self.map)
    }
}

// ===========================================================================
// Tests
// ===========================================================================

#[cfg(test)]
mod tests {
    use super::*;

    // ----- MapValidator Tests -----

    #[test]
    fn test_validate_empty_map() {
        let map = MapData::new();
        let issues = MapValidator::validate(&map);
        // Empty map should have at least one warning
        assert!(issues.iter().any(|i| i.category == "map" && i.severity == Severity::Warning));
    }

    #[test]
    fn test_validate_good_map() {
        let mut map = MapData::with_dimensions(512, 512);
        map.add_tile(10, 20, 7, tiles::GRASS);
        map.add_town(1, "Thais", Position::new(100, 200, 7));

        let issues = MapValidator::validate(&map);
        let errors: Vec<_> = issues.iter().filter(|i| i.severity == Severity::Error).collect();
        assert!(errors.is_empty(), "unexpected errors: {:?}", errors);
    }

    #[test]
    fn test_validate_zero_dimensions() {
        let map = MapData {
            width: 0,
            height: 2048,
            ..MapData::new()
        };
        let issues = MapValidator::check_dimensions(&map);
        assert!(issues.iter().any(|i| i.severity == Severity::Error));
    }

    #[test]
    fn test_validate_large_dimensions() {
        let map = MapData {
            width: 4096,
            height: 4096,
            ..MapData::new()
        };
        let issues = MapValidator::check_dimensions(&map);
        assert!(issues.iter().any(|i| i.severity == Severity::Info));
    }

    #[test]
    fn test_validate_tile_out_of_bounds() {
        let mut map = MapData::with_dimensions(100, 100);
        map.add_tile(200, 200, 7, tiles::GRASS);

        let issues = MapValidator::check_tiles_bounds(&map);
        assert!(!issues.is_empty());
        assert!(issues[0].severity == Severity::Error);
    }

    #[test]
    fn test_validate_no_ground() {
        let mut map = MapData::with_dimensions(512, 512);
        map.add_tile(10, 20, 7, 0);

        let issues = MapValidator::check_ground_ids(&map);
        assert_eq!(issues.len(), 1);
        assert!(issues[0].severity == Severity::Warning);
    }

    #[test]
    fn test_validate_duplicate_tiles() {
        let mut map = MapData::with_dimensions(512, 512);
        map.add_tile(10, 20, 7, tiles::GRASS);
        map.add_tile(10, 20, 7, tiles::DIRT);

        let issues = MapValidator::check_no_duplicate_tiles(&map);
        assert_eq!(issues.len(), 1);
        assert!(issues[0].severity == Severity::Error);
    }

    #[test]
    fn test_validate_invalid_item_id() {
        let mut map = MapData::with_dimensions(512, 512);
        map.add_tile(10, 20, 7, tiles::GRASS);
        map.tiles[0].items.push(ItemData::new(0));

        let issues = MapValidator::check_tile_items_valid(&map);
        assert_eq!(issues.len(), 1);
    }

    #[test]
    fn test_validate_container_depth() {
        let mut map = MapData::with_dimensions(512, 512);
        // Create deeply nested container: depth 4 > MAX_CONTAINER_DEPTH(3)
        let deep = ItemData::new(1);
        let lvl3 = ItemData::new(2).with_child(deep);
        let lvl2 = ItemData::new(3).with_child(lvl3);
        let lvl1 = ItemData::new(4).with_child(lvl2);

        map.add_tile(10, 20, 7, tiles::GRASS);
        map.tiles[0].items.push(lvl1);

        let issues = MapValidator::check_container_depth(&map);
        assert_eq!(issues.len(), 1);
        assert!(issues[0].severity == Severity::Warning);
    }

    #[test]
    fn test_validate_house_tile_no_towns() {
        let mut map = MapData::with_dimensions(512, 512);
        map.add_tile_full(10, 20, 7, tiles::FLOOR_WOOD, TileFlags::NONE, 1);

        let issues = MapValidator::check_house_tiles_valid(&map);
        assert_eq!(issues.len(), 1);
        assert!(issues[0].severity == Severity::Warning);
    }

    #[test]
    fn test_validate_spawn_out_of_bounds() {
        let mut map = MapData::with_dimensions(100, 100);
        map.add_spawn(200, 200, 7, 5);

        let issues = MapValidator::check_spawns_bounds(&map);
        assert_eq!(issues.len(), 1);
    }

    #[test]
    fn test_validate_spawn_no_monsters() {
        let mut map = MapData::with_dimensions(512, 512);
        map.add_spawn(100, 200, 7, 5);
        // No monsters added

        let issues = MapValidator::check_spawn_monsters(&map);
        assert_eq!(issues.len(), 1);
    }

    #[test]
    fn test_validate_duplicate_towns() {
        let mut map = MapData::with_dimensions(512, 512);
        map.add_town(1, "Thais", Position::new(100, 200, 7));
        map.add_town(1, "Carlin", Position::new(300, 400, 7));

        let issues = MapValidator::check_towns_unique(&map);
        assert_eq!(issues.len(), 2); // both flagged
    }

    #[test]
    fn test_validate_duplicate_waypoints() {
        let mut map = MapData::with_dimensions(512, 512);
        map.add_waypoint("Temple", Position::new(100, 200, 7));
        map.add_waypoint("Temple", Position::new(300, 400, 7));

        let issues = MapValidator::check_waypoints_unique(&map);
        assert_eq!(issues.len(), 2);
    }

    #[test]
    fn test_validate_npc_spawn_out_of_bounds() {
        let mut map = MapData::with_dimensions(100, 100);
        map.add_npc_spawn(200, 200, 7, "Guide");

        let issues = MapValidator::check_npc_spawns_bounds(&map);
        assert_eq!(issues.len(), 1);
    }

    #[test]
    fn test_validate_summary() {
        let map = MapData::new();
        let issues = MapValidator::validate(&map);
        let summary = MapValidator::summary(&issues);
        assert!(summary["warnings"] > 0);
    }

    #[test]
    fn test_validate_is_valid() {
        let mut map = MapData::with_dimensions(512, 512);
        map.add_tile(10, 20, 7, tiles::GRASS);
        assert!(MapValidator::is_valid(&map));

        map.add_tile(10, 20, 7, tiles::DIRT); // duplicate
        assert!(!MapValidator::is_valid(&map));
    }

    #[test]
    fn test_validate_issue_display() {
        let issue = ValidationIssue {
            severity: Severity::Error,
            category: "tiles".into(),
            message: "test message".into(),
            position: Some((10, 20, 7)),
        };
        let s = format!("{}", issue);
        assert!(s.contains("[error]"));
        assert!(s.contains("[tiles]"));
        assert!(s.contains("(10, 20, 7)"));
    }

    // ----- MapDiff Tests -----

    #[test]
    fn test_diff_identical_maps() {
        let mut map = MapData::with_dimensions(512, 512);
        map.add_tile(10, 20, 7, tiles::GRASS);

        let diffs = MapDiff::diff(&map, &map);
        assert!(diffs.is_empty());
    }

    #[test]
    fn test_diff_tile_added() {
        let mut a = MapData::with_dimensions(512, 512);
        a.add_tile(10, 20, 7, tiles::GRASS);

        let mut b = MapData::with_dimensions(512, 512);
        b.add_tile(10, 20, 7, tiles::GRASS);
        b.add_tile(30, 40, 7, tiles::DIRT);

        let diffs = MapDiff::diff(&a, &b);
        let added: Vec<_> = diffs.iter().filter_map(|d| match d {
            MapDifference::TileAdded(t) => Some(t),
            _ => None,
        }).collect();
        assert_eq!(added.len(), 1);
        assert_eq!(added[0].x, 30);
        assert_eq!(added[0].y, 40);
    }

    #[test]
    fn test_diff_tile_removed() {
        let mut a = MapData::with_dimensions(512, 512);
        a.add_tile(10, 20, 7, tiles::GRASS);
        a.add_tile(30, 40, 7, tiles::DIRT);

        let mut b = MapData::with_dimensions(512, 512);
        b.add_tile(10, 20, 7, tiles::GRASS);

        let diffs = MapDiff::diff(&a, &b);
        let removed: Vec<_> = diffs.iter().filter_map(|d| match d {
            MapDifference::TileRemoved(t) => Some(t),
            _ => None,
        }).collect();
        assert_eq!(removed.len(), 1);
        assert_eq!(removed[0].ground_id, tiles::DIRT);
    }

    #[test]
    fn test_diff_tile_changed_ground() {
        let mut a = MapData::with_dimensions(512, 512);
        a.add_tile(10, 20, 7, tiles::GRASS);

        let mut b = MapData::with_dimensions(512, 512);
        b.add_tile(10, 20, 7, tiles::DIRT);

        let diffs = MapDiff::diff(&a, &b);
        let changed: Vec<_> = diffs.iter().filter_map(|d| match d {
            MapDifference::TileChanged { pos, changes } => Some((pos, changes)),
            _ => None,
        }).collect();
        assert_eq!(changed.len(), 1);
        assert!(changed[0].1.iter().any(|c| c.contains("ground_id")));
    }

    #[test]
    fn test_diff_town_added() {
        let a = MapData::with_dimensions(512, 512);
        let mut b = MapData::with_dimensions(512, 512);
        b.add_town(1, "Thais", Position::new(100, 200, 7));

        let diffs = MapDiff::diff(&a, &b);
        assert!(diffs.iter().any(|d| matches!(d, MapDifference::TownAdded(1))));
    }

    // ----- Stitcher Tests -----

    #[test]
    fn test_stitch_empty() {
        let stitcher = Stitcher::new(100, 100);
        let result = stitcher.stitch(&[]);
        assert!(result.tiles.is_empty());
    }

    #[test]
    fn test_stitch_single_map() {
        let mut map = MapData::with_dimensions(512, 512);
        map.add_tile(10, 20, 7, tiles::GRASS);

        let stitcher = Stitcher::identity();
        let result = stitcher.stitch(&[&map]);
        assert_eq!(result.tiles.len(), 1);
        assert_eq!(result.tiles[0].x, 10);
    }

    #[test]
    fn test_stitch_two_maps() {
        let mut a = MapData::with_dimensions(512, 512);
        a.add_tile(10, 20, 7, tiles::GRASS);

        let mut b = MapData::with_dimensions(512, 512);
        b.add_tile(5, 5, 7, tiles::DIRT);

        let stitcher = Stitcher::new(100, 100);
        let result = stitcher.stitch(&[&a, &b]);
        assert_eq!(result.tiles.len(), 2);
        // First map tiles at original positions
        assert_eq!(result.tiles[0].x, 10);
        // Second map tiles offset by (100, 100)
        assert_eq!(result.tiles[1].x, 105);
        assert_eq!(result.tiles[1].y, 105);
    }

    #[test]
    fn test_stitch_dedup_towns() {
        let mut a = MapData::with_dimensions(512, 512);
        a.add_town(1, "Thais", Position::new(100, 200, 7));

        let mut b = MapData::with_dimensions(512, 512);
        b.add_town(1, "Thais", Position::new(100, 200, 7));
        b.add_town(2, "Carlin", Position::new(300, 400, 7));

        let stitcher = Stitcher::identity();
        let result = stitcher.stitch(&[&a, &b]);
        // Town 1 should only appear once
        assert_eq!(result.towns.len(), 2);
    }

    #[test]
    fn test_stitch_two_convenience() {
        let mut a = MapData::with_dimensions(512, 512);
        a.add_tile(10, 20, 7, tiles::GRASS);

        let mut b = MapData::with_dimensions(512, 512);
        b.add_tile(5, 5, 7, tiles::DIRT);

        let stitcher = Stitcher::new(100, 0);
        let result = Stitcher::stitch_two(&a, &b);
        assert_eq!(result.tiles.len(), 2);
    }

    // ----- RegionExtractor Tests -----

    #[test]
    fn test_extract_region() {
        let mut map = MapData::with_dimensions(512, 512);
        map.add_tile(10, 20, 7, tiles::GRASS);
        map.add_tile(110, 220, 7, tiles::DIRT);
        map.add_tile(10, 20, 6, tiles::SAND);

        let result = RegionExtractor::extract_region(&map, 0, 0, 7, 50, 50, 7);
        assert_eq!(result.tiles.len(), 1);
        assert_eq!(result.tiles[0].x, 10);
        assert_eq!(result.tiles[0].y, 20);
    }

    #[test]
    fn test_extract_region_shifts_coords() {
        let mut map = MapData::with_dimensions(512, 512);
        map.add_tile(100, 200, 7, tiles::GRASS);

        let result = RegionExtractor::extract_region(&map, 50, 50, 0, 200, 200, 15);
        assert_eq!(result.tiles.len(), 1);
        // Coordinates should be shifted: 100-50=50, 200-50=150
        assert_eq!(result.tiles[0].x, 50);
        assert_eq!(result.tiles[0].y, 150);
    }

    #[test]
    fn test_extract_region_empty() {
        let mut map = MapData::with_dimensions(512, 512);
        map.add_tile(100, 200, 7, tiles::GRASS);

        let result = RegionExtractor::extract_region(&map, 0, 0, 0, 10, 10, 0);
        assert!(result.tiles.is_empty());
    }

    #[test]
    fn test_extract_region_with_towns() {
        let mut map = MapData::with_dimensions(512, 512);
        map.add_town(1, "Thais", Position::new(100, 200, 7));

        let result = RegionExtractor::extract_region(&map, 0, 0, 0, 200, 200, 15);
        assert_eq!(result.towns.len(), 1);
    }

    // ----- MapComposer Tests -----

    #[test]
    fn test_composer_empty() {
        let composer = MapComposer::empty(512, 512);
        let map = composer.build();
        assert_eq!(map.width, 512);
        assert!(map.tiles.is_empty());
    }

    #[test]
    fn test_composer_v3() {
        let composer = MapComposer::empty_v3(1024, 1024);
        let map = composer.build();
        assert_eq!(map.otbm_version, 3);
        assert_eq!(map.otb_major_version, 3);
    }

    #[test]
    fn test_composer_with_description() {
        let composer = MapComposer::empty(512, 512).with_description("My Test Map");
        let map = composer.build();
        assert_eq!(map.description, "My Test Map");
    }

    #[test]
    fn test_composer_add_tiles() {
        let tiles = vec![
            TileData::new(10, 20, 7, tiles::GRASS),
            TileData::new(30, 40, 7, tiles::DIRT),
        ];
        let composer = MapComposer::empty(512, 512).add_tiles(tiles);
        let map = composer.build();
        assert_eq!(map.tiles.len(), 2);
    }

    #[test]
    fn test_composer_add_town() {
        let composer = MapComposer::empty(512, 512)
            .add_town(TownData::new(1, "Thais", Position::new(100, 200, 7)));
        let map = composer.build();
        assert_eq!(map.towns.len(), 1);
    }

    #[test]
    fn test_composer_add_waypoint() {
        let composer = MapComposer::empty(512, 512)
            .add_waypoint(WaypointData::new("Temple", Position::new(100, 200, 7)));
        let map = composer.build();
        assert_eq!(map.waypoints.len(), 1);
    }

    #[test]
    fn test_composer_add_spawn() {
        let composer = MapComposer::empty(512, 512)
            .add_spawn(SpawnData::new(100, 200, 7, 10));
        let map = composer.build();
        assert_eq!(map.spawns.len(), 1);
    }

    #[test]
    fn test_composer_add_npc() {
        let composer = MapComposer::empty(512, 512)
            .add_npc_spawn(NPCSpawnData::new(100, 200, 7, "Guide"));
        let map = composer.build();
        assert_eq!(map.npc_spawns.len(), 1);
    }

    #[test]
    fn test_composer_add_house() {
        let composer = MapComposer::empty(512, 512)
            .add_house(HouseData::new(1, "Castle", 1));
        let map = composer.build();
        assert_eq!(map.houses.len(), 1);
    }

    #[test]
    fn test_composer_with_ext_files() {
        let composer = MapComposer::empty(512, 512)
            .with_ext_files("spawns.xml", "houses.xml", "npcs.xml");
        let map = composer.build();
        assert_eq!(map.ext_spawn_file, "spawns.xml");
        assert_eq!(map.ext_house_file, "houses.xml");
        assert_eq!(map.ext_spawn_npc_file, "npcs.xml");
    }

    #[test]
    fn test_composer_validate() {
        let composer = MapComposer::empty(512, 512);
        let issues = composer.validate();
        // Empty map has a warning
        assert!(!issues.is_empty());
    }

    #[test]
    fn test_composer_build_validated() {
        let mut composer = MapComposer::empty(512, 512);
        composer.map_mut().add_tile(10, 20, 7, tiles::GRASS);
        let (map, issues) = composer.build_validated();
        assert_eq!(map.tiles.len(), 1);
    }

    #[test]
    fn test_composer_build_otbm() {
        let mut composer = MapComposer::empty(512, 512);
        composer.map_mut().add_tile(10, 20, 7, tiles::GRASS);
        let bytes = composer.build_otbm();
        // Should start with OTBM magic
        assert_eq!(&bytes[0..4], OTBM_MAGIC);
    }

    #[test]
    fn test_composer_chain() {
        let map = MapComposer::empty(1024, 1024)
            .with_description("Chained Map")
            .add_town(TownData::new(1, "City", Position::new(100, 200, 7)))
            .add_waypoint(WaypointData::new("Home", Position::new(100, 200, 7)))
            .add_spawn(SpawnData::new(100, 200, 7, 10))
            .add_npc_spawn(NPCSpawnData::new(100, 200, 7, "Guide"))
            .add_house(HouseData::new(1, "Villa", 1))
            .build();

        assert_eq!(map.description, "Chained Map");
        assert_eq!(map.towns.len(), 1);
        assert_eq!(map.waypoints.len(), 1);
        assert_eq!(map.spawns.len(), 1);
        assert_eq!(map.npc_spawns.len(), 1);
        assert_eq!(map.houses.len(), 1);
    }

    #[test]
    fn test_map_difference_display() {
        let d = MapDifference::TileAdded(TileData::new(10, 20, 7, 102));
        let s = format!("{}", d);
        assert!(s.contains("Tile added"));
        assert!(s.contains("10, 20, 7"));
    }
}
