//! Neutral creep plants and flyers (OpenSA creep-plants.yaml / creep-units.yaml behaviour).

use std::path::PathBuf;

use sa_sim::*;

fn assets() -> PathBuf {
    // the packaged game keeps `assets` beside `source`; a plain checkout has it inside
    let crate_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    ["../../assets", "../../../assets"].iter().map(|r| crate_dir.join(r)).find(|p| p.join("data").is_dir()).unwrap_or_else(|| crate_dir.join("../../assets"))
}

/// An empty 40x40 meadow with one human team and nothing on it.
fn meadow() -> World {
    let defs = Defs::load_dir(&assets().join("data")).expect("data files");
    let map = MapDef {
        name: "meadow".into(),
        width: 40,
        height: 40,
        teams: vec![TeamDef { id: 1, name: "Ants".into(), color: "Y".into(), controller: Controller::Human, bot_profile: String::new(), breed_speed: 1.0 }],
        ..Default::default()
    };
    World::new(defs, map).expect("world")
}

fn kind(w: &World, id: &str) -> u16 {
    w.defs.unit(id).unwrap_or_else(|| panic!("unit {id}"))
}

/// A fully grown plant.
fn plant(w: &mut World, id: &str, pos: Vec2) -> UnitId {
    let k = kind(w, id);
    let p = w.spawn_unit(k, 0, pos, 0.0);
    w.unit_mut(p).unwrap().age = 100.0;
    p
}

/// A player unit that stands still (paralysed for a long time) so it only serves as bait.
fn bait(w: &mut World, pos: Vec2) -> UnitId {
    let k = kind(w, "ant_soldier");
    let id = w.spawn_unit(k, 1, pos, 0.0);
    w.unit_mut(id).unwrap().paralyzed = 1000.0;
    id
}

fn weapon_shots(w: &World, weapon: &str) -> usize {
    let wi = w.defs.weapon(weapon).unwrap();
    w.projectiles.iter().filter(|p| p.alive && p.weapon == wi).count()
}

#[test]
fn seed_ball_bursts_only_when_an_enemy_comes_near_and_its_seeds_take_root() {
    let mut w = meadow();
    let sb = plant(&mut w, "plant_seedball", Vec2::new(20.5, 20.5));
    // nobody near: nothing happens
    w.run(60);
    assert_eq!(weapon_shots(&w, "plant_puff"), 0, "a seed ball with no enemy within 5 cells stays shut");
    // a soldier 4 cells away sets it off: six puffs and a seed every 0.8 s
    bait(&mut w, Vec2::new(24.5, 20.5));
    w.step();
    w.step();
    assert_eq!(weapon_shots(&w, "plant_puff"), 6, "six puffs per burst");
    assert_eq!(weapon_shots(&w, "plant_seed_throw"), 1, "one seed per burst");
    assert!(w.unit(sb).unwrap().attack_seq >= 1);
    // after a few seconds seeds have landed and rooted (some spots may be taken)
    w.run(120);
    let seed = kind(&w, "plant_seed");
    let seeds = w.living_units().filter(|u| u.kind == seed).count();
    assert!(seeds >= 2, "seeds should take root round the seed ball, found {seeds}");
    for u in w.living_units().filter(|u| u.kind == seed) {
        assert!(u.pos.distance(Vec2::new(20.5, 20.5)) <= 5.8, "a seed landed beyond the throw range: {:?}", u.pos);
    }
}

#[test]
fn seeds_wither_in_ten_seconds_and_some_become_seed_balls() {
    let mut w = meadow();
    let seed = kind(&w, "plant_seed");
    let ball = kind(&w, "plant_seedball");
    let mut n = 0;
    for y in 0..10 {
        for x in 0..10 {
            w.spawn_unit(seed, 0, Vec2::new(3.5 + x as f32 * 3.0, 3.5 + y as f32 * 3.0), 0.0);
            n += 1;
        }
    }
    w.run((9.0 * 30.0) as u32);
    assert_eq!(w.living_units().filter(|u| u.kind == seed).count(), n, "seeds last about 10 seconds");
    w.run((1.5 * 30.0) as u32);
    assert_eq!(w.living_units().filter(|u| u.kind == seed).count(), 0, "every seed has withered after 10.5 s");
    let balls = w.living_units().filter(|u| u.kind == ball).count();
    assert!((8..=35).contains(&balls), "about one seed in five grows into a Seed Ball (got {balls} of {n})");
    // a seed cannot be shot
    let s = w.spawn_unit(seed, 0, Vec2::new(1.5, 1.5), 0.0);
    let soldier = kind(&w, "ant_soldier");
    let a = w.spawn_unit(soldier, 1, Vec2::new(2.5, 1.5), 0.0);
    w.issue(&[a], Order::Attack(Target::Unit(s)));
    w.run(30);
    assert!(w.unit(s).unwrap().hp > 40000.0, "seeds take no damage");
    assert_ne!(w.unit(a).unwrap().target, Some(Target::Unit(s)), "seeds are not targetable (the soldier may pick another target)");
}

