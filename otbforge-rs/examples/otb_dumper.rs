use std::fs;
use std::path::Path;

fn main() {
    // Quick OTB item dumper
    let args: Vec<String> = std::env::args().collect();
    if args.len() < 2 {
        eprintln!("Usage: otb_dumper <items.otb>");
        std::process::exit(1);
    }
    
    let data = fs::read(&args[1]).unwrap_or_else(|e| {
        eprintln!("Error reading {}: {}", args[1], e);
        std::process::exit(1);
    });
    
    if data.len() < 4 {
        eprintln!("File too small");
        std::process::exit(1);
    }
    
    println!("OTB file: {} ({} bytes)", args[1], data.len());
    println!("Signature: {:08X}", u32::from_le_bytes([data[0], data[1], data[2], data[3]]));
    
    // Simple scan for item patterns
    // OTB items are stored as child nodes of root
    // Look for common ground item patterns
    
    // Count ground items (type=1) and their IDs
    let mut ground_count = 0;
    let mut total_nodes = 0;
    
    // Simple byte scan
    let mut i = 4; // skip signature
    while i < data.len() {
        if data[i] == 0xFE {
            total_nodes += 1;
            // Check if this could be an item node
            // Items typically start after root node's version data
            i += 1;
        } else if data[i] == 0xFF {
            i += 1;
        } else if data[i] == 0xFD && i + 1 < data.len() {
            i += 2;
        } else {
            i += 1;
        }
    }
    
    println!("Total nodes (0xFE): {total_nodes}");
    println!("File ends at offset {}", data.len());
    
    // Find string data - item names
    let mut name_offsets = Vec::new();
    let search_terms = ["grass", "dirt", "sand", "snow", "stone", "water", "lava", "wall", "tree", "bush", "rock", "road", "floor", "ground"];
    for term in &search_terms {
        let term_bytes = term.as_bytes();
        let mut pos = 0;
        while pos < data.len() {
            if let Some(idx) = data[pos..].windows(term_bytes.len()).position(|w| w == term_bytes) {
                let abs_idx = pos + idx;
                // Get surrounding context
                let start = abs_idx.saturating_sub(10);
                let end = (abs_idx + term_bytes.len() + 20).min(data.len());
                let context: Vec<u8> = data[start..end].iter().map(|&b| if b >= 0x20 && b < 0x7f { b } else { b'.' }).collect();
                name_offsets.push((term.to_string(), abs_idx, String::from_utf8_lossy(&context).to_string()));
                pos = abs_idx + 1;
                if name_offsets.len() > 50 {
                    break;
                }
            } else {
                break;
            }
        }
    }
    
    println!("\n=== Item name strings found ===");
    for (term, offset, ctx) in &name_offsets {
        println!("[{}] offset {}: {}", term, offset, ctx);
    }
}
