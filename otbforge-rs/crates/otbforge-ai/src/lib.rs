/*!
OTBForge AI — AI-powered map generation via LLM blueprint system.

This crate provides:
- `Blueprint` types that describe a map layout in a JSON-friendly format
- `AiClient` for calling an OpenAI-compatible LLM API to generate blueprints
- `execute_blueprint()` to convert a blueprint into a `MapData` ready for OTBM export
*/

use std::collections::HashMap;

use anyhow::{anyhow, Context, Result};
use rand::Rng;
use serde::{Deserialize, Serialize};

use otbforge_models::{ItemData, MapData, Position};

// ---------------------------------------------------------------------------
// Compact item catalog (inline — avoids bloating the LLM prompt)
// ---------------------------------------------------------------------------

const ITEM_CATALOG: &str = "\
GROUND: grass=106 sand=104 dirt=103 dark_dirt=351 swamp=354 snow=670 stone_floor=431 wood_floor=405 marble_floor=406\n\
WALLS: stone_wall=371 dirt_wall=356 brick_wall=1025 bamboo_wall=388 sandstone_wall=464 white_stone_wall=1111 ornamented_wall=1128\n\
WATER: water=493 deep_water=491\n\
DOORS: wooden_door=512 stone_door=513 bamboo_door=389\n\
TREES: tree=3599 cherry_blossom=2670 palm_tree=3642 bamboo=3675\n\
NARUTO: bamboo_fence=390 bamboo_roof=391 lantern=1764 konoha_banner=3605 torii_gate=3606 pagoda=3607\n\
FURNITURE: table=1623 chair=1628 bed=1754\n\
CONTAINERS: chest=1747 barrel=1744\n\
NATURE: flower=2982 rock=1304 mushroom=3457";

// ---------------------------------------------------------------------------
// Blueprint types (what the LLM generates)
// ---------------------------------------------------------------------------

/// Top-level blueprint describing a map layout.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Blueprint {
    pub description: String,
    pub zones: Vec<Zone>,
    pub structures: Vec<Structure>,
    pub roads: Vec<Road>,
    pub decorations: Vec<Decoration>,
    pub spawns: Vec<SpawnPoint>,
}

/// A rectangular area filled with a ground tile type.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Zone {
    pub name: String,
    pub x: u16,
    pub y: u16,
    pub width: u16,
    pub height: u16,
    pub ground_id: u16,
    pub border_wall_id: Option<u16>,
}

/// A building or structure placed on the map.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Structure {
    pub name: String,
    pub structure_type: String,
    pub x: u16,
    pub y: u16,
    pub width: u16,
    pub height: u16,
    pub wall_id: u16,
    pub floor_id: u16,
    pub door_id: Option<u16>,
    pub roof_id: Option<u16>,
    pub interior_items: Vec<InteriorItem>,
}

/// An item placed inside a structure at a relative offset.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct InteriorItem {
    pub id: u16,
    pub x: u16,
    pub y: u16,
    pub name: String,
}

/// A road defined by waypoints.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Road {
    pub ground_id: u16,
    pub width: u16,
    pub path: Vec<[u16; 2]>,
}

/// Decoration items scattered within a zone.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Decoration {
    pub id: u16,
    pub count: u16,
    pub zone: String,
    pub name: String,
}

/// A monster spawn point.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SpawnPoint {
    pub name: String,
    pub x: u16,
    pub y: u16,
    pub monster: String,
    pub count: u16,
}

// ---------------------------------------------------------------------------
// AI Client
// ---------------------------------------------------------------------------

/// Configuration for AI map generation.
pub struct AiGenerateConfig {
    pub prompt: String,
    pub width: u32,
    pub height: u32,
    pub seed: u64,
}

/// Client for calling an OpenAI-compatible LLM API.
pub struct AiClient {
    api_url: String,
    api_key: String,
    model: String,
}

#[derive(Serialize)]
struct ChatMessage {
    role: String,
    content: String,
}

#[derive(Serialize)]
struct ChatRequest {
    model: String,
    messages: Vec<ChatMessage>,
    max_tokens: u32,
    temperature: f32,
}

#[derive(Deserialize)]
struct ChatResponse {
    choices: Vec<ChatChoice>,
}

#[derive(Deserialize)]
struct ChatChoice {
    message: ChatResponseMessage,
}

#[derive(Deserialize)]
struct ChatResponseMessage {
    content: String,
    #[serde(default)]
    reasoning_content: Option<String>,
}

impl AiClient {
    /// Create a new AI client.
    pub fn new(api_url: &str, api_key: &str, model: &str) -> Self {
        Self {
            api_url: api_url.trim_end_matches('/').to_string(),
            api_key: api_key.to_string(),
            model: model.to_string(),
        }
    }

