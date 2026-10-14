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
    let team = |id: u8, name: &str, color: &str| TeamDef { id, name: name.into(), color: color.into(), controller: Controller::Human, bot_profile: String::new(), breed_speed: 1.0 };
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
    // Cannon Beetle: the original plays its attack animation (100+300 ms) and then waits
    // 400..1099 ms, so a shot every 0.8..1.5 s: reload 0.8 s from the start of an attack plus up
    // to 0.7 s at random. With its fire delay of 0.2 s added on top (an old bug) the shortest gap
    // would be 1.0 s.
    let mut w = meadow(false);
    let beetle = spawn(&mut w, "beetle_cannon", 1, Vec2::new(10.5, 20.5));
    let dummy = spawn(&mut w, "ant_soldier", 2, Vec2::new(18.5, 20.5));
    w.unit_mut(dummy).unwrap().paralyzed = 1000.0;
    w.issue(&[beetle], Order::Attack(Target::Unit(dummy)));
    let wd = w.defs.weapons[w.defs.weapon("beetle_cannon").unwrap() as usize].clone();
    let tick = 1.0 / w.defs.rules.tick_hz;
    let ticks = (30.0 * w.defs.rules.tick_hz).round() as u32;
    let (starts, _) = attacks(&mut w, beetle, ticks);
    assert!(starts.len() >= 15, "the cannon beetle attacked only {} times", starts.len());
    let gaps: Vec<f32> = starts.windows(2).map(|p| p[1] - p[0]).collect();
    for g in &gaps {
        assert!((wd.reload - tick..=wd.reload + wd.reload_jitter + 2.0 * tick).contains(g), "a gap of {g:.3} s between shots, outside the original's {:.2}..{:.2} s", wd.reload, wd.reload + wd.reload_jitter);
    }
    let short = gaps.iter().filter(|g| **g < wd.reload + 0.2).count();
    assert!(short > 0, "no gap under {:.2} s: the fire delay is being added to the reload again", wd.reload + 0.2);
    let p = period(&starts);
    assert!((wd.reload + 0.25 * wd.reload_jitter..wd.reload + 0.75 * wd.reload_jitter).contains(&p), "fired every {p:.3} s on average");
}

#[test]
fn biters_bite_every_three_tenths_of_a_second_like_the_original() {
    // the original loops the Ant Soldier's bite animation (150+150 ms, Damage on frame 2); our 3-D
    // bite clip is 0.45 s long and is played faster to keep that rhythm
    let mut w = meadow(false);
    let soldier = spawn(&mut w, "ant_soldier", 1, Vec2::new(17.6, 20.5));
    let dummy = spawn(&mut w, "ant_soldier", 2, Vec2::new(18.5, 20.5));
    w.unit_mut(dummy).unwrap().paralyzed = 1000.0;
    w.issue(&[soldier], Order::Attack(Target::Unit(dummy)));
    let ticks = (6.0 * w.defs.rules.tick_hz).round() as u32;
    let (starts, idle) = attacks(&mut w, soldier, ticks);
    assert!(starts.len() >= 15, "the soldier bit only {} times", starts.len());
    let p = period(&starts);
    assert!((0.29..0.34).contains(&p), "bit every {p:.3} s");
    assert_eq!(idle, 0, "{idle} idle ticks between bites");
}

