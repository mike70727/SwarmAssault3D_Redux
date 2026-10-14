//! Headless battle tests: these exercise movement, path-finding, combat, death, colony turrets,
//! colony capture, AI and victory without any rendering.

use std::path::PathBuf;

use sa_sim::*;

fn assets() -> PathBuf {
    // the packaged game keeps `assets` beside `source`; a plain checkout has it inside
    let crate_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    ["../../assets", "../../../assets"].iter().map(|r| crate_dir.join(r)).find(|p| p.join("data").is_dir()).unwrap_or_else(|| crate_dir.join("../../assets"))
}

fn world() -> World {
    load_world(&assets(), "ants_skirmish.ron").expect("load world")
}

#[test]
fn data_files_load_and_every_model_is_named() {
    let w = world();
    assert_eq!(w.defs.units.iter().filter(|u| u.plant.is_none()).count(), 21, "21 roster entries expected");
    assert_eq!(w.defs.units.iter().filter(|u| u.plant.is_some()).count(), 9, "creep plants: popcorn, thorn, seed ball, seed, freckle, four lollies");
    assert!(w.defs.colonies.len() >= 5, "5 colony families (+ level structures) expected");
    for u in &w.defs.units {
        assert!(!u.model.is_empty(), "unit {} has no model", u.name);
        // seeds and Death Lollies have no gun: a lolly's weapon is its blast when it dies
        assert!(u.weapon.is_some() || u.plant.is_some(), "unit {} has no weapon", u.name);
    }
    assert_eq!(w.colonies.len(), 2);
    assert_eq!(w.living_units().count(), 16);
}

#[test]
fn units_walk_to_a_move_order_around_obstacles() {
    let mut w = world();
    let ids: Vec<UnitId> = w.living_units().filter(|u| u.team == 1).map(|u| u.id).collect();
    // destination behind the central rocks
    let goal = Vec2::new(40.0, 40.0);
    w.issue(&ids, Order::Move(goal));
    let mut arrived_at: Vec<Option<u32>> = vec![None; ids.len()];
    for t in 0..30 * 25 {
        w.step();
        w.events.clear();
        // never inside a blocked cell
        for u in w.living_units() {
            assert!(!w.grid.is_blocked_pos(u.pos), "unit walked into a blocked cell at {:?}", u.pos);
        }
        for (k, id) in ids.iter().enumerate() {
            if arrived_at[k].is_none() && w.unit(*id).is_some_and(|u| u.pos.distance(goal) < 3.5) {
                arrived_at[k] = Some(t);
            }
        }
    }
    let arrived = arrived_at.iter().filter(|a| a.is_some()).count();
    assert!(arrived >= ids.len() - 1, "only {arrived}/{} units arrived near {goal:?}: {arrived_at:?}", ids.len());
    let slowest = arrived_at.iter().flatten().max().copied().unwrap_or(0);
    assert!(slowest < 30 * 20, "slowest unit took {slowest} ticks");
}

#[test]
fn soldiers_fight_and_die() {
    let mut w = world();
    let yellow: Vec<UnitId> = w.living_units().filter(|u| u.team == 1).map(|u| u.id).collect();
    let red: Vec<UnitId> = w.living_units().filter(|u| u.team == 2).map(|u| u.id).collect();
    // teleport both groups into the middle so they meet quickly
    for (i, id) in yellow.iter().enumerate() {
        w.unit_mut(*id).unwrap().pos = Vec2::new(28.0 + i as f32 * 0.8, 30.0);
    }
    for (i, id) in red.iter().enumerate() {
        w.unit_mut(*id).unwrap().pos = Vec2::new(28.0 + i as f32 * 0.8, 36.0);
    }
    w.issue(&yellow, Order::AttackMove(Vec2::new(31.0, 36.0)));
    let mut attacks = 0;
    let mut deaths = 0;
    for _ in 0..30 * 40 {
        w.step();
        for e in w.drain_events() {
            match e {
                SimEvent::AttackStarted { .. } => attacks += 1,
                SimEvent::UnitDied(_) => deaths += 1,
                _ => {}
            }
        }
    }
    assert!(attacks > 20, "expected attacks, got {attacks}");
    assert!(deaths >= 4, "expected deaths, got {deaths}");
    assert!(w.stats.units_killed >= 4);
}