    /// Generate a blueprint from a natural language prompt.
    pub fn generate_blueprint(&self, config: &AiGenerateConfig) -> Result<Blueprint> {
        let system_prompt = build_system_prompt(config.width, config.height);
        let user_prompt = format!(
            "Create a map blueprint for the following request:\n\n{}\n\nMap size: {}x{}, seed: {}",
            config.prompt, config.width, config.height, config.seed
        );

        let request = ChatRequest {
            model: self.model.clone(),
            messages: vec![
                ChatMessage {
                    role: "system".to_string(),
                    content: system_prompt,
                },
                ChatMessage {
                    role: "user".to_string(),
                    content: user_prompt,
                },
            ],
            max_tokens: 8192,
            temperature: 0.7,
        };

        let url = format!("{}/chat/completions", self.api_url);
        eprintln!("  API URL: {}", url);
        let client = reqwest::blocking::Client::builder()
            .danger_accept_invalid_certs(true)
            .timeout(std::time::Duration::from_secs(120))
            .build()
            .map_err(|e| anyhow!("Failed to build HTTP client: {}", e))?;
        let response = client
            .post(&url)
            .header("Authorization", format!("Bearer {}", self.api_key))
            .header("Content-Type", "application/json")
            .json(&request)
            .send()
            .map_err(|e| {
                anyhow!(
                    "Failed to send request to AI API (url={}, error={})",
                    url, e
                )
            })?;

        if !response.status().is_success() {
            let status = response.status();
            let body = response.text().unwrap_or_default();
            return Err(anyhow!("AI API returned status {}: {}", status, body));
        }

        let chat_response: ChatResponse = response
            .json()
            .context("Failed to parse AI API response as JSON")?;

        let choice = chat_response
            .choices
            .first()
            .ok_or_else(|| anyhow!("AI API returned no choices"))?;

        // GLM models may use reasoning_content instead of content
        let content = if choice.message.content.trim().is_empty() {
            choice
                .message
                .reasoning_content
                .as_deref()
                .unwrap_or("")
                .trim()
                .to_string()
            // For reasoning models, the actual JSON output may be at the end of reasoning
        } else {
            choice.message.content.trim().to_string()
        };

        if content.is_empty() {
            return Err(anyhow!("AI API returned empty content (finish_reason may indicate truncation)"));
        }

        eprintln!("  Response length: {} chars", content.len());

        // Strip markdown code fences if present
        let json_str = strip_code_fences(&content);

        serde_json::from_str::<Blueprint>(json_str)
            .map_err(|e| anyhow!("Failed to parse blueprint JSON from LLM: {}\nRaw content:\n{}", e, content))
    }
}

/// Strip ```json ... ``` or ``` ... ``` code fences from LLM output.
fn strip_code_fences(s: &str) -> &str {
    let trimmed = s.trim();
    if let Some(rest) = trimmed.strip_prefix("```json") {
        rest.trim_end_matches('`').trim()
    } else if let Some(rest) = trimmed.strip_prefix("```") {
        rest.trim_end_matches('`').trim()
    } else {
        trimmed
    }
}

fn build_system_prompt(width: u32, height: u32) -> String {
    format!(
        r#"You are an expert OTBM map designer for a Naruto-themed OT server (World of Shinobi Brasil).
The user will describe a map they want. You must create a JSON blueprint.

AVAILABLE ITEMS (WoSBR item catalog):
{catalog}

MAP SIZE: {width}x{height}

RULES:
1. All coordinates must be within 0-{w} for x and 0-{h} for y.
2. Use real item IDs from the catalog above. Ground zones MUST use ground IDs, walls MUST use wall IDs, etc.
3. Design realistic layouts: roads connect buildings, zones don't overlap excessively.
4. Include appropriate decorations for each biome (trees in forest zones, cactus in desert, etc.).
5. Place spawns where monsters should appear (each spawn gets a name, position, monster type, and count).
6. Structures should have walls around the perimeter, floor_id for interior, and optionally a door_id on one wall tile.
7. Roads are defined by a list of waypoints — each waypoint is [x, y]. The road draws tiles between consecutive waypoints at the given width.
8. Decorations are scattered randomly within the named zone.

RESPOND ONLY WITH VALID JSON matching this schema. No markdown, no explanation, no extra text.

JSON SCHEMA:
{{
  "description": "string — human-readable map description",
  "zones": [
    {{
      "name": "string — unique zone name (e.g. 'village_center', 'forest', 'desert')",
      "x": number, "y": number,
      "width": number, "height": number,
      "ground_id": number,
      "border_wall_id": null or number
    }}
  ],
  "structures": [
    {{
      "name": "string",
      "structure_type": "building|tower|shrine|bridge|other",
      "x": number, "y": number,
      "width": number, "height": number,
      "wall_id": number,
      "floor_id": number,
      "door_id": null or number,
      "roof_id": null or number,
      "interior_items": [
        {{"id": number, "x": number, "y": number, "name": "string"}}
      ]
    }}
  ],
  "roads": [
    {{
      "ground_id": number,
      "width": number,
      "path": [[x, y], [x, y], ...]
    }}
  ],
  "decorations": [
    {{"id": number, "count": number, "zone": "zone_name", "name": "string"}}
  ],
  "spawns": [
    {{"name": "string", "x": number, "y": number, "monster": "string", "count": number}}
  ]
}}"#,
        catalog = ITEM_CATALOG,
        width = width,
        height = height,
        w = width - 1,
        h = height - 1,
    )
}

