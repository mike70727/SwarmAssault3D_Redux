//! Procedural levels (the endless mode unlocked by the campaign).

use std::collections::VecDeque;
use std::path::PathBuf;
use std::sync::OnceLock;

use sa_sim::procgen::{GroundModel, generate, plan};
use sa_sim::*;

fn assets() -> PathBuf {
    // the packaged game keeps `assets` beside `source`; a plain checkout has it inside
    let crate_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    ["../../assets", "../../../assets"].iter().map(|r| crate_dir.join(r)).find(|p| p.join("data").is_dir()).unwrap_or_else(|| crate_dir.join("../../assets"))
}

fn model() -> &'static GroundModel {
    static MODEL: OnceLock<GroundModel> = OnceLock::new();
    MODEL.get_or_init(|| GroundModel::from_dir(&assets().join("data/maps")).expect("levels"))
}

fn defs() -> Defs {
    Defs::load_dir(&assets().join("data")).expect("data files")
}

/// Cells reachable on foot from `from` (4-neighbour flood over the nav grid).
fn reachable(w: &World, from: Vec2) -> Vec<bool> {
    let (gw, gh) = (w.grid.w as i32, w.grid.h as i32);
    let mut seen = vec![false; (gw * gh) as usize];
    let start = IVec2::new(from.x as i32, from.y as i32);
    assert!(!w.grid.is_blocked(start), "the player's army starts on a blocked cell at {start}");
    seen[(start.y * gw + start.x) as usize] = true;
    let mut queue = VecDeque::from([start]);
    while let Some(c) = queue.pop_front() {
        for d in [IVec2::X, IVec2::NEG_X, IVec2::Y, IVec2::NEG_Y] {
            let n = c + d;
            if n.x >= 0 && n.y >= 0 && n.x < gw && n.y < gh && !seen[(n.y * gw + n.x) as usize] && !w.grid.is_blocked(n) {
                seen[(n.y * gw + n.x) as usize] = true;
                queue.push_back(n);
            }
        }
    }
    seen
}

#[test]
fn the_levels_teach_every_tileset() {
    let m = model();
    for t in ["normal", "desert", "swamp", "candy"] {
        let tm = m.tilesets.get(t).unwrap_or_else(|| panic!("no {t} levels learned"));
        assert!(tm.levels >= 10, "{t}: only {} levels", tm.levels);
    }
}

#[test]
fn procedural_levels_are_valid_reachable_and_playable() {
    let defs = defs();
    for seed in [1u64, 42, 2026] {
        for level in [1u32, 2, 4, 8, 13, 25, 60] {
            let map = generate(model(), &defs, level, seed).unwrap_or_else(|e| panic!("level {level} seed {seed}: {e}"));
            let p = plan(level);
            assert_eq!(map.teams.len(), 1 + p.enemies, "level {level}: teams");
            assert_eq!(map.category, "procedural");
            assert_eq!(map.number, Some(level));
            let name = map.name.clone();
            let mut w = World::new(defs.clone(), map).unwrap_or_else(|e| panic!("level {level} seed {seed} ({name}): {e}"));
            // every team owns a colony; the player's army can walk to every colony and structure
            for t in 1..=(1 + p.enemies) as u8 {
                assert!(w.colonies.iter().any(|c| c.team == t), "level {level} seed {seed}: team {t} has no colony");
            }
            let army = w.living_units().find(|u| u.team == 1).map(|u| u.pos).expect("the player has units");
            let seen = reachable(&w, army);
            let gw = w.grid.w as i32;
            let gh = w.grid.h as i32;
            for c in &w.colonies {
                // some cell round the footprint can be walked to
                let r = w.defs.colonies[c.def as usize].half_extent + 1.5;
                let (x0, y0) = (((c.pos.x - r) as i32).max(0), ((c.pos.y - r) as i32).max(0));
                let (x1, y1) = (((c.pos.x + r) as i32).min(gw - 1), ((c.pos.y + r) as i32).min(gh - 1));
                let near = (y0..=y1).any(|y| (x0..=x1).any(|x| seen[(y * gw + x) as usize]));
                assert!(near, "level {level} seed {seed} ({name}): colony at {} cannot be reached", c.pos);
            }
            // a few seconds of play: bots act, nothing panics, nobody has won yet
            w.run(30 * 8);
            assert!(!w.game_over, "level {level} seed {seed} ({name}) ended within 8 s");
        }
    }
}

#[test]
fn the_same_seed_gives_the_same_level_and_others_differ() {
    let defs = defs();
    let a = generate(model(), &defs, 7, 99).unwrap();
    let b = generate(model(), &defs, 7, 99).unwrap();
    let c = generate(model(), &defs, 8, 99).unwrap();
    let d = generate(model(), &defs, 7, 100).unwrap();
    assert_eq!(a.tiles, b.tiles);
    assert_eq!(a.cells, b.cells);
    assert_eq!(a.name, b.name);
    assert_eq!(format!("{:?}", a.colonies), format!("{:?}", b.colonies));
    assert_ne!(a.tiles, c.tiles, "the next level is a new map");
    assert_ne!(a.tiles, d.tiles, "another run is a new map");
}

#[test]
fn the_ground_has_more_than_plain_earth() {
    // the learned layouts bring water, rock or scrub; the generator should not fall back to plain
    // ground on most levels
    let defs = defs();
    let mut varied = 0;
    for seed in 0..12u64 {
        let map = generate(model(), &defs, 5, seed).unwrap();
        let cells = map.cells.unwrap();
        if cells.chars().any(|c| matches!(c, 'w' | 'r' | 'v')) {
            varied += 1;
        }
    }
    assert!(varied >= 9, "only {varied} of 12 levels have any water, rock or scrub");
}

#[test]
fn every_level_is_at_least_as_hard_as_the_last() {
    let mut last = plan(1);
    for level in 2..=200 {
        let p = plan(level);
        assert!(p.enemies >= last.enemies && p.enemy_colonies >= last.enemy_colonies && p.enemy_turrets >= last.enemy_turrets, "level {level}");
        assert!(p.enemy_units.iter().sum::<u32>() >= last.enemy_units.iter().sum::<u32>(), "level {level}: enemy army");
        assert!(p.breed_speed >= last.breed_speed && p.creep_scale >= last.creep_scale && p.bot_delay <= last.bot_delay, "level {level}");
        last = p;
    }
    assert!(plan(200).breed_speed > plan(100).breed_speed, "it keeps getting harder");
}