#[test]
fn colony_turrets_shoot_intruders() {
    let mut w = world();
    let red: Vec<UnitId> = w.living_units().filter(|u| u.team == 2).map(|u| u.id).collect();
    let yellow_colony = w.colonies.iter().find(|c| c.team == 1).unwrap().pos;
    for (i, id) in red.iter().enumerate() {
        let u = w.unit_mut(*id).unwrap();
        u.pos = yellow_colony + Vec2::new(6.0 + i as f32 * 0.5, 0.0);
    }
    w.issue(&red, Order::Move(yellow_colony + Vec2::new(5.0, 0.0)));
    let mut turret_shots = 0;
    for _ in 0..30 * 10 {
        w.step();
        for e in w.drain_events() {
            if let SimEvent::TurretFired { .. } = e {
                turret_shots += 1;
            }
        }
    }
    assert!(turret_shots > 10, "turrets fired {turret_shots} times");
    let dead = red.iter().filter(|id| !w.unit(**id).is_some_and(|u| u.alive())).count();
    assert!(dead >= 1, "turrets should have killed at least one soldier, dead={dead}");
}

#[test]
fn colony_capture_flow_bits_and_ownership() {
    let mut w = world();
    let red_colony = w.colonies.iter().find(|c| c.team == 2).unwrap().id;
    let cpos = w.colonies[red_colony as usize].pos;
    // remove the red army so yellow collects every bit
    let red: Vec<UnitId> = w.living_units().filter(|u| u.team == 2).map(|u| u.id).collect();
    for id in red {
        w.unit_mut(id).unwrap().hp = 0.0;
    }
    // stop red from breeding so the test is deterministic, and its colony from healing meanwhile
    // (the original heals a colony only while it does not breed; a few biters at the front of the
    // queue could not outpace that under the turrets' fire)
    w.set_production(red_colony, None);
    let def = w.colonies[red_colony as usize].def as usize;
    w.defs.colonies[def].regen_per_s = 0.0;
    // the turrets pick off the soldiers queueing at the wall; this test is about the bits after
    w.cheats.invincible = Some(1);
    let yellow: Vec<UnitId> = w.living_units().filter(|u| u.team == 1).map(|u| u.id).collect();
    for (i, id) in yellow.iter().enumerate() {
        w.unit_mut(*id).unwrap().pos = cpos + Vec2::new(-5.0, (i as f32 - 4.0) * 0.9);
    }
    // bring the colony to the brink and let the soldiers finish it (provisional map rule)
    let max = w.colony_def(&w.colonies[red_colony as usize]).hp;
    w.colonies[red_colony as usize].hp = max * 0.02;
    w.issue(&yellow, Order::Attack(Target::Colony(red_colony)));
    let mut defeated = false;
    let mut scattered = false;
    let mut picked = 0;
    let mut captured: Option<u8> = None;
    for _ in 0..30 * 120 {
        // red's bot would switch breeding back on while yellow's soldiers queue at the wall
        if w.colonies[red_colony as usize].team == 2 {
            w.set_production(red_colony, None);
        }
        w.step();
        for e in w.drain_events() {
            match e {
                SimEvent::ColonyDefeated(c) if c == red_colony => defeated = true,
                SimEvent::ColonyScattered(c) if c == red_colony => scattered = true,
                SimEvent::BitPicked { team, .. } => {
                    assert_eq!(team, 1);
                    picked += 1;
                }
                SimEvent::ColonyCaptured { colony, team } if colony == red_colony => captured = Some(team),
                _ => {}
            }
        }
        if captured.is_some() {
            break;
        }
    }
    assert!(defeated, "colony was never defeated");
    assert!(scattered, "bits were never scattered");
    assert!(picked >= 5, "yellow picked only {picked} bits");
    assert_eq!(captured, Some(1), "yellow should own the colony");
    let c = &w.colonies[red_colony as usize];
    assert_eq!(c.team, 1);
    assert!(c.active());
    assert!((c.hp - max * 0.25).abs() < 0.01, "resurrect HP should be 25% of {max}: {}", c.hp);
}