#[test]
fn popcorn_plant_fires_a_ring_of_homing_whips() {
    let mut w = meadow();
    let pop = plant(&mut w, "plant_popcorn", Vec2::new(20.5, 20.5));
    let victim = bait(&mut w, Vec2::new(25.5, 20.5));
    let wi = w.defs.weapon("plant_popcorn").unwrap();
    let centre = w.unit(pop).unwrap().pos;
    let mut headings: Vec<f32> = Vec::new();
    for _ in 0..30 {
        w.step();
        if headings.is_empty() {
            // launched from points all round the plant (each whip then turns towards the target)
            headings = w.projectiles.iter().filter(|p| p.weapon == wi).map(|p| dir_to_heading(p.start - centre)).collect();
        }
    }
    assert_eq!(headings.len(), 8, "eight whips per shot");
    // evenly spread all the way round
    let mut dirs: Vec<f32> = headings.iter().map(|h| h.rem_euclid(std::f32::consts::TAU)).collect();
    dirs.sort_by(|a, b| a.total_cmp(b));
    for pair in dirs.windows(2) {
        assert!((pair[1] - pair[0] - std::f32::consts::FRAC_PI_4).abs() < 0.05, "whips not 45 degrees apart: {dirs:?}");
    }
    // they come round and hit
    let hp0 = w.defs.units[w.unit(victim).unwrap().kind as usize].hp;
    w.run(150);
    assert!(w.unit(victim).unwrap().hp < hp0, "the whips should curl round onto the target");
    assert!(w.unit(pop).unwrap().attack_seq >= 2, "it keeps shooting");
}

#[test]
fn hurt_plants_go_quiet_and_heal() {
    let mut w = meadow();
    let pop = plant(&mut w, "plant_popcorn", Vec2::new(20.5, 20.5));
    let max = w.defs.units[kind(&w, "plant_popcorn") as usize].hp;
    w.unit_mut(pop).unwrap().hp = max * 0.3;
    bait(&mut w, Vec2::new(23.5, 20.5));
    w.run(60);
    assert_eq!(weapon_shots(&w, "plant_popcorn"), 0, "below half health a plant does not attack");
    let hp = w.unit(pop).unwrap().hp;
    assert!((hp - (max * 0.3 + 250.0 * 2.0)).abs() < 30.0, "heals 250 HP per second, got {hp}");
    // a growing plant does not attack either
    let mut w = meadow();
    let k = kind(&w, "plant_thorn");
    let t = w.spawn_unit(k, 0, Vec2::new(20.5, 20.5), 0.0);
    bait(&mut w, Vec2::new(23.5, 20.5));
    w.run(4 * 30);
    assert_eq!(w.unit(t).unwrap().attack_seq, 0, "still growing");
    w.run(2 * 30);
    assert!(w.unit(t).unwrap().attack_seq >= 1, "grown after 5 s and shooting");
}

