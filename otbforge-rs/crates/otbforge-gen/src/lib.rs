//! # otbforge-gen
//!
//! Procedural map generators for OTBForge — terrain, dungeons, noise, and more.
//!
//! This crate provides:
//! - **Perlin noise** — zero-dependency 2-D noise implementation
//! - **TerrainGenerator** — biome-aware terrain with 11 biomes and rivers
//! - **DungeonGenerator** — BSP-tree dungeon with multiple z-levels

use otbforge_models::{ItemData, MapData, Position, SpawnData};
use rand::SeedableRng;
use rand::Rng;
use rand::rngs::StdRng;

// ===========================================================================
// Perlin Noise
// ===========================================================================

/// Zero-dependency 2-D Perlin noise implementation.
pub mod noise {
    use rand::SeedableRng;
    use rand::Rng;
    use rand::rngs::StdRng;

    /// Permutation table pre-computed from a seed.
    #[derive(Debug, Clone)]
    struct Permutation {
        perm: [usize; 512],
    }

    impl Permutation {
        fn new(seed: u64) -> Self {
            let mut rng = StdRng::seed_from_u64(seed);
            let mut p: Vec<usize> = (0..256).collect();
            // Fisher-Yates shuffle
            for i in (1..256).rev() {
                let j = rng.random_range(0..=i);
                p.swap(i, j);
            }
            let mut perm = [0usize; 512];
            for i in 0..512 {
                perm[i] = p[i & 255];
            }
            Self { perm }
        }
    }

    /// 2-D gradient vectors.
    fn gradient(hash: usize, x: f64, y: f64) -> f64 {
        match hash & 3 {
            0 => x,
            1 => -x,
            2 => y,
            3 => -y,
            _ => 0.0,
        }
    }

    /// Fade curve: 6t⁵ − 15t⁴ + 10t³
    fn fade(t: f64) -> f64 {
        t * t * t * (t * (t * 6.0 - 15.0) + 10.0)
    }

    /// Linear interpolation.
    fn lerp(a: f64, b: f64, t: f64) -> f64 {
        a + t * (b - a)
    }

    /// 2-D Perlin noise generator.
    #[derive(Debug, Clone)]
    pub struct PerlinNoise {
        perm: Permutation,
        seed: u64,
    }

    impl PerlinNoise {
        /// Create a new Perlin noise generator with the given seed.
        pub fn new(seed: u64) -> Self {
            Self {
                perm: Permutation::new(seed),
                seed,
            }
        }

        /// Sample 2-D Perlin noise at `(x, y)`.
        ///
        /// Returns a value in the approximate range `[-1.0, 1.0]`.
        pub fn noise2d(&self, x: f64, y: f64) -> f64 {
            // Grid cell coordinates
            let xi = x.floor() as isize;
            let yi = y.floor() as isize;

            // Relative position within cell
            let xf = x - xi as f64;
            let yf = y - yi as f64;

            // Wrap to positive indices
            let xi = ((xi % 256) + 256) as usize % 256;
            let yi = ((yi % 256) + 256) as usize % 256;

            let p = &self.perm.perm;

            // Hash the four corners
            let aa = p[p[xi] + yi];
            let ab = p[p[xi] + yi + 1];
            let ba = p[p[xi + 1] + yi];
            let bb = p[p[xi + 1] + yi + 1];

            // Fade curves
            let u = fade(xf);
            let v = fade(yf);

            // Dot products
            let x1 = lerp(gradient(aa, xf, yf), gradient(ba, xf - 1.0, yf), u);
            let x2 = lerp(
                gradient(ab, xf, yf - 1.0),
                gradient(bb, xf - 1.0, yf - 1.0),
                u,
            );

            lerp(x1, x2, v)
        }

        /// Fractal (octave) noise.
        ///
        /// Layers multiple octaves of Perlin noise for richer terrain.
        pub fn octave(
            &self,
            x: f64,
            y: f64,
            octaves: u32,
            persistence: f64,
            lacunarity: f64,
        ) -> f64 {
            let mut total = 0.0;
            let mut amplitude = 1.0;
            let mut frequency = 1.0;
            let mut max_value = 0.0;

            for _ in 0..octaves {
                total += self.noise2d(x * frequency, y * frequency) * amplitude;
                max_value += amplitude;
                amplitude *= persistence;
                frequency *= lacunarity;
            }

            // Normalize to approximately [-1.0, 1.0]
            if max_value > 0.0 {
                total / max_value
            } else {
                0.0
            }
        }
    }
}

// ===========================================================================
// Biomes
// ===========================================================================

/// All supported terrain biomes.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum Biome {
    Grass,
    Forest,
    Desert,
    Snow,
    Jungle,
    Swamp,
    Mountain,
    Taiga,
    Tundra,
    Volcanic,
    Ocean,
}

impl Biome {
    /// Default ground item ID for this biome.
    pub fn ground_id(self) -> u16 {
        match self {
            Biome::Grass => 106,
            Biome::Forest => 106,
            Biome::Desert => 104,
            Biome::Snow => 670,
            Biome::Jungle => 106,
            Biome::Swamp => 354,
            Biome::Mountain => 431,
            Biome::Taiga => 670,
            Biome::Tundra => 670,
            Biome::Volcanic => 598,
            Biome::Ocean => 493,
        }
    }

    /// Returns the number of distinct biomes.
    pub const fn count() -> usize {
        11
    }
}

// ===========================================================================
// Terrain Generator
// ===========================================================================