#[test]
fn colonies_breed_units_up_to_the_cap() {
    let mut w = world();
    let before = w.team_count(2);
    w.run(30 * 60);
    let after = w.team_count(2);
    assert!(after > before, "bot colony should breed: {before} -> {after}");
    assert!(after <= w.unit_cap());
}

#[test]
fn bot_wins_against_an_idle_human_or_the_game_keeps_going() {
    // The red bot should eventually attack; the yellow colony's turrets defend. Either the game
    // ends with a winner or both sides are still alive after the budget – the point is that the
    // AI issues orders and nothing panics.
    let mut w = world();
    let mut bot_orders = 0;
    for _ in 0..30 * 240 {
        w.step();
        for e in w.drain_events() {
            if let SimEvent::AttackStarted { unit, .. } = e
                && w.unit(unit).is_some_and(|u| u.team == 2)
            {
                bot_orders += 1;
            }
        }
        if w.game_over {
            break;
        }
    }
    assert!(bot_orders > 0, "the bot never attacked");
}

#[test]
fn paralysis_and_projectiles_from_the_full_roster() {
    let mut w = world();
    let yellow: Vec<UnitId> = w.living_units().filter(|u| u.team == 1).map(|u| u.id).collect();
    let red: Vec<UnitId> = w.living_units().filter(|u| u.team == 2).map(|u| u.id).collect();
    for id in yellow.iter().chain(red.iter()) {
        w.unit_mut(*id).unwrap().hp = 0.0;
    }
    w.run(1);
    let wasp = w.defs.unit("wasp_paralysis").unwrap();
    let grenadier = w.defs.unit("ant_grenadier").unwrap();
    let soldier = w.defs.unit("ant_soldier").unwrap();
    let a = w.spawn_unit(wasp, 1, Vec2::new(30.0, 30.0), 0.0);
    let g = w.spawn_unit(grenadier, 1, Vec2::new(31.0, 30.0), 0.0);
    let s = w.spawn_unit(soldier, 2, Vec2::new(33.0, 36.0), 0.0);
    w.issue(&[a], Order::Attack(Target::Unit(s)));
    w.issue(&[g], Order::Attack(Target::Unit(s)));
    let mut paralyzed = false;
    let mut projectiles = 0;
    let mut impacts = 0;
    for _ in 0..30 * 20 {
        w.step();
        for e in w.drain_events() {
            match e {
                SimEvent::UnitParalyzed(id) if id == s => paralyzed = true,
                SimEvent::ProjectileSpawned(_) => projectiles += 1,
                SimEvent::Impact { .. } => impacts += 1,
                _ => {}
            }
        }
    }
    assert!(paralyzed, "soldier was never paralysed");
    assert!(projectiles > 0 && impacts > 0, "projectiles {projectiles}, impacts {impacts}");
    assert!(w.unit(s).is_none_or(|u| !u.alive()), "grenades should have killed the soldier");
}

#[test]
fn save_and_load_round_trip_is_deterministic() {
    let mut w = world();
    let ids: Vec<UnitId> = w.living_units().filter(|u| u.team == 1).map(|u| u.id).collect();
    w.issue(&ids, Order::AttackMove(Vec2::new(50.0, 16.0)));
    w.run(30 * 5);
    let text = save::to_string(&w).expect("serialize");
    let mut a = save::from_str(&text).expect("deserialize");
    let mut b = w.clone();
    a.run(30 * 10);
    b.run(30 * 10);
    let pa: Vec<Vec2> = a.living_units().map(|u| u.pos).collect();
    let pb: Vec<Vec2> = b.living_units().map(|u| u.pos).collect();
    assert_eq!(pa, pb, "simulation diverged after save/load");
    assert_eq!(a.stats.shots, b.stats.shots);
}

