//! Weapon timing and line of sight (found by the attack-animation crews, 2026-10-14).

use std::path::PathBuf;

use sa_sim::*;

fn assets() -> PathBuf {
    // the packaged game keeps `assets` beside `source`; a plain checkout has it inside
    let crate_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    ["../../assets", "../../../assets"].iter().map(|r| crate_dir.join(r)).find(|p| p.join("data").is_dir()).unwrap_or_else(|| crate_dir.join("../../assets"))
}

/// An empty 40x40 meadow with two teams, optionally a red colony in the middle.
fn meadow(colony: bool) -> World {
    let defs = Defs::load_dir(&assets().join("data")).expect("data files");
    let team = |id: u8, name: &str, color: &str| TeamDef { id, name: name.into(), color: color.into(), controller: Controller::Human, bot_profile: String::new() };
    let map = MapDef {
        name: "meadow".into(),
        width: 40,
        height: 40,
        teams: vec![team(1, "Beetles", "Y"), team(2, "Ants", "R")],
        colonies: if colony {
            vec![ColonySpawn { colony: "colony_ant".into(), team: 2, pos: Vec2::new(20.0, 20.0), produce: None, defeated: false }]
        } else {
            Vec::new()
        },
        ..Default::default()
    };
    World::new(defs, map).expect("world")
}

fn spawn(w: &mut World, id: &str, team: u8, pos: Vec2) -> UnitId {
    let k = w.defs.unit(id).unwrap_or_else(|| panic!("unit {id}"));
    let u = w.spawn_unit(k, team, pos, 0.0);
    // nobody dies here: the test is about who fires when
    w.unit_mut(u).unwrap().hp = 1.0e9;
    u
}

/// Attack starts of `unit` over `ticks` ticks (in seconds since the first tick), and how many of
/// its ticks after the first attack it spent idle.
fn attacks(w: &mut World, unit: UnitId, ticks: u32) -> (Vec<f32>, u32) {
    let dt = 1.0 / w.defs.rules.tick_hz;
    let (mut starts, mut idle) = (Vec::new(), 0);
    for tick in 0..ticks {
        w.step();
        for e in w.drain_events() {
            if let SimEvent::AttackStarted { unit: u, .. } = e
                && u == unit
            {
                starts.push(tick as f32 * dt);
            }
        }
        if !starts.is_empty() && w.unit(unit).is_some_and(|u| u.anim == Anim::Idle) {
            idle += 1;
        }
    }
    (starts, idle)
}

/// Mean time between consecutive attack starts.
fn period(starts: &[f32]) -> f32 {
    (starts[starts.len() - 1] - starts[0]) / (starts.len() - 1) as f32
}

#[test]
fn a_weapon_fires_once_per_reload_not_once_per_reload_plus_fire_delay() {
    // Cannon Beetle: reload 1.2 s, fire delay 0.2 s; it used to fire once per 1.4 s
    let mut w = meadow(false);
    let beetle = spawn(&mut w, "beetle_cannon", 1, Vec2::new(10.5, 20.5));
    let dummy = spawn(&mut w, "ant_soldier", 2, Vec2::new(18.5, 20.5));
    w.unit_mut(dummy).unwrap().paralyzed = 1000.0;
    w.issue(&[beetle], Order::Attack(Target::Unit(dummy)));
    let ticks = (15.0 * w.defs.rules.tick_hz).round() as u32;
    let (starts, _) = attacks(&mut w, beetle, ticks);
    assert!(starts.len() >= 5, "the cannon beetle attacked only {} times", starts.len());
    let p = period(&starts);
    assert!((1.18..1.26).contains(&p), "a 1.2 s reload should fire every 1.2 s, fired every {p:.3} s");
}

#[test]
fn back_to_back_attacks_have_no_idle_tick_between_them() {
    // Assault Wasp: reload 0.2 s, attack clip 0.23 s: the abdomen gun pumps without dropping to idle
    let mut w = meadow(false);
    let wasp = spawn(&mut w, "wasp_assault", 1, Vec2::new(14.5, 20.5));
    let dummy = spawn(&mut w, "ant_soldier", 2, Vec2::new(18.5, 20.5));
    w.unit_mut(dummy).unwrap().paralyzed = 1000.0;
    w.issue(&[wasp], Order::Attack(Target::Unit(dummy)));
    let ticks = (6.0 * w.defs.rules.tick_hz).round() as u32;
    let (starts, idle) = attacks(&mut w, wasp, ticks);
    assert!(starts.len() >= 10, "the assault wasp attacked only {} times", starts.len());
    let p = period(&starts);
    assert!(p < 0.26, "the assault wasp should attack every ~0.23 s (its clip), attacked every {p:.3} s");
    assert_eq!(idle, 0, "{idle} idle ticks between back-to-back attacks");
}

#[test]
fn instant_hit_guns_shoot_a_colony_from_range() {
    // the Lady Bug's machine gun (range 6, instant hit) used to need to come within 2 cells of a
    // colony: the line of sight was tested against the colony's centre, behind its own footprint
    let mut w = meadow(true);
    let colony = w.colonies[0].id;
    let half = w.defs.colonies[w.colonies[0].def as usize].half_extent;
    let edge_x = 20.0 - half;
    let bug = spawn(&mut w, "beetle_ladybug", 1, Vec2::new(edge_x - 4.5, 20.0));
    w.issue(&[bug], Order::Attack(Target::Colony(colony)));
    let hp0 = w.colonies[colony as usize].hp;
    let mut fired_from = None;
    for _ in 0..(5.0 * w.defs.rules.tick_hz) as u32 {
        w.step();
        if w.colonies[colony as usize].hp < hp0 {
            fired_from = w.unit(bug).map(|u| edge_x - u.pos.x);
            break;
        }
    }
    let d = fired_from.expect("the Lady Bug never hurt the colony");
    assert!(d > 3.0, "the Lady Bug walked up to {d:.2} cells from the colony before it could shoot");
}
