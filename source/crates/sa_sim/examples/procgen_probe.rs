//! Prints how the ground of procedural levels came about: cargo run -p sa_sim --example procgen_probe
use std::path::PathBuf;

use sa_sim::Defs;
use sa_sim::procgen::{GroundModel, generate_with_report};

fn main() {
    let crate_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    let assets = ["../../assets", "../../../assets"].iter().map(|r| crate_dir.join(r)).find(|p| p.join("data").is_dir()).expect("assets");
    let t0 = std::time::Instant::now();
    let model = GroundModel::from_dir(&assets.join("data/maps")).expect("levels");
    println!("learned in {:.2} s", t0.elapsed().as_secs_f32());
    let defs = Defs::load_dir(&assets.join("data")).expect("data");
    for level in [1u32, 5, 12, 30] {
        for seed in 0..6u64 {
            let t = std::time::Instant::now();
            let (map, r) = generate_with_report(&model, &defs, level, seed).expect("level");
            let cells = map.cells.as_deref().unwrap_or("");
            let n = cells.chars().filter(|c| !c.is_whitespace()).count().max(1) as f32;
            let share = |k: char| cells.chars().filter(|c| *c == k).count() as f32 / n * 100.0;
            println!(
                "level {level:3} seed {seed}: {:6} {:22} {:3}x{:3}  dead ends {:2}  cut off {:2}  plain {:5}  water {:4.1}% rock {:4.1}% scrub {:4.1}%  {:.0} ms",
                map.tileset, map.name, map.width, map.height, r.dead_ends, r.cut_off, r.plain, share('w'), share('r'), share('v'), t.elapsed().as_secs_f32() * 1000.0
            );
        }
    }
}