#[test]
fn melee_bugs_bite_a_colony_single_file_and_can_bring_it_down() {
    // In the original, melee bugs walk up to a colony and bite it from one stretch of wall, so an
    // attack forms a line (FUN_00402e90 "mode 20"; Mike: "they all lined up in a straight line").
    // 40 soldiers that the turrets cannot kill (invincible cheat) must bring the colony down that
    // way, with never more than the front of the line biting at once (taking it over afterwards is
    // `colony_capture_flow_bits_and_ownership`).
    let mut w = world();
    let red_colony = w.colonies.iter().find(|c| c.team == 2).unwrap().id;
    let cpos = w.colonies[red_colony as usize].pos;
    w.set_production(red_colony, None);
    // an enemy colony normally breeds, and the original heals a colony only while it does not
    let def = w.colonies[red_colony as usize].def as usize;
    w.defs.colonies[def].regen_per_s = 0.0;
    let red: Vec<UnitId> = w.living_units().filter(|u| u.team == 2).map(|u| u.id).collect();
    for id in red {
        w.unit_mut(id).unwrap().hp = 0.0;
    }
    w.cheats.invincible = Some(1);
    let soldier = w.defs.unit("ant_soldier").unwrap();
    let mut army = Vec::new();
    for i in 0..40 {
        let p = cpos + Vec2::new(-16.0 + (i % 8) as f32 * 0.9, -4.0 + (i / 8) as f32 * 0.9);
        army.push(w.spawn_unit(soldier, 1, p, 0.0));
    }
    w.issue(&army, Order::Attack(Target::Colony(red_colony)));
    let mut defeated = false;
    let mut most_biting = 0;
    let mut widest = 0.0f32;
    for _ in 0..30 * 300 {
        w.step();
        let biters: Vec<Vec2> = army
            .iter()
            .filter_map(|id| w.unit(*id))
            .filter(|u| u.anim == Anim::Attack && u.target == Some(Target::Colony(red_colony)))
            .map(|u| u.pos)
            .collect();
        most_biting = most_biting.max(biters.len());
        for a in &biters {
            for b in &biters {
                widest = widest.max(a.distance(*b));
            }
        }
        for e in w.drain_events() {
            if e == SimEvent::ColonyDefeated(red_colony) {
                defeated = true;
            }
        }
        if defeated {
            break;
        }
    }
    assert!(most_biting >= 2, "the front of the line should bite side by side (at most {most_biting} bit)");
    assert!(most_biting <= 4, "{most_biting} soldiers bit at once: they surrounded the colony instead of lining up");
    assert!(widest <= 2.5, "biters {widest} cells apart: not from one spot");
    assert!(defeated, "40 soldiers biting single file could not bring the colony down");
}