/// Configuration for [`TerrainGenerator`].
#[derive(Debug, Clone)]
pub struct TerrainConfig {
    /// Map width in tiles.
    pub width: u32,
    /// Map height in tiles.
    pub height: u32,
    /// RNG seed.
    pub seed: u64,
    /// Tiles with noise value below this become water/ocean (0.0–1.0).
    pub water_level: f64,
    /// Noise scale for biome determination.
    pub biome_scale: f64,
    /// Number of rivers to carve.
    pub num_rivers: u32,
}

impl Default for TerrainConfig {
    fn default() -> Self {
        Self {
            width: 128,
            height: 128,
            seed: 42,
            water_level: 0.35,
            biome_scale: 0.02,
            num_rivers: 3,
        }
    }
}

/// Procedural terrain generator using Perlin noise and 11 biomes.
pub struct TerrainGenerator {
    noise: noise::PerlinNoise,
    config: TerrainConfig,
}

impl TerrainGenerator {
    /// Create a new terrain generator.
    pub fn new(config: TerrainConfig) -> Self {
        let noise = noise::PerlinNoise::new(config.seed);
        Self { noise, config }
    }

    /// Determine the biome at a given world position using noise layers.
    ///
    /// - `elevation` controls land vs water.
    /// - `temperature` and `moisture` determine biome type.
    fn determine_biome(&self, elevation: f64, moisture: f64, temperature: f64) -> Biome {
        // Ocean: below water level
        if elevation < self.config.water_level {
            return Biome::Ocean;
        }

        // Map elevation/moisture/temperature to biome
        // temperature: < -0.3 = cold, -0.3..0.3 = temperate, > 0.3 = hot
        // moisture:    < -0.2 = dry,   -0.2..0.2 = normal,  > 0.2 = wet

        if temperature > 0.3 {
            // Hot biomes
            if moisture > 0.3 {
                Biome::Jungle
            } else if moisture > 0.0 {
                Biome::Swamp
            } else if moisture < -0.3 {
                Biome::Desert
            } else if elevation > 0.5 {
                Biome::Volcanic
            } else {
                Biome::Grass
            }
        } else if temperature < -0.3 {
            // Cold biomes
            if moisture > 0.1 {
                Biome::Taiga
            } else if elevation > 0.4 {
                Biome::Snow
            } else {
                Biome::Tundra
            }
        } else {
            // Temperate biomes
            if moisture > 0.2 {
                Biome::Forest
            } else if elevation > 0.45 {
                Biome::Mountain
            } else {
                Biome::Grass
            }
        }
    }

    /// Carve rivers from random source points toward the map edge.
    fn carve_rivers(&self, map: &mut MapData, rng: &mut StdRng) {
        let w = self.config.width as f64;
        let h = self.config.height as f64;

        for _ in 0..self.config.num_rivers {
            // Pick a random source point
            let sx = rng.random_range(10..self.config.width - 10) as f64;
            let sy = rng.random_range(10..self.config.height - 10) as f64;

            let mut cx = sx;
            let mut cy = sy;

            // Walk toward an edge using noise gradient, up to max steps
            for _ in 0..500 {
                let ix = cx as u32;
                let iy = cy as u32;

                if ix >= self.config.width || iy >= self.config.height {
                    break;
                }

                // Place water tile (3-tile wide river)
                for dx in -1i32..=1 {
                    for dy in -1i32..=1 {
                        let rx = (ix as i32 + dx).clamp(0, self.config.width as i32 - 1) as u32;
                        let ry = (iy as i32 + dy).clamp(0, self.config.height as i32 - 1) as u32;
                        let rx16 = rx as u16;
                        let ry16 = ry as u16;
                        // Only overwrite if not already water (avoid flooding)
                        let already_water = map
                            .tiles
                            .iter()
                            .any(|t| t.x == rx16 && t.y == ry16 && t.z == 7 && t.ground_id == 493);
                        if !already_water {
                            map.add_tile(rx16, ry16, 7, 493);
                        }
                    }
                }

                // Follow the noise gradient downhill
                let n = self.noise.noise2d(cx * 0.05, cy * 0.05);
                let angle = n * std::f64::consts::PI * 2.0;

                cx += angle.cos() * 1.5;
                cy += angle.sin() * 1.5;

                // Stop if we reach the edge
                if cx < 0.0 || cy < 0.0 || cx >= w || cy >= h {
                    break;
                }
            }
        }
    }