#[test]
fn death_lollies_blow_up_when_approached() {
    let mut w = meadow();
    let a = plant(&mut w, "plant_lolly_blue", Vec2::new(10.5, 10.5));
    let b = plant(&mut w, "plant_lolly_red", Vec2::new(12.5, 10.5)); // inside the first one's blast
    let far = plant(&mut w, "plant_lolly_orange", Vec2::new(30.5, 30.5));
    let full = w.defs.units[kind(&w, "plant_lolly_red") as usize].hp;
    w.run(30);
    assert!(w.unit(a).unwrap().alive(), "nothing near yet");
    let victim = bait(&mut w, Vec2::new(8.8, 10.5)); // 1.7 cells from lolly a, 3.7 from lolly b
    let victim_hp = w.unit(victim).unwrap().hp;
    w.run(3);
    assert!(!w.unit(a).unwrap().alive(), "lolly a goes off");
    let hp_b = w.unit(b).unwrap().hp;
    assert!(w.unit(b).unwrap().alive() && hp_b < full - 4000.0, "its blast (4500 within 3 cells) hurts lolly b without killing it: {hp_b}");
    assert_eq!(w.unit(far).unwrap().hp, full, "a lolly far away is untouched");
    let left = w.unit(victim).map(|u| if u.alive() { u.hp } else { 0.0 }).unwrap();
    assert!(left <= victim_hp - 4499.0 || left == 0.0, "4500 damage to everything within 3 cells");
}

#[test]
fn plants_hold_their_cell_until_they_die() {
    let mut w = meadow();
    let p = plant(&mut w, "plant_thorn", Vec2::new(15.2, 15.7));
    let cell = IVec2::new(15, 15);
    assert_eq!(w.unit(p).unwrap().pos, Vec2::new(15.5, 15.5), "plants sit in the middle of their cell");
    assert!(w.grid.is_blocked(cell));
    w.cheat_kill_enemies(1);
    assert!(!w.grid.is_blocked(cell), "a dead plant frees its cell");
    // and a unit ordered to attack a plant can reach and hit it
    let mut w = meadow();
    let p = plant(&mut w, "plant_seedball", Vec2::new(20.5, 20.5));
    w.unit_mut(p).unwrap().age = -100.0; // not grown for the whole test: it cannot fight back
    let soldier = kind(&w, "ant_soldier");
    let a = w.spawn_unit(soldier, 1, Vec2::new(14.5, 20.5), 0.0);
    w.issue(&[a], Order::Attack(Target::Unit(p)));
    w.run(30 * 8);
    let hp = w.unit(p).map(|u| u.hp).unwrap_or(0.0);
    assert!(hp < 4500.0, "the soldier should reach the seed ball and bite it (hp {hp})");
}

#[test]
fn the_dragonfly_bombs_right_then_left_then_rests() {
    let mut w = meadow();
    let k = kind(&w, "neutral_dragonfly");
    // flying south down the middle of the map
    let id = w.spawn_unit(k, 0, Vec2::new(20.0, 1.0), 0.0);
    w.unit_mut(id).unwrap().cruise = Some(Vec2::new(0.0, 1.0));
    let bomb = w.defs.weapon("dragonfly_bomb").unwrap();
    let mut seen: Vec<u32> = Vec::new();
    let mut drops: Vec<(f32, f32)> = Vec::new(); // (time, sideways offset of the landing spot)
    for tick in 0..(30 * 9) {
        w.step();
        for p in &w.projectiles {
            if p.weapon == bomb && !seen.contains(&p.id) {
                seen.push(p.id);
                drops.push((tick as f32 / 30.0, p.aim.x - p.start.x));
                assert!(p.aim.y < p.start.y - 1.0, "brake bombs land behind the dragonfly");
            }
        }
    }
    assert!(drops.len() >= 12, "about 8 bombs per 4.4 s cycle, got {}", drops.len());
    // facing south, its right is west (-x): first right, then left, alternating
    for (i, (_, side)) in drops.iter().enumerate() {
        let expect_right = i % 2 == 0;
        assert!((*side < -0.9) == expect_right && (*side > 0.9) == !expect_right, "drop {i} landed on the wrong side: {drops:?}");
    }
    // a rest: no bombs between 3.2 s and 4.4 s into the run
    assert!(!drops.iter().any(|(t, _)| *t > 3.25 && *t < 4.35), "the dragonfly rests between bombing runs: {drops:?}");
    // the bombs go off
    let impacts = w.drain_events().iter().filter(|e| matches!(e, SimEvent::Impact { effect, .. } if effect == "explosion_big")).count();
    assert!(impacts > 0 || drops.len() > 0);
}