#[test]
fn back_to_back_attacks_have_no_idle_tick_between_them() {
    // Assault Wasp: the original loops a 50+50 ms attack animation, a shot every 0.1 s; our attack
    // clip (0.23 s) plays faster: the abdomen gun pumps without dropping to idle
    let mut w = meadow(false);
    let wasp = spawn(&mut w, "wasp_assault", 1, Vec2::new(14.5, 20.5));
    let dummy = spawn(&mut w, "ant_soldier", 2, Vec2::new(18.5, 20.5));
    w.unit_mut(dummy).unwrap().paralyzed = 1000.0;
    w.issue(&[wasp], Order::Attack(Target::Unit(dummy)));
    let ticks = (6.0 * w.defs.rules.tick_hz).round() as u32;
    let (starts, idle) = attacks(&mut w, wasp, ticks);
    assert!(starts.len() >= 30, "the assault wasp attacked only {} times", starts.len());
    let p = period(&starts);
    assert!((0.09..0.14).contains(&p), "the assault wasp should fire every ~0.1 s, fired every {p:.3} s");
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

#[test]
fn idle_biters_leave_colonies_alone_but_idle_shooters_take_them_on() {
    // the original: a biter's sensor skips colonies (and flyers); every other unit takes on whatever
    // its sensor finds within its own radius, an enemy colony too
    let mut w = meadow(true);
    w.map.rules.unit_cap = Some(0); // the colony breeds nobody to distract them
    let half = w.defs.colonies[w.colonies[0].def as usize].half_extent;
    // both 6.5 cells from the wall: inside the soldier's sensor (9) and the grenadier's (7)
    let soldier = spawn(&mut w, "ant_soldier", 1, Vec2::new(20.0 - half - 6.5, 20.0));
    let grenadier = spawn(&mut w, "ant_grenadier", 1, Vec2::new(20.0, 20.0 - half - 6.5));
    w.run((3.0 * w.defs.rules.tick_hz) as u32);
    assert_eq!(w.unit(soldier).unwrap().target, None, "an idle biter takes on no colony");
    assert!(matches!(w.unit(grenadier).unwrap().target, Some(Target::Colony(_))), "an idle grenadier takes on the colony its sensor sees");
}

#[test]
fn idle_units_see_as_far_as_the_original_sensors_and_chase() {
    // the Black Widow's sensor reaches 12 cells (ours used to scan 6); it goes after what it sees,
    // however far it runs
    let mut w = meadow(false);
    let widow = spawn(&mut w, "spider_black_widow", 1, Vec2::new(8.5, 20.5));
    let runner = spawn(&mut w, "ant_soldier", 2, Vec2::new(19.5, 20.5)); // 11 cells off
    w.run((1.5 * w.defs.rules.tick_hz) as u32);
    assert_eq!(w.unit(widow).unwrap().target, Some(Target::Unit(runner)), "the widow spotted the soldier 11 cells away");
    w.issue(&[runner], Order::Move(Vec2::new(38.5, 38.5)));
    w.run((12.0 * w.defs.rules.tick_hz) as u32);
    let (wp, rp) = (w.unit(widow).unwrap().pos, w.unit(runner).unwrap().pos);
    assert_eq!(w.unit(widow).unwrap().target, Some(Target::Unit(runner)), "still after it");
    assert!(wp.distance(Vec2::new(8.5, 20.5)) > 15.0 && wp.distance(rp) < 3.0, "the widow chased the soldier across the meadow: {wp:?} vs {rp:?}");
}

#[test]
fn splash_hurts_the_shooters_own_side_too() {
    // the original's collisions never look at teams: a grenade landing in a scrum hurts friends too
    let mut w = meadow(false);
    let gren = spawn(&mut w, "ant_grenadier", 1, Vec2::new(10.5, 20.5));
    let enemy = spawn(&mut w, "ant_soldier", 2, Vec2::new(15.5, 20.5));
    let friend = spawn(&mut w, "ant_soldier", 1, Vec2::new(15.5, 21.0));
    for id in [enemy, friend] {
        let u = w.unit_mut(id).unwrap();
        u.paralyzed = 1000.0;
        u.hp = 1000.0;
    }
    w.issue(&[gren], Order::Attack(Target::Unit(enemy)));
    w.run((6.0 * w.defs.rules.tick_hz) as u32);
    assert!(w.unit(enemy).unwrap().hp < 1000.0, "the grenades hit their target");
    assert!(w.unit(friend).unwrap().hp < 1000.0, "and the friend standing next to it");
}
