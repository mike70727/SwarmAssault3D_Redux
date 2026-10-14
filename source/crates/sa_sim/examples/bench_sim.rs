//! Headless simulation benchmark: ms per tick for growing battles on the five-family map.
//! Run: cargo run --release -p sa_sim --example bench_sim
use std::path::PathBuf;
use std::time::Instant;

use sa_sim::*;

fn main() {
    let assets = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../assets");
    let sizes = [50u32, 200, 500, 1000, 2000];
    println!("units_per_team total_units ticks ms_per_tick sim_fps_equivalent shots kills");
    for &n in &sizes {
        let defs = Defs::load_dir(&assets.join("data")).expect("defs");
        let mut map = MapDef::load(&assets.join("data/maps/five_families.ron")).expect("map");
        map.rules.unit_cap = Some(n * 2 + 100);
        map.rules.flyers = false;
        map.rules.pirates = false;
        for t in map.teams.iter_mut() {
            t.controller = Controller::Bot;
            t.bot_profile = "hard".into();
        }
        map.units.clear();
        let kinds = ["ant_soldier", "ant_grenadier", "ant_bazooka"];
        let kinds2 = ["spider_black_widow", "spider_sniper", "spider_missile"];
        for i in 0..3 {
            map.units.push(UnitSpawn { unit: kinds[i].into(), team: 1, pos: Vec2::new(26.0 + i as f32 * 6.0, 70.0), count: n / 3 + 1, spread: (n as f32).sqrt() * 0.7 + 2.0 });
            map.units.push(UnitSpawn { unit: kinds2[i].into(), team: 2, pos: Vec2::new(70.0 - i as f32 * 6.0, 26.0), count: n / 3 + 1, spread: (n as f32).sqrt() * 0.7 + 2.0 });
        }
        let mut w = World::new(defs, map).expect("world");
        let total = w.living_units().count();
        // send everyone at the enemy so the whole map fights
        let a: Vec<UnitId> = w.living_units().filter(|u| u.team == 1).map(|u| u.id).collect();
        let b: Vec<UnitId> = w.living_units().filter(|u| u.team == 2).map(|u| u.id).collect();
        w.issue(&a, Order::AttackMove(Vec2::new(80.0, 16.0)));
        w.issue(&b, Order::AttackMove(Vec2::new(16.0, 80.0)));
        let ticks = 30 * 60;
        let t0 = Instant::now();
        for _ in 0..ticks {
            w.step();
            w.events.clear();
        }
        let ms = t0.elapsed().as_secs_f64() * 1000.0 / ticks as f64;
        println!("{n:>6} {total:>6} {ticks:>6} {ms:>9.3} {:>8.0} {:>6} {:>5}", 1000.0 / ms, w.stats.shots, w.stats.units_killed);
    }
}
