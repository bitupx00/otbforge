use clap::{Parser, Subcommand};
use std::path::PathBuf;

/// OTBForge — OpenTibia AI Forge
///
/// Rust-powered OTBM map generation, validation, and manipulation toolkit.
#[derive(Parser)]
#[command(name = "otbforge", version, about)]
struct Cli {
    #[command(subcommand)]
    command: Commands,
}

#[derive(Subcommand)]
enum Commands {
    /// Generate a new OTBM map procedurally
    Generate {
        /// Biome type: grass, forest, desert, snow, swamp, dungeon, mixed
        #[arg(default_value = "grass")]
        biome: String,

        /// Map width in tiles
        #[arg(short, long, default_value_t = 256)]
        width: u32,

        /// Map height in tiles
        #[arg(short = 'H', long, default_value_t = 256)]
        height: u32,

        /// Random seed (0 = random)
        #[arg(short, long, default_value_t = 0)]
        seed: u64,

        /// Output .otbm file path
        #[arg(short, long, default_value = "output.otbm")]
        output: PathBuf,
    },
    /// Validate an OTBM map file
    Validate {
        /// Input .otbm file
        input: PathBuf,
    },
    /// Convert between OTBM and JSON
    Convert {
        /// Input file (.otbm or .json)
        input: PathBuf,

        /// Output file
        #[arg(short, long)]
        output: PathBuf,
    },
    /// Show information about an OTBM map
    Info {
        /// Input .otbm file
        input: PathBuf,
    },
    /// Compare two OTBM maps
    Diff {
        /// First map
        map_a: PathBuf,
        /// Second map
        map_b: PathBuf,
    },
    /// Extract a region from a map
    Extract {
        /// Input .otbm file
        input: PathBuf,
        /// X1 coordinate
        #[arg(long)]
        x1: u16,
        /// Y1 coordinate
        #[arg(long)]
        y1: u16,
        /// X2 coordinate
        #[arg(long)]
        x2: u16,
        /// Y2 coordinate
        #[arg(long)]
        y2: u16,
        /// Z1 (floor)
        #[arg(long, default_value_t = 0)]
        z1: u8,
        /// Z2 (floor)
        #[arg(long, default_value_t = 15)]
        z2: u8,
        /// Output file
        #[arg(short, long, default_value = "region.otbm")]
        output: PathBuf,
    },
    /// Stitch multiple maps together
    Stitch {
        /// Input .otbm files (2-16 maps)
        inputs: Vec<PathBuf>,
        /// Layout: horizontal, vertical, grid
        #[arg(short, long, default_value = "auto")]
        layout: String,
        /// Output file
        #[arg(short, long, default_value = "stitched.otbm")]
        output: PathBuf,
    },
    /// Generate a dungeon map
    Dungeon {
        /// Map width
        #[arg(short, long, default_value_t = 128)]
        width: u32,
        /// Map height
        #[arg(short = 'H', long, default_value_t = 128)]
        height: u32,
        /// Random seed
        #[arg(short, long, default_value_t = 0)]
        seed: u64,
        /// Output file
        #[arg(short, long, default_value = "dungeon.otbm")]
        output: PathBuf,
    },
}