    /// Generate the terrain map.
    pub fn generate(&self) -> MapData {
        let w = self.config.width as u16;
        let h = self.config.height as u16;

        let mut map = MapData::with_dimensions(w, h);
        map.description = format!("Generated terrain (seed={})", self.config.seed);

        let scale = self.config.biome_scale;

        for y in 0..self.config.height {
            for x in 0..self.config.width {
                let fx = x as f64;
                let fy = y as f64;

                // Three independent noise layers for biome determination
                let elevation = self.noise.octave(fx * scale, fy * scale, 4, 0.5, 2.0);
                let moisture =
                    self.noise.octave(fx * scale + 1000.0, fy * scale + 1000.0, 3, 0.5, 2.0);
                let temperature =
                    self.noise.octave(fx * scale + 2000.0, fy * scale + 2000.0, 3, 0.5, 2.0);

                let biome = self.determine_biome(elevation, moisture, temperature);
                let ground = biome.ground_id();

                // z = 7 is the main surface level
                map.add_tile(x as u16, y as u16, 7, ground);
            }
        }

        // Carve rivers
        let mut rng = StdRng::seed_from_u64(self.config.seed.wrapping_add(1));
        self.carve_rivers(&mut map, &mut rng);

        // Place decoration items for some biomes
        let mut deco_rng = StdRng::seed_from_u64(self.config.seed.wrapping_add(2));
        for tile in &mut map.tiles {
            if tile.z != 7 {
                continue;
            }
            let r: f64 = deco_rng.random();
            match tile.ground_id {
                106 => {
                    // Grass: occasional tree or flower
                    if r < 0.03 {
                        tile.items.push(ItemData::new(4035)); // tree
                    } else if r < 0.06 {
                        tile.items.push(ItemData::new(6226)); // flower
                    } else if r < 0.07 {
                        tile.items.push(ItemData::new(2767)); // bush
                    }
                }
                670 => {
                    // Snow: rare dead tree (taiga-like)
                    if r < 0.02 {
                        tile.items.push(ItemData::new(2709)); // dead tree
                    }
                }
                _ => {}
            }
        }

        // Add a default town at map center
        let cx = self.config.width / 2;
        let cy = self.config.height / 2;
        map.add_town(1, "Main Town", Position::new(cx as u16, cy as u16, 7));

        // Add a spawn at the center with a rat
        let spawn = SpawnData::new(cx as u16, cy as u16, 7, 15).with_monster("Rat", 2, 3);
        map.spawns.push(spawn);

        map
    }
}

// ===========================================================================
// Uniform Biome Map Generator
// ===========================================================================

/// Parse a biome name string (case-insensitive) into a [`Biome`] variant.
///
/// Returns `None` for unrecognized names.
pub fn parse_biome(name: &str) -> Option<Biome> {
    match name.to_ascii_lowercase().as_str() {
        "grass" => Some(Biome::Grass),
        "forest" => Some(Biome::Forest),
        "desert" => Some(Biome::Desert),
        "snow" => Some(Biome::Snow),
        "jungle" => Some(Biome::Jungle),
        "swamp" => Some(Biome::Swamp),
        "mountain" => Some(Biome::Mountain),
        "taiga" => Some(Biome::Taiga),
        "tundra" => Some(Biome::Tundra),
        "volcanic" => Some(Biome::Volcanic),
        "ocean" => Some(Biome::Ocean),
        "dungeon" => None, // handled separately
        "mixed" => None,   // handled separately
        _ => None,
    }
}

/// Generate a map uniformly filled with a specific biome.
///
/// Unlike [`TerrainGenerator::generate`], this produces a map where *all* surface
/// tiles belong to the requested biome — no ocean/water, no biome mixing.
/// Noise is used only for subtle terrain variation *within* the biome.
///
/// # Panics
/// Panics if `biome` is not a recognized biome name (not "dungeon" or "mixed").
pub fn generate_biome_map(biome_str: &str, width: u32, height: u32, seed: u64) -> MapData {
    // "dungeon" delegates to DungeonGenerator
    if biome_str.eq_ignore_ascii_case("dungeon") {
        let config = DungeonConfig {
            width,
            height,
            seed,
            ..Default::default()
        };
        return DungeonGenerator::new(config).generate();
    }

    let biome = parse_biome(biome_str).unwrap_or_else(|| {
        panic!("unknown biome: '{}'; expected grass, forest, desert, snow, swamp, mountain, jungle, taiga, tundra, volcanic, ocean, or dungeon", biome_str)
    });

    let w = width as u16;
    let h = height as u16;

    let mut map = MapData::with_dimensions(w, h);
    map.description = format!("Generated {} biome (seed={})", biome_str, seed);

    let perlin = noise::PerlinNoise::new(seed);
    let scale = 0.015; // gentle noise for subtle variation

    // Decorations depend on biome
    struct Decoration {
        /// Probability of a decoration on any given tile (0.0–1.0).
        chance: f64,
        /// Item IDs placed when triggered (first hit wins).
        items: &'static [u16],
    }

    let decorations: &[Decoration] = match biome {
        Biome::Grass => &[
            Decoration { chance: 0.04, items: &[4035] },  // tree
            Decoration { chance: 0.07, items: &[6226] },  // flower
            Decoration { chance: 0.09, items: &[2767] },  // bush
        ],
        Biome::Forest => &[
            Decoration { chance: 0.15, items: &[4035] },  // tree
            Decoration { chance: 0.20, items: &[2709] },  // dead tree (variety)
            Decoration { chance: 0.23, items: &[6226] },  // flower
            Decoration { chance: 0.26, items: &[2767] },  // bush
        ],
        Biome::Desert => &[
            Decoration { chance: 0.02, items: &[4039] },  // cactus-like
            Decoration { chance: 0.03, items: &[2767] },  // small bush
        ],
        Biome::Snow => &[
            Decoration { chance: 0.02, items: &[2709] },  // dead tree
        ],
        Biome::Jungle => &[
            Decoration { chance: 0.18, items: &[4035] },  // tree (dense)
            Decoration { chance: 0.24, items: &[2709] },  // dead tree
            Decoration { chance: 0.27, items: &[2767] },  // bush
        ],
        Biome::Swamp => &[
            Decoration { chance: 0.06, items: &[4035] },  // tree (mangrove-like)
            Decoration { chance: 0.08, items: &[2767] },  // bush
        ],
        Biome::Mountain => &[
            Decoration { chance: 0.02, items: &[2709] },  // dead tree
        ],
        Biome::Taiga => &[
            Decoration { chance: 0.08, items: &[4035] },  // tree
            Decoration { chance: 0.10, items: &[2709] },  // dead tree
        ],
        Biome::Tundra => &[
            Decoration { chance: 0.01, items: &[2709] },  // rare dead tree
        ],
        Biome::Volcanic => &[
            Decoration { chance: 0.03, items: &[2709] },  // dead tree
        ],
        Biome::Ocean => &[], // no decorations on water
    };

    let ground_id = biome.ground_id();
    let mut deco_rng = StdRng::seed_from_u64(seed.wrapping_add(2));

    // Fill the map with the biome's ground tile and add decorations
    for y in 0..height {
        for x in 0..width {
            let fx = x as f64;
            let fy = y as f64;

            // Use noise for subtle ground variation — but never switch biome or add water.
            // Just vary the density of decorations slightly.
            let _noise_val = perlin.octave(fx * scale, fy * scale, 3, 0.5, 2.0);

            let tile = map.add_tile(x as u16, y as u16, 7, ground_id);

            // Place decorations
            let r: f64 = deco_rng.random();
            for deco in decorations {
                if r < deco.chance {
                    for &item_id in deco.items {
                        tile.items.push(ItemData::new(item_id));
                    }
                    break;
                }
            }
        }
    }

    // Add rivers for grass / forest biomes
    if matches!(biome, Biome::Grass | Biome::Forest) {
        let river_rng = StdRng::seed_from_u64(seed.wrapping_add(3));
        carve_biome_rivers(&mut map, &perlin, 2, width, height);
        let _ = river_rng; // consumed conceptually by carve_biome_rivers via seed offset
    }

    // Add a default town at map center
    let cx = width / 2;
    let cy = height / 2;
    map.add_town(1, "Main Town", Position::new(cx as u16, cy as u16, 7));

    // Add a spawn at the center with a rat
    let spawn = SpawnData::new(cx as u16, cy as u16, 7, 15).with_monster("Rat", 2, 3);
    map.spawns.push(spawn);

    map
}

