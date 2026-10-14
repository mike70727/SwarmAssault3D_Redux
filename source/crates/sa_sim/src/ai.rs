//! Simple bot controller (assumption A7 – not the original AI).
//!
//! Every bot team: keeps its colonies breeding, defends colonies that are attacked, gathers idle
//! units into squads and sends them at the nearest enemy colony, and sends spare units to collect
//! colony bits.

use glam::Vec2;
use serde::{Deserialize, Serialize};

use crate::world::{Order, UnitId, World};

#[derive(Serialize, Deserialize, Clone, Debug)]
pub struct BotState {
    pub profile: String,
    pub think_timer: f32,
    pub attack_timer: f32,
    pub squad_size: u32,
    pub attack_interval: f32,
    pub defend_radius: f32,
    pub squad: Vec<UnitId>,
    pub squad_goal: Option<Vec2>,
}

impl BotState {
    pub fn new(profile: &str) -> Self {
        let (squad_size, attack_interval) = match profile {
            "easy" => (14, 90.0),
            "hard" => (8, 35.0),
            _ => (10, 55.0),
        };
        Self {
            profile: profile.to_string(),
            think_timer: 0.0,
            attack_timer: attack_interval * 0.6,
            squad_size,
            attack_interval,
            defend_radius: 14.0,
            squad: Vec::new(),
            squad_goal: None,
        }
    }
}

pub fn run_bots(w: &mut World, dt: f32) {
    let teams: Vec<u8> = w.teams.iter().filter(|t| t.bot.is_some() && !t.defeated).map(|t| t.def.id).collect();
    for team in teams {
        let mut bot = w.teams[team as usize].bot.clone().unwrap();
        bot.think_timer -= dt;
        bot.attack_timer -= dt;
        if bot.think_timer <= 0.0 {
            bot.think_timer = 1.0;
            think(w, team, &mut bot);
        }
        w.teams[team as usize].bot = Some(bot);
    }
}

fn think(w: &mut World, team: u8, bot: &mut BotState) {
    // 1. keep every colony breeding
    let colony_ids: Vec<u32> = w.colonies_of(team).map(|c| c.id).collect();
    for cid in &colony_ids {
        let c = &w.colonies[*cid as usize];
        if c.production.kind.is_none() {
            let def = w.colony_def(c);
            // pick a random affordable unit from the family's roster, weighted towards light units
            let roster: Vec<u16> = def.produces.iter().filter_map(|p| w.defs.unit(p)).collect();
            if !roster.is_empty() {
                let r: f32 = rand::Rng::random(&mut w.rng);
                let idx = if r < 0.6 { 0 } else if r < 0.9 { 1.min(roster.len() - 1) } else { 2.min(roster.len() - 1) };
                let kind = roster[idx];
                w.set_production(*cid, Some(kind));
            }
        }
    }

    // 2. collect our idle units
    let idle: Vec<UnitId> = w
        .living_units()
        .filter(|u| u.team == team && matches!(u.order, Order::Idle) && u.target.is_none() && w.unit_def(u).controllable)
        .map(|u| u.id)
        .collect();

    // 3. defend: any enemy near one of our colonies?
    for cid in &colony_ids {
        let cpos = w.colonies[*cid as usize].pos;
        if let Some(enemy) = w.nearest_enemy_unit(team, cpos, bot.defend_radius) {
            let epos = enemy.pos;
            let defenders: Vec<UnitId> = w
                .living_units()
                .filter(|u| u.team == team && u.pos.distance(cpos) < bot.defend_radius * 2.0 && u.target.is_none() && w.unit_def(u).controllable)
                .map(|u| u.id)
                .collect();
            if !defenders.is_empty() {
                w.issue(&defenders, Order::AttackMove(epos));
            }
            return; // defending has priority this think
        }
    }

    // 4. bits: send the nearest idle unit to each landed bit (max a few)
    let bits: Vec<(u32, Vec2)> = w.bits.iter().filter(|b| b.alive && b.landed()).map(|b| (b.id, b.end)).collect();
    let mut used = Vec::new();
    for (bid, bpos) in bits.iter().take(6) {
        let mut best: Option<(f32, UnitId)> = None;
        for id in &idle {
            if used.contains(id) {
                continue;
            }
            if let Some(u) = w.unit(*id) {
                let d = u.pos.distance(*bpos);
                if d < 25.0 && best.is_none_or(|(bd, _)| d < bd) {
                    best = Some((d, *id));
                }
            }
        }
        if let Some((_, id)) = best {
            used.push(id);
            w.issue(&[id], Order::Collect(*bid));
        }
    }
    let idle: Vec<UnitId> = idle.into_iter().filter(|id| !used.contains(id)).collect();

    // 5. attack with a squad when big enough or the timer expired
    bot.squad.retain(|id| w.unit(*id).is_some_and(|u| u.alive()));
    if (idle.len() as u32 >= bot.squad_size || (bot.attack_timer <= 0.0 && idle.len() >= 3)) && bot.squad.is_empty() {
        let home = colony_ids.first().map(|c| w.colonies[*c as usize].pos).or_else(|| w.unit(idle[0]).map(|u| u.pos)).unwrap_or(Vec2::ZERO);
        // prefer a defeated colony (free capture), then the nearest enemy colony, else enemy units
        let goal = w
            .colonies
            .iter()
            .filter(|c| !c.active())
            .map(|c| c.pos)
            .min_by(|a, b| a.distance(home).total_cmp(&b.distance(home)))
            .or_else(|| w.nearest_enemy_colony(team, home).map(|c| c.pos))
            .or_else(|| w.nearest_enemy_unit(team, home, 1000.0).map(|u| u.pos));
        if let Some(goal) = goal {
            w.issue(&idle, Order::AttackMove(goal));
            bot.squad = idle.clone();
            bot.squad_goal = Some(goal);
            bot.attack_timer = bot.attack_interval;
        }
    } else if !bot.squad.is_empty() {
        // squad finished its attack-move? re-target the nearest enemy from its centroid
        let members: Vec<&crate::world::Unit> = bot.squad.iter().filter_map(|id| w.unit(*id)).collect();
        let all_idle = members.iter().all(|u| matches!(u.order, Order::Idle) && u.target.is_none());
        if all_idle && !members.is_empty() {
            let centroid = members.iter().map(|u| u.pos).fold(Vec2::ZERO, |a, b| a + b) / members.len() as f32;
            let next = w
                .colonies
                .iter()
                .filter(|c| c.team != team)
                .map(|c| c.pos)
                .min_by(|a, b| a.distance(centroid).total_cmp(&b.distance(centroid)))
                .or_else(|| w.nearest_enemy_unit(team, centroid, 1000.0).map(|u| u.pos));
            match next {
                Some(goal) if goal.distance(centroid) > 4.0 => {
                    let ids = bot.squad.clone();
                    w.issue(&ids, Order::AttackMove(goal));
                    bot.squad_goal = Some(goal);
                }
                _ => {
                    bot.squad.clear();
                    bot.squad_goal = None;
                }
            }
        }
    }
}