#[test]
fn five_families_map_runs_with_flyers_pirates_and_ranged_capture() {
    let mut w = load_world(&assets(), "five_families.ron").expect("load five_families");
    assert_eq!(w.colonies.len(), 5);
    assert!(!w.map.rules.melee_can_damage_colonies);
    let mut flyers = 0;
    let mut pirates = 0;
    let mut impacts = 0;
    // force the spawners early so the test does not need minutes of sim time
    w.spawn_flyer(w.defs.unit("neutral_dragonfly").unwrap());
    w.spawn_pirates();
    // grenadiers + bazookas (ranged, colony-capable) attack the neutral beetle colony
    let beetle = w.colonies.iter().find(|c| c.team == 0 && w.colony_def(c).family == Family::Beetle).unwrap().id;
    let bpos = w.colonies[beetle as usize].pos;
    let gren = w.defs.unit("ant_grenadier").unwrap();
    let baz = w.defs.unit("ant_bazooka").unwrap();
    let mut army = Vec::new();
    for i in 0..30 {
        let kind = if i % 3 == 0 { baz } else { gren };
        army.push(w.spawn_unit(kind, 1, bpos + Vec2::new(10.0 + (i % 6) as f32, -3.0 + (i / 6) as f32), 0.0));
    }
    w.colonies[beetle as usize].hp = w.colony_def(&w.colonies[beetle as usize]).hp * 0.3; // keep the test short
    w.issue(&army, Order::Attack(Target::Colony(beetle)));
    let soldier = w.defs.unit("ant_soldier").unwrap();
    let s = w.spawn_unit(soldier, 1, bpos + Vec2::new(8.0, 0.0), 0.0);
    w.issue(&[s], Order::Attack(Target::Colony(beetle)));
    let mut captured = None;
    let (mut picked, mut expired, mut defeated_at) = (0, 0, None);
    for t in 0..30 * 300 {
        w.step();
        for e in w.drain_events() {
            match e {
                SimEvent::FlyerSpawn(_) => flyers += 1,
                SimEvent::PirateSpawn { count, .. } => pirates += count,
                SimEvent::Impact { .. } => impacts += 1,
                SimEvent::ColonyDefeated(c) if c == beetle => defeated_at = Some(t),
                SimEvent::BitPicked { .. } => picked += 1,
                SimEvent::BitExpired(_) => expired += 1,
                SimEvent::ColonyCaptured { colony, team } if colony == beetle => captured = Some(team),
                _ => {}
            }
        }
        if t % 300 == 0 && defeated_at.is_some() {
            let orders: Vec<String> = army.iter().filter_map(|id| w.unit(*id)).filter(|u| u.alive()).map(|u| format!("{:?}/{:?}/{:?}", u.order, u.anim, u.target.is_some())).take(6).collect();
            eprintln!("t={t} picked={picked} expired={expired} bits_alive={} alive={} orders={:?}", w.bits.iter().filter(|b| b.alive).count(), army.iter().filter(|id| w.unit(**id).is_some_and(|u| u.alive())).count(), orders);
        }
        if captured.is_some() {
            break;
        }
    }
    eprintln!("defeated_at={defeated_at:?} picked={picked} expired={expired} captured={captured:?}");
    assert!(flyers >= 1 && pirates >= 1, "flyers {flyers} pirates {pirates}");
    assert!(impacts > 10);
    assert_eq!(captured, Some(1), "ranged ants should capture the neutral beetle colony");
    // the melee soldier must not have been allowed to attack the colony (no colony damage from it)
    assert!(w.unit(s).is_none_or(|u| !matches!(u.target, Some(Target::Colony(_)))));
}

#[test]
fn neutral_flyers_cross_the_map_and_leave() {
    let mut w = load_world(&assets(), "five_families.ron").expect("load five_families");
    let moth = w.defs.unit("neutral_spawn_moth").unwrap();
    let id = w.spawn_flyer(moth);
    let start = w.unit(id).unwrap().pos;
    let mut last = start;
    let mut stuck_ticks = 0;
    let mut gone_at = None;
    for t in 0..30 * 120 {
        w.step();
        w.events.clear();
        match w.unit(id) {
            Some(u) if u.alive() => {
                if u.pos.distance(last) < 0.01 {
                    stuck_ticks += 1;
                }
                last = u.pos;
            }
            Some(_) => {}
            None => {
                gone_at = Some(t);
                break;
            }
        }
    }
    eprintln!("moth start {start:?} last {last:?} stuck_ticks {stuck_ticks} gone_at {gone_at:?}");
    assert!(stuck_ticks < 30, "flyer got stuck for {stuck_ticks} ticks at {last:?}");
    assert!(gone_at.is_some(), "flyer never left the map (last pos {last:?})");
}