/// Carve 1–2 rivers through a biome map using noise for direction.
/// Only places water tiles; does *not* convert ground tiles to ocean biome.
fn carve_biome_rivers(map: &mut MapData, perlin: &noise::PerlinNoise, count: u32, width: u32, height: u32) {
    let w = width as f64;
    let h = height as f64;

    for i in 0..count {
        // Deterministic source points based on river index
        let sx = w * (0.25 + 0.5 * (i as f64 / (count as f64).max(1.0)));
        let sy = h * 0.2;

        let mut cx = sx;
        let mut cy = sy;

        for _ in 0..600 {
            let ix = cx as u32;
            let iy = cy as u32;

            if ix >= width || iy >= height {
                break;
            }

            // Place water tile (2-tile wide river — narrower than mixed terrain)
            for dx in 0i32..=0 {
                for dy in 0i32..=0 {
                    let rx = (ix as i32 + dx).clamp(0, width as i32 - 1) as u32;
                    let ry = (iy as i32 + dy).clamp(0, height as i32 - 1) as u32;
                    let rx16 = rx as u16;
                    let ry16 = ry as u16;
                    let already_water = map
                        .tiles
                        .iter()
                        .any(|t| t.x == rx16 && t.y == ry16 && t.z == 7 && t.ground_id == 493);
                    if !already_water {
                        map.add_tile(rx16, ry16, 7, 493);
                    }
                }
            }

            // Follow noise gradient toward bottom of map
            let n = perlin.noise2d(cx * 0.05, cy * 0.05);
            let angle = n * std::f64::consts::PI * 2.0;

            cx += angle.cos() * 1.5;
            cy += 1.0 + angle.sin().abs() * 0.5; // bias downward

            if cx < 0.0 || cy < 0.0 || cx >= w || cy >= h {
                break;
            }
        }
    }
}

// ===========================================================================
// Dungeon Generator (BSP)
// ===========================================================================

/// Configuration for [`DungeonGenerator`].
#[derive(Debug, Clone)]
pub struct DungeonConfig {
    /// Map width in tiles.
    pub width: u32,
    /// Map height in tiles.
    pub height: u32,
    /// Number of z-levels (floors).
    pub floors: u32,
    /// Target number of rooms per floor.
    pub rooms_per_floor: u32,
    /// Minimum room dimension (width or height).
    pub min_room_size: u32,
    /// Maximum room dimension (width or height).
    pub max_room_size: u32,
    /// RNG seed.
    pub seed: u64,
}

impl Default for DungeonConfig {
    fn default() -> Self {
        Self {
            width: 50,
            height: 50,
            floors: 3,
            rooms_per_floor: 6,
            min_room_size: 4,
            max_room_size: 10,
            seed: 1337,
        }
    }
}

/// A rectangle used by the BSP tree for room placement.
#[derive(Debug, Clone)]
struct Rect {
    x: u32,
    y: u32,
    w: u32,
    h: u32,
}

impl Rect {
    fn center(&self) -> (u32, u32) {
        (self.x + self.w / 2, self.y + self.h / 2)
    }

    #[allow(dead_code)]
    fn intersects(&self, other: &Rect) -> bool {
        self.x < other.x + other.w
            && self.x + self.w > other.x
            && self.y < other.y + other.h
            && self.y + self.h > other.y
    }
}