// ---------------------------------------------------------------------------
// Blueprint Executor
// ---------------------------------------------------------------------------

/// Execute a blueprint to produce a MapData.
pub fn execute_blueprint(blueprint: &Blueprint, width: u16, height: u16) -> MapData {
    let mut map = MapData::with_dimensions(width, height);
    map.description = blueprint.description.clone();

    // Build a lookup of zone names → bounds for decoration scattering
    let mut zone_bounds: HashMap<String, Zone> = HashMap::new();
    for zone in &blueprint.zones {
        zone_bounds.insert(zone.name.clone(), zone.clone());
    }

    // Default ground: fill the entire map with grass if no zones cover it
    let default_ground: u16 = 106; // grass

    // 1. Fill zones with ground tiles
    for zone in &blueprint.zones {
        fill_rectangle(&mut map, zone.x, zone.y, zone.width, zone.height, zone.ground_id);
    }

    // Fill remaining area with default grass
    fill_gaps(&mut map, 0, 0, width, height, default_ground);

    // 2. Build border walls around zones
    for zone in &blueprint.zones {
        if let Some(wall_id) = zone.border_wall_id {
            draw_rect_border(&mut map, zone.x, zone.y, zone.width, zone.height, wall_id);
        }
    }

    // 3. Place structures
    for structure in &blueprint.structures {
        place_structure(&mut map, structure);
    }

    // 4. Draw roads
    for road in &blueprint.roads {
        draw_road(&mut map, road);
    }

    // 5. Scatter decorations
    let mut rng = rand::rng();
    for deco in &blueprint.decorations {
        if let Some(zone) = zone_bounds.get(&deco.zone) {
            scatter_in_zone(&mut map, zone, deco.id, deco.count, &mut rng);
        }
    }

    // 6. Add spawns
    for spawn in &blueprint.spawns {
        let spawn_data = map.add_spawn(spawn.x, spawn.y, 7, 10);
        for _ in 0..spawn.count {
            spawn_data.monsters.push(otbforge_models::MonsterEntry {
                name: spawn.monster.clone(),
                offset_x: 0,
                offset_y: 0,
            });
        }
    }

    // 7. Add a default town
    let center_x = width / 2;
    let center_y = height / 2;
    map.add_town(
        1,
        "Main Village",
        Position::new(center_x, center_y, 7),
    );

    map
}

fn fill_rectangle(map: &mut MapData, x: u16, y: u16, w: u16, h: u16, ground_id: u16) {
    for dy in 0..h {
        for dx in 0..w {
            let tx = x.saturating_add(dx);
            let ty = y.saturating_add(dy);
            if tx < map.width && ty < map.height {
                map.add_tile(tx, ty, 7, ground_id);
            }
        }
    }
}

fn fill_gaps(map: &mut MapData, x0: u16, y0: u16, w: u16, h: u16, ground_id: u16) {
    for y in y0..h {
        for x in x0..w {
            // Check if this tile already exists
            let exists = map.tiles.iter().any(|t| t.x == x && t.y == y && t.z == 7);
            if !exists {
                map.add_tile(x, y, 7, ground_id);
            }
        }
    }
}

fn draw_rect_border(map: &mut MapData, x: u16, y: u16, w: u16, h: u16, wall_id: u16) {
    // Top and bottom rows
    for dx in 0..w {
        let tx = x.saturating_add(dx);
        if tx < map.width {
            // Top
            if y < map.height {
                map.add_item(tx, y, 7, ItemData::new(wall_id));
            }
            // Bottom
            let by = y.saturating_add(h.saturating_sub(1));
            if by < map.height {
                map.add_item(tx, by, 7, ItemData::new(wall_id));
            }
        }
    }
    // Left and right columns
    for dy in 0..h {
        let ty = y.saturating_add(dy);
        if ty < map.height {
            // Left
            if x < map.width {
                map.add_item(x, ty, 7, ItemData::new(wall_id));
            }
            // Right
            let rx = x.saturating_add(w.saturating_sub(1));
            if rx < map.width {
                map.add_item(rx, ty, 7, ItemData::new(wall_id));
            }
        }
    }
}