fn main() {
    let cli = Cli::parse();

    match cli.command {
        Commands::Generate { biome, width, height, seed, output } => {
            println!("otbforge generate: biome={} {}x{} seed={}", biome, width, height, seed);
            println!("→ Generating map...");
            let effective_seed = if seed == 0 { 42 } else { seed };
            let map = if biome.eq_ignore_ascii_case("mixed") {
                // Mixed: use the full TerrainGenerator with biomes, ocean, rivers, etc.
                let config = otbforge_gen::TerrainConfig {
                    width,
                    height,
                    seed: effective_seed,
                    ..Default::default()
                };
                let terrain_gen = otbforge_gen::TerrainGenerator::new(config);
                terrain_gen.generate()
            } else {
                // Specific biome: fill entire map with that biome (no ocean)
                otbforge_gen::generate_biome_map(&biome, width, height, effective_seed)
            };
            let tiles = map.tiles.len();
            let bytes = otbforge_otbm::write_otbm(&map);
            std::fs::write(&output, &bytes).unwrap_or_else(|e| {
                eprintln!("Error writing {}: {}", output.display(), e);
                std::process::exit(1);
            });
            println!("✓ Written {} tiles ({} bytes) to {}", tiles, bytes.len(), output.display());
        }
        Commands::Validate { input } => {
            println!("otbforge validate: {}", input.display());
            let data = std::fs::read(&input).unwrap_or_else(|e| {
                eprintln!("Error reading {}: {}", input.display(), e);
                std::process::exit(1);
            });
            let map = otbforge_otbm::read_otbm(&data).unwrap_or_else(|e| {
                eprintln!("Parse error: {:?}", e);
                std::process::exit(1);
            });
            let issues = otbforge_core::MapValidator::validate(&map);
            if issues.is_empty() {
                println!("✓ Map is valid! ({} tiles)", map.tiles.len());
            } else {
                let errors = issues.iter().filter(|i| i.severity == otbforge_core::Severity::Error).count();
                let warnings = issues.iter().filter(|i| i.severity == otbforge_core::Severity::Warning).count();
                println!("Found {} errors, {} warnings:", errors, warnings);
                for issue in &issues {
                    let icon = match issue.severity {
                        otbforge_core::Severity::Error => "✗",
                        otbforge_core::Severity::Warning => "⚠",
                        otbforge_core::Severity::Info => "ℹ",
                    };
                    println!("  {} [{}] {}", icon, issue.category, issue.message);
                }
            }
        }
        Commands::Convert { input, output } => {
            println!("otbforge convert: {} → {}", input.display(), output.display());
            let data = std::fs::read(&input).unwrap_or_else(|e| {
                eprintln!("Error reading {}: {}", input.display(), e);
                std::process::exit(1);
            });
            let ext = input.extension().and_then(|e| e.to_str()).unwrap_or("");
            if ext == "otbm" {
                let map = otbforge_otbm::read_otbm(&data).unwrap_or_else(|e| {
                    eprintln!("Parse error: {:?}", e);
                    std::process::exit(1);
                });
                let json = serde_json::to_string_pretty(&map).unwrap();
                std::fs::write(&output, &json).unwrap_or_else(|e| {
                    eprintln!("Error writing {}: {}", output.display(), e);
                    std::process::exit(1);
                });
                println!("✓ Converted to JSON ({} bytes)", json.len());
            } else {
                println!("JSON → OTBM conversion coming soon");
            }
        }
        Commands::Info { input } => {
            println!("otbforge info: {}", input.display());
            let data = std::fs::read(&input).unwrap_or_else(|e| {
                eprintln!("Error reading {}: {}", input.display(), e);
                std::process::exit(1);
            });
            let map = otbforge_otbm::read_otbm(&data).unwrap_or_else(|e| {
                eprintln!("Parse error: {:?}", e);
                std::process::exit(1);
            });
            println!("  Description: {}", map.description);
            println!("  Size: {}x{}", map.width, map.height);
            println!("  OTBM Version: {}.{}", map.otb_major_version, map.otb_minor_version);
            println!("  Tiles: {}", map.tiles.len());
            println!("  Towns: {}", map.towns.len());
            println!("  Houses: {}", map.houses.len());
            println!("  Spawns: {}", map.spawns.len());
            println!("  NPC Spawns: {}", map.npc_spawns.len());
            println!("  Waypoints: {}", map.waypoints.len());
        }
        Commands::Diff { map_a, map_b } => {
            println!("otbforge diff: {} vs {}", map_a.display(), map_b.display());
            let da = std::fs::read(&map_a).unwrap_or_else(|e| {
                eprintln!("Error: {}", e); std::process::exit(1);
            });
            let db = std::fs::read(&map_b).unwrap_or_else(|e| {
                eprintln!("Error: {}", e); std::process::exit(1);
            });
            let a = otbforge_otbm::read_otbm(&da).unwrap_or_else(|e| {
                eprintln!("Parse A: {:?}", e); std::process::exit(1);
            });
            let b = otbforge_otbm::read_otbm(&db).unwrap_or_else(|e| {
                eprintln!("Parse B: {:?}", e); std::process::exit(1);
            });
            let diffs = otbforge_core::MapDiff::diff(&a, &b);
            if diffs.is_empty() {
                println!("✓ Maps are identical");
            } else {
                println!("Found {} differences:", diffs.len());
                for d in &diffs {
                    println!("  {}", d);
                }
            }
        }
        Commands::Extract { input, x1, y1, x2, y2, z1, z2, output } => {
            println!("otbforge extract: {} [{}-{},{}-{},{}-{}] → {}", 
                     input.display(), x1, x2, y1, y2, z1, z2, output.display());
            let data = std::fs::read(&input).unwrap_or_else(|e| {
                eprintln!("Error: {}", e); std::process::exit(1);
            });
            let map = otbforge_otbm::read_otbm(&data).unwrap_or_else(|e| {
                eprintln!("Parse: {:?}", e); std::process::exit(1);
            });
            let region = otbforge_core::RegionExtractor::extract_region(&map, x1, y1, z1, x2, y2, z2);
            let bytes = otbforge_otbm::write_otbm(&region);
            std::fs::write(&output, &bytes).unwrap_or_else(|e| {
                eprintln!("Error writing: {}", e); std::process::exit(1);
            });
            println!("✓ Extracted {} tiles → {}", region.tiles.len(), output.display());
        }
        Commands::Stitch { inputs, layout, output } => {
            if inputs.len() < 2 {
                eprintln!("Need at least 2 maps to stitch");
                std::process::exit(1);
            }
            println!("otbforge stitch: {} maps, layout={}", inputs.len(), layout);
            let maps: Vec<_> = inputs.iter().map(|p| {
                let data = std::fs::read(p).unwrap_or_else(|e| {
                    eprintln!("Error reading {}: {}", p.display(), e);
                    std::process::exit(1);
                });
                otbforge_otbm::read_otbm(&data).unwrap_or_else(|e| {
                    eprintln!("Parse error {}: {:?}", p.display(), e);
                    std::process::exit(1);
                })
            }).collect();
            let refs: Vec<_> = maps.iter().collect();
            let result = otbforge_core::Stitcher::new(0, 0).stitch(&refs);
            let bytes = otbforge_otbm::write_otbm(&result);
            std::fs::write(&output, &bytes).unwrap_or_else(|e| {
                eprintln!("Error writing: {}", e); std::process::exit(1);
            });
            println!("✓ Stitched {} tiles → {}", result.tiles.len(), output.display());
        }
        Commands::Dungeon { width, height, seed, output } => {
            println!("otbforge dungeon: {}x{} seed={}", width, height, seed);
            let config = otbforge_gen::DungeonConfig {
                width,
                height,
                seed: if seed == 0 { 42 } else { seed },
                ..Default::default()
            };
            let dungeon_gen = otbforge_gen::DungeonGenerator::new(config);
            let map = dungeon_gen.generate();
            let bytes = otbforge_otbm::write_otbm(&map);
            std::fs::write(&output, &bytes).unwrap_or_else(|e| {
                eprintln!("Error: {}", e); std::process::exit(1);
            });
            println!("✓ Dungeon {} tiles → {}", map.tiles.len(), output.display());
        }
    }
}