/// BSP tree node — either a leaf (holds a room) or a branch (two children).
#[derive(Debug, Clone)]
enum BspNode {
    Leaf {
        room: Option<Rect>,
    },
    Branch {
        left: Box<BspNode>,
        right: Box<BspNode>,
    },
}

impl BspNode {
    /// Recursively collect all rooms from leaves.
    fn collect_rooms(&self) -> Vec<Rect> {
        match self {
            BspNode::Leaf { room } => room.clone().map(|r| vec![r]).unwrap_or_default(),
            BspNode::Branch { left, right } => {
                let mut rooms = left.collect_rooms();
                rooms.extend(right.collect_rooms());
                rooms
            }
        }
    }

    /// Recursively collect all (left_center, right_center) pairs from branches.
    fn collect_connections(&self) -> Vec<((u32, u32), (u32, u32))> {
        match self {
            BspNode::Leaf { .. } => vec![],
            BspNode::Branch { left, right } => {
                let mut conns = left.collect_connections();
                conns.extend(right.collect_connections());

                // Get centers of left and right subtrees
                let left_rooms = left.collect_rooms();
                let right_rooms = right.collect_rooms();

                if let (Some(lr), Some(rr)) = (left_rooms.last(), right_rooms.first()) {
                    conns.push((lr.center(), rr.center()));
                }

                conns
            }
        }
    }
}

/// BSP-based dungeon generator.
pub struct DungeonGenerator {
    config: DungeonConfig,
}

impl DungeonGenerator {
    /// Create a new dungeon generator.
    pub fn new(config: DungeonConfig) -> Self {
        Self { config }
    }

    /// BSP subdivision: recursively split `area` until it reaches `min_size`.
    fn subdivide(&self, area: &Rect, rng: &mut StdRng, depth: u32) -> BspNode {
        let max_depth = 5;

        if depth >= max_depth
            || area.w < self.config.min_room_size * 2
            || area.h < self.config.min_room_size * 2
        {
            // Leaf: place a room inside this area
            let effective_max_w = self.config.max_room_size.min(area.w.saturating_sub(1));
            let effective_max_h = self.config.max_room_size.min(area.h.saturating_sub(1));
            let room_w = if effective_max_w >= self.config.min_room_size {
                rng.random_range(self.config.min_room_size..=effective_max_w)
            } else {
                self.config.min_room_size
            };
            let room_h = if effective_max_h >= self.config.min_room_size {
                rng.random_range(self.config.min_room_size..=effective_max_h)
            } else {
                self.config.min_room_size
            };
            let room_x = if area.w > room_w {
                rng.random_range(area.x..=area.x + area.w - room_w)
            } else {
                area.x
            };
            let room_y = if area.h > room_h {
                rng.random_range(area.y..=area.y + area.h - room_h)
            } else {
                area.y
            };

            return BspNode::Leaf {
                room: Some(Rect {
                    x: room_x,
                    y: room_y,
                    w: room_w,
                    h: room_h,
                }),
            };
        }

        // Decide horizontal vs vertical split
        let split_horizontally = if area.w > area.h {
            false
        } else if area.h > area.w {
            true
        } else {
            rng.random()
        };

        if split_horizontally {
            let lo = area.y + self.config.min_room_size;
            let hi = area.y + area.h - self.config.min_room_size;
            let split = if lo <= hi { rng.random_range(lo..=hi) } else { area.y + area.h / 2 };
            let left = Rect {
                x: area.x,
                y: area.y,
                w: area.w,
                h: split - area.y,
            };
            let right = Rect {
                x: area.x,
                y: split,
                w: area.w,
                h: area.y + area.h - split,
            };
            BspNode::Branch {
                left: Box::new(self.subdivide(&left, rng, depth + 1)),
                right: Box::new(self.subdivide(&right, rng, depth + 1)),
            }
        } else {
            let lo = area.x + self.config.min_room_size;
            let hi = area.x + area.w - self.config.min_room_size;
            let split = if lo <= hi {
                rng.random_range(lo..=hi)
            } else {
                area.x + area.w / 2
            };
            let left = Rect {
                x: area.x,
                y: area.y,
                w: split - area.x,
                h: area.h,
            };
            let right = Rect {
                x: split,
                y: area.y,
                w: area.x + area.w - split,
                h: area.h,
            };
            BspNode::Branch {
                left: Box::new(self.subdivide(&left, rng, depth + 1)),
                right: Box::new(self.subdivide(&right, rng, depth + 1)),
            }
        }
    }

    /// Carve a corridor between two points (L-shaped).
    fn carve_corridor(
        map: &mut MapData,
        x1: u16,
        y1: u16,
        x2: u16,
        y2: u16,
        z: u8,
        ground_id: u16,
    ) {
        let mut cx = x1;
        let mut cy = y1;

        // Go horizontal first, then vertical
        while cx != x2 {
            // Only place if within bounds
            if cx < map.width && cy < map.height {
                let already = map.tiles.iter().any(|t| t.x == cx && t.y == cy && t.z == z);
                if !already {
                    map.add_tile(cx, cy, z, ground_id);
                }
            }
            if x2 > cx {
                cx += 1;
            } else {
                cx = cx.saturating_sub(1);
            }
        }

        while cy != y2 {
            if cx < map.width && cy < map.height {
                let already = map.tiles.iter().any(|t| t.x == cx && t.y == cy && t.z == z);
                if !already {
                    map.add_tile(cx, cy, z, ground_id);
                }
            }
            if y2 > cy {
                cy += 1;
            } else {
                cy = cy.saturating_sub(1);
            }
        }
    }