fn place_structure(map: &mut MapData, structure: &Structure) {
    let x = structure.x;
    let y = structure.y;
    let w = structure.width;
    let h = structure.height;

    // Fill interior with floor
    for dy in 0..h {
        for dx in 0..w {
            let tx = x.saturating_add(dx);
            let ty = y.saturating_add(dy);
            if tx < map.width && ty < map.height {
                map.add_tile(tx, ty, 7, structure.floor_id);
            }
        }
    }

    // Draw walls around perimeter
    draw_rect_border(map, x, y, w, h, structure.wall_id);

    // Place door on the middle of the bottom wall
    if let Some(door_id) = structure.door_id {
        let door_x = x.saturating_add(w / 2);
        let door_y = y.saturating_add(h.saturating_sub(1));
        if door_x < map.width && door_y < map.height {
            // Replace wall with door
            let tile = map.tiles.iter_mut().find(|t| t.x == door_x && t.y == door_y && t.z == 7);
            if let Some(tile) = tile {
                // Remove the wall item and replace with door
                tile.items.retain(|i| i.id != structure.wall_id);
                tile.items.push(ItemData::new(door_id));
            } else {
                map.add_item(door_x, door_y, 7, ItemData::new(door_id));
            }
        }
    }

    // Place interior items
    for item in &structure.interior_items {
        let ix = x.saturating_add(item.x);
        let iy = y.saturating_add(item.y);
        if ix < map.width && iy < map.height {
            map.add_item(ix, iy, 7, ItemData::new(item.id));
        }
    }
}

fn draw_road(map: &mut MapData, road: &Road) {
    if road.path.len() < 2 {
        return;
    }

    let half_w = (road.width as i32) / 2;

    for i in 0..road.path.len() - 1 {
        let (x0, y0) = (road.path[i][0] as i32, road.path[i][1] as i32);
        let (x1, y1) = (road.path[i + 1][0] as i32, road.path[i + 1][1] as i32);

        let steps = ((x1 - x0).abs() + (y1 - y0).abs()).max(1) as usize;
        for step in 0..=steps {
            let t = step as f64 / steps as f64;
            let cx = (x0 as f64 + (x1 - x0) as f64 * t).round() as i32;
            let cy = (y0 as f64 + (y1 - y0) as f64 * t).round() as i32;

            for offset in -half_w..=half_w {
                // Draw along both axes for width
                let tx1 = (cx + offset) as u16;
                let ty1 = cy as u16;
                if tx1 < map.width && ty1 < map.height {
                    map.add_tile(tx1, ty1, 7, road.ground_id);
                }

                if offset != 0 {
                    let tx2 = cx as u16;
                    let ty2 = (cy + offset) as u16;
                    if tx2 < map.width && ty2 < map.height {
                        map.add_tile(tx2, ty2, 7, road.ground_id);
                    }
                }
            }
        }
    }
}

fn scatter_in_zone(
    map: &mut MapData,
    zone: &Zone,
    item_id: u16,
    count: u16,
    rng: &mut impl Rng,
) {
    if count == 0 || zone.width == 0 || zone.height == 0 {
        return;
    }

    for _ in 0..count {
        let dx = rng.random_range(0..zone.width);
        let dy = rng.random_range(0..zone.height);
        let tx = zone.x.saturating_add(dx);
        let ty = zone.y.saturating_add(dy);
        if tx < map.width && ty < map.height {
            map.add_item(tx, ty, 7, ItemData::new(item_id));
        }
    }
}

// ---------------------------------------------------------------------------
// Public convenience: generate + execute in one step
// ---------------------------------------------------------------------------

/// Generate a blueprint via AI and execute it into a MapData.
pub fn generate_map(client: &AiClient, config: &AiGenerateConfig) -> Result<MapData> {
    let blueprint = client.generate_blueprint(config)?;
    println!("  Blueprint: {}", blueprint.description);
    println!("  Zones: {}, Structures: {}, Roads: {}, Decorations: {}, Spawns: {}",
        blueprint.zones.len(),
        blueprint.structures.len(),
        blueprint.roads.len(),
        blueprint.decorations.len(),
        blueprint.spawns.len(),
    );
    let map = execute_blueprint(&blueprint, config.width as u16, config.height as u16);
    Ok(map)
}