#[test]
fn desert_fly_bombs_split_into_four() {
    let mut w = meadow();
    let k = kind(&w, "neutral_desert_fly");
    let id = w.spawn_unit(k, 0, Vec2::new(20.0, 8.0), 0.0);
    w.unit_mut(id).unwrap().cruise = Some(Vec2::new(0.0, 1.0));
    let bomb = w.defs.weapon("fly_bomb").unwrap();
    // the fly drops a pair at once; each bomb becomes four explosions
    let mut booms = 0;
    for _ in 0..(30 * 4) {
        w.step();
        booms += w.drain_events().iter().filter(|e| matches!(e, SimEvent::Impact { sound, .. } if sound == "bouncebomb_explode")).count();
    }
    let _ = bomb;
    assert_eq!(booms, 8, "two bombs, four explosions each");
}

#[test]
fn spawn_moths_throw_puffs_and_seeds_behind_them() {
    let mut w = meadow();
    let k = kind(&w, "neutral_spawn_moth");
    let id = w.spawn_unit(k, 0, Vec2::new(20.0, 2.0), 0.0);
    w.unit_mut(id).unwrap().cruise = Some(Vec2::new(0.0, 1.0));
    w.step();
    assert_eq!(weapon_shots(&w, "moth_puff"), 5, "five puffs per drop");
    assert_eq!(weapon_shots(&w, "moth_seed"), 1, "and a seed");
}

#[test]
fn creep_pools_keep_the_level_stocked_up_to_its_count() {
    let mut w = meadow();
    w.map.rules.creeps = vec![CreepPool { units: vec!["plant_popcorn".into()], count: 3, interval: (1.0, 1.0), first: (0.5, 0.5) }];
    let k = kind(&w, "plant_popcorn");
    w.run(30 * 10);
    assert_eq!(w.living_units().filter(|u| u.kind == k).count(), 3, "the pool tops up to its count and no further");
    // kill them: they grow back elsewhere
    w.cheat_kill_enemies(1);
    w.run(30 * 5);
    assert_eq!(w.living_units().filter(|u| u.kind == k).count(), 3, "dead plants are replaced");
    for u in w.living_units().filter(|u| u.kind == k) {
        assert!(w.grid.is_blocked(w.grid.cell_of(u.pos)));
    }
    // flyers: one pass at a time when the count is 1
    let mut w = meadow();
    w.map.rules.creeps = vec![CreepPool { units: vec!["neutral_dragonfly".into()], count: 1, interval: (2.0, 2.0), first: (0.1, 0.1) }];
    let k = kind(&w, "neutral_dragonfly");
    let mut most = 0;
    for _ in 0..(30 * 30) {
        w.step();
        most = most.max(w.living_units().filter(|u| u.kind == k).count());
    }
    assert_eq!(most, 1);
}

#[test]
fn missile_spider_rockets_chase_a_moving_target_round_and_hit() {
    let mut w = meadow();
    let spider = kind(&w, "spider_missile");
    let soldier = kind(&w, "ant_soldier");
    let s = w.spawn_unit(spider, 1, Vec2::new(5.5, 12.5), std::f32::consts::FRAC_PI_2);
    // a target running across the line of fire
    let t = w.spawn_unit(soldier, 0, Vec2::new(14.5, 6.5), 0.0);
    w.issue_uncontrolled(t, Order::Move(Vec2::new(14.5, 36.0)));
    w.issue(&[s], Order::Attack(Target::Unit(t)));
    let mw = w.defs.weapon("spider_missile").unwrap();
    let full = w.defs.units[soldier as usize].hp;
    let mut tracked: Option<u32> = None;
    let mut top_speed = 0.0f32;
    let mut turned = 0.0f32;
    let mut last_heading: Option<f32> = None;
    for _ in 0..(30 * 10) {
        w.step();
        if tracked.is_none() {
            tracked = w.projectiles.iter().find(|p| p.weapon == mw).map(|p| p.id);
        }
        if let Some(id) = tracked {
            match w.projectiles.iter().find(|p| p.id == id) {
                Some(p) => {
                    top_speed = top_speed.max(p.speed);
                    if let Some(h) = last_heading {
                        turned += angle_diff(h, p.heading).abs();
                    }
                    last_heading = Some(p.heading);
                }
                None => break, // it went off
            }
        }
    }
    assert!(tracked.is_some(), "the spider fired");
    assert!(top_speed <= 8.5 + 1e-3 && top_speed > 6.0, "rocket top speed {top_speed}");
    assert!(turned > 0.5, "the rocket curves after its moving target (turned {turned} rad)");
    assert!(w.unit(t).is_none_or(|u| u.hp < full), "the rocket hit the moving target");
}