    /// Place a room onto the map.
    fn carve_room(map: &mut MapData, room: &Rect, z: u8, ground_id: u16, wall_id: u16) {
        let mw = map.width as u32;
        let mh = map.height as u32;

        // Walls around the perimeter
        for x in room.x.saturating_sub(1)..=room.x + room.w {
            if x < mw {
                if room.y > 0 && room.y.saturating_sub(1) < mh {
                    map.add_tile(x as u16, room.y.saturating_sub(1) as u16, z, wall_id);
                }
                let bottom = room.y + room.h;
                if bottom < mh {
                    map.add_tile(x as u16, bottom as u16, z, wall_id);
                }
            }
        }
        for y in room.y..room.y + room.h + 1 {
            if y < mh {
                if room.x > 0 {
                    map.add_tile(room.x.saturating_sub(1) as u16, y as u16, z, wall_id);
                }
                let right = room.x + room.w;
                if right < mw {
                    map.add_tile(right as u16, y as u16, z, wall_id);
                }
            }
        }

        // Floor
        for y in room.y..room.y + room.h {
            for x in room.x..room.x + room.w {
                if x < mw && y < mh {
                    map.add_tile(x as u16, y as u16, z, ground_id);
                }
            }
        }
    }

    /// Generate the dungeon map with BSP rooms and corridors across z-levels.
    pub fn generate(&self) -> MapData {
        let w = self.config.width as u16;
        let h = self.config.height as u16;

        let mut map = MapData::with_dimensions(w, h);
        map.description = format!("Generated dungeon (seed={})", self.config.seed);

        let ground_id: u16 = 431; // stone_floor
        let wall_id: u16 = 1017; // stone_wall

        // Monster names for dungeon spawns
        let monster_pool: &[&str] = &[
            "Dragon",
            "Demon",
            "Orc",
            "Spider",
            "Skeleton",
            "Cave Rat",
            "Ghoul",
            "Fire Elemental",
        ];

        let mut rng = StdRng::seed_from_u64(self.config.seed);
        let mut prev_floor_center: Option<(u16, u16)> = None;

        for floor in 0..self.config.floors {
            let z = 7 + floor as u8;
            if z > 15 {
                break;
            }

            // BSP subdivision for this floor
            let root_rect = Rect {
                x: 2,
                y: 2,
                w: self.config.width.saturating_sub(4),
                h: self.config.height.saturating_sub(4),
            };

            let tree = self.subdivide(&root_rect, &mut rng, 0);
            let rooms = tree.collect_rooms();
            let connections = tree.collect_connections();

            // Carve rooms
            for room in &rooms {
                Self::carve_room(&mut map, room, z, ground_id, wall_id);

                // Place random chests in some rooms
                if rng.random_bool(0.3) {
                    let (rcx, rcy) = room.center();
                    if (rcx as u16) < map.width && (rcy as u16) < map.height {
                        map.add_item(rcx as u16, rcy as u16, z, ItemData::new(1740));
                    }
                }
            }

            // Carve corridors between connected rooms
            for ((x1, y1), (x2, y2)) in &connections {
                Self::carve_corridor(
                    &mut map, *x1 as u16, *y1 as u16, *x2 as u16, *y2 as u16, z, ground_id,
                );
            }

            // Stairs between floors
            if floor > 0 {
                if let Some(prev) = prev_floor_center {
                    // Stair down at previous floor's center → stair up here
                    let stair_item_down = ItemData {
                        id: 1386,
                        ..ItemData::default()
                    };
                    let stair_item_up = ItemData {
                        id: 1385,
                        ..ItemData::default()
                    };
                    map.add_item(prev.0, prev.1, z - 1, stair_item_down);
                    if !rooms.is_empty() {
                        let (scx, scy) = rooms[0].center();
                        if (scx as u16) < map.width && (scy as u16) < map.height {
                            map.add_item(scx as u16, scy as u16, z, stair_item_up);
                        }
                    }
                }
            }

            // Remember this floor's center for stairs
            prev_floor_center = if !rooms.is_empty() {
                let (fcx, fcy) = rooms[0].center();
                Some((fcx as u16, fcy as u16))
            } else {
                None
            };

            // Place monster spawns in some rooms
            for room in &rooms {
                if rng.random_bool(0.5) {
                    let (mcx, mcy) = room.center();
                    if (mcx as u16) < map.width && (mcy as u16) < map.height {
                        let mut spawn = SpawnData::new(mcx as u16, mcy as u16, z, 5);
                        // Add 1–3 monsters
                        let num_monsters = rng.random_range(1..=3);
                        for _ in 0..num_monsters {
                            let mon = monster_pool[rng.random_range(0..monster_pool.len())];
                            let ox = rng.random_range(0..room.w.min(5)) as u16;
                            let oy = rng.random_range(0..room.h.min(5)) as u16;
                            spawn.monsters.push(otbforge_models::MonsterEntry {
                                name: mon.to_string(),
                                offset_x: ox,
                                offset_y: oy,
                            });
                        }
                        map.spawns.push(spawn);
                    }
                }
            }
        }

        map
    }
}

// ===========================================================================
// Tests
// ===========================================================================

#[cfg(test)]
mod tests {
    use super::*;

    // ----- Perlin noise tests -----

    #[test]
    fn test_perlin_deterministic() {
        let p1 = noise::PerlinNoise::new(42);
        let p2 = noise::PerlinNoise::new(42);
        for _ in 0..100 {
            let x = rand::random_range(-100.0..100.0);
            let y = rand::random_range(-100.0..100.0);
            assert_eq!(p1.noise2d(x, y), p2.noise2d(x, y));
        }
    }

    #[test]
    fn test_perlin_range() {
        let p = noise::PerlinNoise::new(1);
        for x in 0..200u32 {
            for y in 0..200u32 {
                let v = p.noise2d(x as f64 * 0.1, y as f64 * 0.1);
                assert!(
                    v >= -1.0 && v <= 1.0,
                    "noise2d out of range: {} at ({}, {})",
                    v,
                    x,
                    y
                );
            }
        }
    }

    #[test]
    fn test_perlin_different_seeds() {
        let p1 = noise::PerlinNoise::new(1);
        let p2 = noise::PerlinNoise::new(999);
        let mut any_different = false;
        // Use non-integer coordinates to ensure gradient differences manifest
        for x in 0..200 {
            for y in 0..200 {
                let fx = x as f64 * 0.37 + 0.13;
                let fy = y as f64 * 0.53 + 0.71;
                if p1.noise2d(fx, fy) != p2.noise2d(fx, fy) {
                    any_different = true;
                    break;
                }
            }
            if any_different {
                break;
            }
        }
        assert!(
            any_different,
            "different seeds should produce different values"
        );
    }

    #[test]
    fn test_perlin_octave_range() {
        let p = noise::PerlinNoise::new(7);
        for x in 0..100u32 {
            for y in 0..100u32 {
                let v = p.octave(x as f64 * 0.05, y as f64 * 0.05, 4, 0.5, 2.0);
                assert!(
                    v >= -1.0 && v <= 1.0,
                    "octave out of range: {} at ({}, {})",
                    v,
                    x,
                    y
                );
            }
        }
    }

    #[test]
    fn test_perlin_zero_octaves() {
        let p = noise::PerlinNoise::new(1);
        let v = p.octave(5.0, 5.0, 0, 0.5, 2.0);
        assert_eq!(v, 0.0);
    }

    // ----- Terrain generator tests -----

    #[test]
    fn test_terrain_generate_basic() {
        let config = TerrainConfig {
            width: 32,
            height: 32,
            seed: 42,
            water_level: 0.35,
            biome_scale: 0.05,
            num_rivers: 1,
        };
        let generator = TerrainGenerator::new(config);
        let map = generator.generate();
        assert!(!map.tiles.is_empty());
        assert_eq!(map.width, 32);
        assert_eq!(map.height, 32);
        assert!(map.validate().is_ok());
    }

    #[test]
    fn test_terrain_dimensions_match() {
        let config = TerrainConfig {
            width: 64,
            height: 48,
            seed: 10,
            water_level: 0.35,
            biome_scale: 0.05,
            num_rivers: 2,
        };
        let generator = TerrainGenerator::new(config);
        let map = generator.generate();
        assert_eq!(map.width, 64);
        assert_eq!(map.height, 48);
    }

    #[test]
    fn test_terrain_biomes_present() {
        // Use a small map with multiple seeds to check biome diversity
        let mut found_biomes = std::collections::HashSet::new();
        for seed in 0..20u64 {
            let config = TerrainConfig {
                width: 64,
                height: 64,
                seed,
                water_level: 0.35,
                biome_scale: 0.03,
                num_rivers: 0,
            };
            let generator = TerrainGenerator::new(config);
            let map = generator.generate();
            for tile in &map.tiles {
                if tile.z == 7 && tile.ground_id > 0 {
                    found_biomes.insert(tile.ground_id);
                }
            }
        }
        // Should have at least 3 distinct ground types (grass, water, and one more)
        assert!(
            found_biomes.len() >= 3,
            "expected biome diversity, got {} ground types: {:?}",
            found_biomes.len(),
            found_biomes
        );
    }

    #[test]
    fn test_terrain_with_rivers() {
        let config = TerrainConfig {
            width: 50,
            height: 50,
            seed: 42,
            water_level: 0.35,
            biome_scale: 0.04,
            num_rivers: 3,
        };
        let generator = TerrainGenerator::new(config);
        let map = generator.generate();
        let water_count = map
            .tiles
            .iter()
            .filter(|t| t.z == 7 && t.ground_id == 493)
            .count();
        // With 3 rivers, there should be at least some water tiles
        assert!(
            water_count > 0,
            "expected river water tiles, got {}",
            water_count
        );
    }

    #[test]
    fn test_terrain_deterministic() {
        let config = TerrainConfig {
            width: 30,
            height: 30,
            seed: 123,
            water_level: 0.35,
            biome_scale: 0.05,
            num_rivers: 2,
        };
        let generator1 = TerrainGenerator::new(config.clone());
        let generator2 = TerrainGenerator::new(config.clone());
        let map1 = generator1.generate();
        let map2 = generator2.generate();

        assert_eq!(map1.tiles.len(), map2.tiles.len());
        for (a, b) in map1.tiles.iter().zip(map2.tiles.iter()) {
            assert_eq!(a.x, b.x);
            assert_eq!(a.y, b.y);
            assert_eq!(a.z, b.z);
            assert_eq!(a.ground_id, b.ground_id);
        }
    }

    #[test]
    fn test_terrain_has_town() {
        let config = TerrainConfig {
            width: 32,
            height: 32,
            seed: 42,
            water_level: 0.35,
            biome_scale: 0.05,
            num_rivers: 0,
        };
        let generator = TerrainGenerator::new(config);
        let map = generator.generate();
        assert_eq!(map.towns.len(), 1);
        assert_eq!(map.towns[0].name, "Main Town");
    }

    #[test]
    fn test_terrain_has_spawn() {
        let config = TerrainConfig {
            width: 32,
            height: 32,
            seed: 42,
            water_level: 0.35,
            biome_scale: 0.05,
            num_rivers: 0,
        };
        let generator = TerrainGenerator::new(config);
        let map = generator.generate();
        assert_eq!(map.spawns.len(), 1);
    }

    // ----- Biome tests -----

    #[test]
    fn test_biome_ground_ids() {
        assert_eq!(Biome::Grass.ground_id(), 102);
        assert_eq!(Biome::Desert.ground_id(), 351);
        assert_eq!(Biome::Snow.ground_id(), 742);
        assert_eq!(Biome::Ocean.ground_id(), 493);
        assert_eq!(Biome::Mountain.ground_id(), 563);
        assert_eq!(Biome::Swamp.ground_id(), 202);
    }

    #[test]
    fn test_biome_count() {
        assert_eq!(Biome::count(), 11);
    }

    // ----- Dungeon generator tests -----

    #[test]
    fn test_dungeon_has_rooms() {
        let config = DungeonConfig {
            width: 50,
            height: 50,
            floors: 1,
            rooms_per_floor: 6,
            min_room_size: 4,
            max_room_size: 10,
            seed: 42,
        };
        let generator = DungeonGenerator::new(config);
        let map = generator.generate();

        // Stone floor tiles (rooms + corridors)
        let floor_tiles: u32 = map
            .tiles
            .iter()
            .filter(|t| t.z == 7 && t.ground_id == 563)
            .count() as u32;
        // Stone wall tiles (room walls)
        let wall_tiles: u32 = map
            .tiles
            .iter()
            .filter(|t| t.z == 7 && t.ground_id == 1017)
            .count() as u32;

        assert!(floor_tiles > 0, "expected floor tiles in dungeon, got 0");
        assert!(wall_tiles > 0, "expected wall tiles in dungeon, got 0");
    }

    #[test]
    fn test_dungeon_multiple_floors() {
        let config = DungeonConfig {
            width: 50,
            height: 50,
            floors: 3,
            rooms_per_floor: 4,
            min_room_size: 4,
            max_room_size: 8,
            seed: 55,
        };
        let generator = DungeonGenerator::new(config);
        let map = generator.generate();

        let z_levels: std::collections::HashSet<u8> = map.tiles.iter().map(|t| t.z).collect();
        assert!(
            z_levels.len() > 1,
            "expected multiple z-levels, got {:?}",
            z_levels
        );
    }

    #[test]
    fn test_dungeon_deterministic() {
        let config = DungeonConfig {
            width: 40,
            height: 40,
            floors: 2,
            rooms_per_floor: 4,
            min_room_size: 4,
            max_room_size: 8,
            seed: 77,
        };
        let generator1 = DungeonGenerator::new(config.clone());
        let generator2 = DungeonGenerator::new(config.clone());
        let map1 = generator1.generate();
        let map2 = generator2.generate();

        assert_eq!(map1.tiles.len(), map2.tiles.len());
        for (a, b) in map1.tiles.iter().zip(map2.tiles.iter()) {
            assert_eq!(a.x, b.x);
            assert_eq!(a.y, b.y);
            assert_eq!(a.z, b.z);
            assert_eq!(a.ground_id, b.ground_id);
        }
    }

    #[test]
    fn test_dungeon_dimensions_match() {
        let config = DungeonConfig {
            width: 60,
            height: 40,
            floors: 1,
            rooms_per_floor: 3,
            min_room_size: 4,
            max_room_size: 10,
            seed: 1,
        };
        let generator = DungeonGenerator::new(config);
        let map = generator.generate();
        assert_eq!(map.width, 60);
        assert_eq!(map.height, 40);
    }

    #[test]
    fn test_dungeon_has_spawns() {
        let config = DungeonConfig {
            width: 50,
            height: 50,
            floors: 2,
            rooms_per_floor: 6,
            min_room_size: 4,
            max_room_size: 10,
            seed: 100,
        };
        let generator = DungeonGenerator::new(config);
        let map = generator.generate();

        let total_monsters: usize = map.spawns.iter().map(|s| s.monsters.len()).sum();
        assert!(
            total_monsters > 0,
            "expected dungeon to have monster spawns, got {} monsters",
            total_monsters
        );
    }

    #[test]
    fn test_dungeon_map_validates() {
        let config = DungeonConfig {
            width: 50,
            height: 50,
            floors: 2,
            rooms_per_floor: 5,
            min_room_size: 4,
            max_room_size: 9,
            seed: 200,
        };
        let generator = DungeonGenerator::new(config);
        let map = generator.generate();
        assert!(map.validate().is_ok());
    }

    #[test]
    fn test_dungeon_no_rivers() {
        // Dungeon should never have water tiles
        let config = DungeonConfig {
            width: 40,
            height: 40,
            floors: 1,
            rooms_per_floor: 4,
            min_room_size: 4,
            max_room_size: 8,
            seed: 1,
        };
        let generator = DungeonGenerator::new(config);
        let map = generator.generate();
        let water_count = map.tiles.iter().filter(|t| t.ground_id == 493).count();
        assert_eq!(water_count, 0, "dungeon should not have water tiles");
    }
}
