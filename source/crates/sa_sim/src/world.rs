//! The simulation world: entities, orders and the per-tick update.

use std::f32::consts::{PI, TAU};

use glam::{IVec2, Vec2};
use rand::{Rng, SeedableRng};
use rand_chacha::ChaCha8Rng;
use serde::{Deserialize, Serialize};

/// Deterministic RNG whose state serialises as (seed, stream position) – RON has no u128 support,
/// so the ChaCha word position is split into two u64 halves.
#[derive(Clone, Debug)]
pub struct SimRng(pub ChaCha8Rng);

impl SimRng {
    pub fn seed_from_u64(seed: u64) -> Self {
        SimRng(ChaCha8Rng::seed_from_u64(seed))
    }
}

impl std::ops::Deref for SimRng {
    type Target = ChaCha8Rng;
    fn deref(&self) -> &ChaCha8Rng {
        &self.0
    }
}

impl std::ops::DerefMut for SimRng {
    fn deref_mut(&mut self) -> &mut ChaCha8Rng {
        &mut self.0
    }
}

#[derive(Serialize, Deserialize)]
struct RngState {
    seed: [u8; 32],
    pos_hi: u64,
    pos_lo: u64,
}

impl Serialize for SimRng {
    fn serialize<S: serde::Serializer>(&self, s: S) -> Result<S::Ok, S::Error> {
        let pos = self.0.get_word_pos();
        RngState { seed: self.0.get_seed(), pos_hi: (pos >> 64) as u64, pos_lo: pos as u64 }.serialize(s)
    }
}

impl<'de> Deserialize<'de> for SimRng {
    fn deserialize<D: serde::Deserializer<'de>>(d: D) -> Result<Self, D::Error> {
        let st = RngState::deserialize(d)?;
        let mut rng = ChaCha8Rng::from_seed(st.seed);
        rng.set_word_pos(((st.pos_hi as u128) << 64) | st.pos_lo as u128);
        Ok(SimRng(rng))
    }
}

use crate::ai::BotState;
use crate::data::*;
use crate::events::SimEvent;
use crate::grid::NavGrid;
use crate::spatial::SpatialHash;
use crate::{angle_diff, dir_to_heading, heading_to_dir, turn_towards};

// ---------------------------------------------------------------------------------------------
// identifiers
// ---------------------------------------------------------------------------------------------

/// Generational unit id (stable even after the slot is reused).
#[derive(Serialize, Deserialize, Clone, Copy, Debug, PartialEq, Eq, Hash, PartialOrd, Ord)]
pub struct UnitId {
    pub idx: u32,
    pub generation: u32,
}

#[derive(Serialize, Deserialize, Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub enum Target {
    Unit(UnitId),
    Colony(u32),
}

#[derive(Serialize, Deserialize, Clone, Copy, Debug, PartialEq)]
pub enum Order {
    Idle,
    Stop,
    Move(Vec2),
    AttackMove(Vec2),
    Attack(Target),
    /// Walk to a colony bit and pick it up.
    Collect(u32),
}

#[derive(Serialize, Deserialize, Clone, Copy, Debug, PartialEq, Eq)]
pub enum UnitState {
    Alive,
    Dying,
    Corpse,
}

#[derive(Serialize, Deserialize, Clone, Copy, Debug, PartialEq, Eq)]
pub enum Anim {
    Idle,
    Move,
    Attack,
    Death,
}

#[derive(Serialize, Deserialize, Clone, Debug)]
pub struct Unit {
    pub id: UnitId,
    pub kind: u16,
    pub team: u8,
    pub pos: Vec2,
    pub prev_pos: Vec2,
    pub heading: f32,
    pub prev_heading: f32,
    pub vel: Vec2,
    pub hp: f32,
    pub state: UnitState,
    pub order: Order,
    /// Order to resume after the current engagement (attack-move destination etc.).
    pub resume: Order,
    pub target: Option<Target>,
    /// Waypoints in travel order; `path_next` indexes the next one.
    pub path: Vec<Vec2>,
    pub path_next: usize,
    pub path_goal: Option<Vec2>,
    pub replan_timer: f32,
    pub stuck_timer: f32,
    pub progress_pos: Vec2,
    pub reload: f32,
    /// Seconds since the current attack animation started (None = not attacking).
    pub attack_timer: Option<f32>,
    pub shot_released: bool,
    pub attack_seq: u32,
    pub anim: Anim,
    pub paralyzed: f32,
    pub idle_time: f32,
    pub scan_timer: f32,
    pub death_timer: f32,
    pub altitude: f32,
    /// Flying creeps only: fixed cross-map heading.
    pub cruise: Option<Vec2>,
    pub wander_timer: f32,
    /// True when `target` was acquired by scanning rather than by an explicit Attack order.
    pub auto_target: bool,
    /// Where the unit was when it auto-acquired its target (chase leash anchor).
    pub leash: Vec2,
    /// Seconds the current auto target has been out of range / unreachable.
    pub chase_timer: f32,
    /// Plants: seconds since the plant sprouted (it can attack once this reaches its grow time).
    #[serde(default)]
    pub age: f32,
    /// Flyers: seconds into the drop/rest rhythm.
    #[serde(default)]
    pub phase: f32,
    /// Choc Freckle: angle (radians) of its spinning spray.
    #[serde(default)]
    pub spin: f32,
    /// Flyers: drops made so far (picks the next aim point).
    #[serde(default)]
    pub drops: u32,
    /// Flyers: drops left in the current burst.
    #[serde(default)]
    pub burst_left: u32,
}

impl Unit {
    pub fn alive(&self) -> bool {
        self.state == UnitState::Alive
    }
}

#[derive(Serialize, Deserialize, Clone, Debug, PartialEq)]
pub enum ColonyState {
    Active,
    /// Defeated/unclaimed: waits, scatters bits, then resolves ownership.
    Defeated { timer: f32, launched: bool, resolved: u32, picks: Vec<u32> },
}

#[derive(Serialize, Deserialize, Clone, Debug)]
pub struct TurretState {
    pub yaw: f32,
    pub target: Option<UnitId>,
    pub reload: f32,
    pub fire_seq: u32,
}

#[derive(Serialize, Deserialize, Clone, Debug, Default)]
pub struct Production {
    pub kind: Option<u16>,
    pub progress: f32,
}

#[derive(Serialize, Deserialize, Clone, Debug)]
pub struct Colony {
    pub id: u32,
    pub def: u16,
    /// 0 = neutral (either a defeated colony or a neutral-owned live colony).
    pub team: u8,
    pub pos: Vec2,
    pub hp: f32,
    pub state: ColonyState,
    pub turrets: Vec<TurretState>,
    pub production: Production,
    pub rally: Vec2,
    pub units_bred: u32,
}

impl Colony {
    pub fn active(&self) -> bool {
        matches!(self.state, ColonyState::Active)
    }
}

#[derive(Serialize, Deserialize, Clone, Debug)]
pub struct Bit {
    pub id: u32,
    pub colony: u32,
    pub start: Vec2,
    pub end: Vec2,
    pub t: f32,
    pub flight: f32,
    pub lifetime: f32,
    pub alive: bool,
    pub claimed: bool,
}

impl Bit {
    pub fn landed(&self) -> bool {
        self.t >= self.flight
    }

    /// Current position and height (arc while flying).
    pub fn pos_height(&self) -> (Vec2, f32) {
        let f = (self.t / self.flight).clamp(0.0, 1.0);
        let p = self.start.lerp(self.end, f);
        let h = (PI * f).sin() * (self.start.distance(self.end) * 0.35).max(0.4);
        (p, if self.landed() { 0.0 } else { h })
    }
}

#[derive(Serialize, Deserialize, Clone, Debug)]
pub struct Projectile {
    pub id: u32,
    pub weapon: u16,
    pub team: u8,
    pub source: Option<UnitId>,
    pub kind: ProjectileKind,
    pub pos: Vec2,
    pub height: f32,
    pub start: Vec2,
    pub start_height: f32,
    pub aim: Vec2,
    pub target: Option<Target>,
    pub t: f32,
    pub flight: f32,
    pub speed: f32,
    pub heading: f32,
    pub alive: bool,
    pub bounces_left: u32,
    pub hop_len: f32,
}

#[derive(Serialize, Deserialize, Clone, Debug)]
pub struct TeamState {
    pub def: TeamDef,
    pub defeated: bool,
    pub bot: Option<BotState>,
    pub units_alive: u32,
    pub colonies: u32,
    pub kills: u32,
    pub losses: u32,
    /// Colonies this team has taken over (the original game menu's "Colony Takeovers").
    #[serde(default)]
    pub takeovers: u32,
}

/// Snapshot of what one team can see (everything; no fog of war in this recreation).
#[derive(Serialize, Deserialize, Clone, Debug, Default)]
pub struct Stats {
    pub ticks: u64,
    pub units_spawned: u32,
    pub units_killed: u32,
    pub shots: u32,
    pub captures: u32,
}

#[derive(Serialize, Deserialize, Clone, Debug)]
pub struct World {
    pub defs: Defs,
    pub map: MapDef,
    pub grid: NavGrid,
    pub tick: u64,
    pub time: f64,
    pub dt: f32,
    pub units: Vec<Option<Unit>>,
    free_units: Vec<u32>,
    generations: Vec<u32>,
    pub colonies: Vec<Colony>,
    pub projectiles: Vec<Projectile>,
    pub bits: Vec<Bit>,
    pub teams: Vec<TeamState>,
    pub rng: SimRng,
    pub events: Vec<SimEvent>,
    pub winner: Option<u8>,
    pub game_over: bool,
    pub stats: Stats,
    next_projectile: u32,
    next_bit: u32,
    victory_timer: f32,
    flyer_timer: f32,
    pirate_timer: f32,
    /// Countdown per `map.rules.creeps` pool (empty until the first tick).
    #[serde(default)]
    creep_timers: Vec<f32>,
    /// Units that died this tick (death weapons and death spawns still to run).
    #[serde(skip)]
    died: Vec<UnitId>,
    #[serde(skip)]
    spatial: SpatialHash,
    #[serde(skip)]
    scratch: Vec<u32>,
    /// Cheat switches (console).
    #[serde(default)]
    pub cheats: Cheats,
}

/// Cheat switches set from the in-game console; saved with the game.
#[derive(Serialize, Deserialize, Clone, Debug, Default)]
#[serde(default)]
pub struct Cheats {
    /// Units and colonies of this team take no damage.
    pub invincible: Option<u8>,
    /// (team, factor): breeding runs `factor` times faster for that team.
    pub fast_breed: Option<(u8, f32)>,
    /// Ignore the unit cap.
    pub no_cap: bool,
}

/// Why a damage was dealt (for stats and friendly-fire rules).
#[derive(Clone, Copy, Debug)]
struct Hit {
    pos: Vec2,
    weapon: u16,
    team: u8,
    source: Option<UnitId>,
    direct: Option<Target>,
}

impl World {
    // -----------------------------------------------------------------------------------------
    // construction
    // -----------------------------------------------------------------------------------------
    pub fn new(defs: Defs, map: MapDef) -> Result<Self, DataError> {
        let mut grid = NavGrid::new(map.width, map.height);
        if let Some(cells) = &map.cells {
            grid.set_cells(cells).map_err(DataError::Missing)?;
        }
        for t in &map.terrain {
            grid.paint_terrain(t.center, t.radius, t.kind);
        }
        for o in &map.obstacles {
            if o.blocking {
                grid.block_circle(o.pos, o.radius * o.scale);
            }
        }
        let dt = 1.0 / defs.rules.tick_hz;
        let mut teams: Vec<TeamState> = Vec::new();
        // team 0 is always the neutral "creeps" team
        teams.push(TeamState {
            def: TeamDef { id: 0, name: "Neutral".into(), color: "X".into(), controller: Controller::None, bot_profile: String::new() },
            defeated: false,
            bot: None,
            units_alive: 0,
            colonies: 0,
            kills: 0,
            losses: 0,
            takeovers: 0,
        });
        let mut team_defs = map.teams.clone();
        team_defs.sort_by_key(|t| t.id);
        for td in team_defs {
            if td.id == 0 {
                continue;
            }
            while teams.len() < td.id as usize {
                teams.push(TeamState {
                    def: TeamDef { id: teams.len() as u8, name: format!("Team {}", teams.len()), color: "X".into(), controller: Controller::None, bot_profile: String::new() },
                    defeated: true,
                    bot: None,
                    units_alive: 0,
                    colonies: 0,
                    kills: 0,
                    losses: 0,
                    takeovers: 0,
                });
            }
            let bot = if td.controller == Controller::Bot { Some(BotState::new(&td.bot_profile)) } else { None };
            teams.push(TeamState { def: td, defeated: false, bot, units_alive: 0, colonies: 0, kills: 0, losses: 0, takeovers: 0 });
        }
        let mut w = World {
            grid,
            tick: 0,
            time: 0.0,
            dt,
            units: Vec::new(),
            free_units: Vec::new(),
            generations: Vec::new(),
            colonies: Vec::new(),
            projectiles: Vec::new(),
            bits: Vec::new(),
            teams,
            rng: SimRng::seed_from_u64(map.seed),
            events: Vec::new(),
            winner: None,
            game_over: false,
            stats: Stats::default(),
            next_projectile: 1,
            next_bit: 1,
            victory_timer: 0.0,
            flyer_timer: 0.0,
            pirate_timer: 0.0,
            creep_timers: Vec::new(),
            died: Vec::new(),
            spatial: SpatialHash::new(2.0),
            scratch: Vec::new(),
            defs,
            map,
            cheats: Cheats::default(),
        };
        let colonies = w.map.colonies.clone();
        for cs in &colonies {
            let def = w.defs.colony(&cs.colony).ok_or_else(|| DataError::Missing(format!("colony '{}'", cs.colony)))?;
            let produce = match &cs.produce {
                Some(p) => Some(w.defs.unit(p).ok_or_else(|| DataError::Missing(format!("unit '{p}'")))?),
                None => w.defs.colonies[def as usize].produces.first().and_then(|p| w.defs.unit(p)),
            };
            let id = w.spawn_colony(def, cs.team, cs.pos, produce);
            if cs.defeated {
                w.colonies[id as usize].hp = 0.0;
                w.defeat_colony(id);
            }
        }
        let spawns = w.map.units.clone();
        for us in &spawns {
            let kind = w.defs.unit(&us.unit).ok_or_else(|| DataError::Missing(format!("unit '{}'", us.unit)))?;
            for i in 0..us.count {
                let ang = i as f32 * 2.399963; // golden angle spiral
                let r = us.spread * (i as f32 / us.count.max(1) as f32).sqrt();
                let p = us.pos + Vec2::new(ang.cos(), ang.sin()) * r;
                w.spawn_unit(kind, us.team, p, 0.0);
            }
        }
        w.events.clear();
        Ok(w)
    }

    pub fn unit_cap(&self) -> u32 {
        if self.cheats.no_cap {
            return u32::MAX;
        }
        self.map.rules.unit_cap.unwrap_or(self.defs.rules.unit_cap)
    }

    // -----------------------------------------------------------------------------------------
    // entity access
    // -----------------------------------------------------------------------------------------
    pub fn unit(&self, id: UnitId) -> Option<&Unit> {
        self.units.get(id.idx as usize).and_then(|s| s.as_ref()).filter(|u| u.id == id)
    }

    pub fn unit_mut(&mut self, id: UnitId) -> Option<&mut Unit> {
        self.units.get_mut(id.idx as usize).and_then(|s| s.as_mut()).filter(|u| u.id == id)
    }

    pub fn units_iter(&self) -> impl Iterator<Item = &Unit> {
        self.units.iter().filter_map(|s| s.as_ref())
    }

    pub fn living_units(&self) -> impl Iterator<Item = &Unit> {
        self.units_iter().filter(|u| u.alive())
    }

    pub fn unit_def(&self, u: &Unit) -> &UnitDef {
        &self.defs.units[u.kind as usize]
    }

    pub fn colony_def(&self, c: &Colony) -> &ColonyDef {
        &self.defs.colonies[c.def as usize]
    }

    pub fn team_count(&self, team: u8) -> u32 {
        self.living_units().filter(|u| u.team == team).count() as u32
    }

    pub fn is_enemy(&self, a: u8, b: u8) -> bool {
        a != b
    }

    pub fn bit(&self, id: u32) -> Option<&Bit> {
        self.bits.iter().find(|b| b.id == id && b.alive)
    }

    // -----------------------------------------------------------------------------------------
    // spawning
    // -----------------------------------------------------------------------------------------
    pub fn spawn_unit(&mut self, kind: u16, team: u8, pos: Vec2, heading: f32) -> UnitId {
        let def = &self.defs.units[kind as usize];
        let mut pos = if def.flying { self.grid.clamp(pos) } else { self.grid.nearest_free(pos) };
        let burst = def.flyer.as_ref().map_or(1, |f| f.burst.max(1));
        if let Some(plant) = &def.plant {
            // a plant sits in the middle of its cell and, like the original's, takes the cell up
            let cell = self.grid.cell_of(pos);
            pos = self.grid.center(cell);
            if plant.blocks {
                self.grid.set_blocked(cell, true);
            }
        }
        let (idx, generation) = match self.free_units.pop() {
            Some(i) => {
                self.generations[i as usize] += 1;
                (i, self.generations[i as usize])
            }
            None => {
                self.units.push(None);
                self.generations.push(1);
                ((self.units.len() - 1) as u32, 1)
            }
        };
        let id = UnitId { idx, generation };
        let u = Unit {
            id,
            kind,
            team,
            pos,
            prev_pos: pos,
            heading,
            prev_heading: heading,
            vel: Vec2::ZERO,
            hp: def.hp,
            state: UnitState::Alive,
            order: Order::Idle,
            resume: Order::Idle,
            target: None,
            path: Vec::new(),
            path_next: 0,
            path_goal: None,
            replan_timer: 0.0,
            stuck_timer: 0.0,
            progress_pos: pos,
            reload: 0.0,
            attack_timer: None,
            shot_released: false,
            attack_seq: 0,
            anim: Anim::Idle,
            paralyzed: 0.0,
            idle_time: 0.0,
            scan_timer: self.rng.random_range(0.0..0.25),
            death_timer: 0.0,
            altitude: def.altitude,
            cruise: None,
            wander_timer: self.rng.random_range(2.0..5.0),
            auto_target: false,
            leash: pos,
            chase_timer: 0.0,
            age: 0.0,
            phase: 0.0,
            spin: 0.0,
            drops: 0,
            burst_left: burst,
        };
        self.units[idx as usize] = Some(u);
        self.stats.units_spawned += 1;
        self.events.push(SimEvent::UnitSpawned(id));
        id
    }

    pub fn spawn_colony(&mut self, def: u16, team: u8, pos: Vec2, produce: Option<u16>) -> u32 {
        let d = self.defs.colonies[def as usize].clone();
        self.grid.block_square(pos, d.half_extent, d.corner_cut);
        let id = self.colonies.len() as u32;
        let turrets = d.turrets.iter().map(|_| TurretState { yaw: 0.0, target: None, reload: 0.0, fire_seq: 0 }).collect();
        self.colonies.push(Colony {
            id,
            def,
            team,
            pos,
            hp: d.hp,
            state: ColonyState::Active,
            turrets,
            production: Production { kind: produce, progress: 0.0 },
            rally: pos + d.rally_offset,
            units_bred: 0,
        });
        id
    }

    fn remove_unit(&mut self, id: UnitId) {
        if let Some(slot) = self.units.get_mut(id.idx as usize)
            && slot.as_ref().is_some_and(|u| u.id == id)
        {
            *slot = None;
            self.free_units.push(id.idx);
            self.events.push(SimEvent::UnitRemoved(id));
        }
    }

    // -----------------------------------------------------------------------------------------
    // orders
    // -----------------------------------------------------------------------------------------
    /// Issue an order to a set of units (ignored for dead/uncontrollable units).
    pub fn issue(&mut self, ids: &[UnitId], order: Order) {
        let n = ids.len().max(1) as f32;
        for (i, id) in ids.iter().enumerate() {
            let Some(u) = self.unit(*id) else { continue };
            if !u.alive() || !self.defs.units[u.kind as usize].controllable {
                continue;
            }
            // spread group destinations so units do not pile onto one point
            let order = match order {
                Order::Move(p) | Order::AttackMove(p) if ids.len() > 1 => {
                    let k = i as f32;
                    let ang = k * 2.399963;
                    let r = 0.55 * (k / n * ids.len() as f32).sqrt();
                    let q = p + Vec2::new(ang.cos(), ang.sin()) * r;
                    if matches!(order, Order::Move(_)) { Order::Move(q) } else { Order::AttackMove(q) }
                }
                o => o,
            };
            self.apply_order(*id, order);
        }
    }

    fn apply_order(&mut self, id: UnitId, order: Order) {
        let Some(u) = self.unit_mut(id) else { return };
        u.path.clear();
        u.path_next = 0;
        u.path_goal = None;
        u.replan_timer = 0.0;
        u.stuck_timer = 0.0;
        u.idle_time = 0.0;
        match order {
            Order::Stop | Order::Idle => {
                u.order = Order::Idle;
                u.resume = Order::Idle;
                u.target = None;
                u.attack_timer = None;
            }
            Order::Move(_) => {
                u.order = order;
                u.resume = Order::Idle;
                u.target = None;
                u.attack_timer = None;
            }
            Order::AttackMove(_) => {
                u.order = order;
                u.resume = order;
                u.target = None;
                u.attack_timer = None;
            }
            Order::Attack(t) => {
                u.order = order;
                u.resume = Order::Idle;
                u.target = Some(t);
                u.auto_target = false;
                u.chase_timer = 0.0;
                u.attack_timer = None;
            }
            Order::Collect(_) => {
                u.order = order;
                u.resume = Order::Idle;
                u.target = None;
                u.attack_timer = None;
            }
        }
    }

    /// Choose what a colony breeds (None = stop breeding).
    pub fn set_production(&mut self, colony: u32, kind: Option<u16>) {
        if let Some(c) = self.colonies.get_mut(colony as usize) {
            if c.production.kind != kind {
                c.production.progress = 0.0;
            }
            c.production.kind = kind;
        }
    }

    pub fn set_rally(&mut self, colony: u32, p: Vec2) {
        if let Some(c) = self.colonies.get_mut(colony as usize) {
            c.rally = self.grid.clamp(p);
        }
    }

    // -----------------------------------------------------------------------------------------
    // main update
    // -----------------------------------------------------------------------------------------
    pub fn step(&mut self) {
        let dt = self.dt;
        self.tick += 1;
        self.time += dt as f64;
        self.stats.ticks = self.tick;
        self.rebuild_spatial();
        for u in self.units.iter_mut().flatten() {
            u.prev_pos = u.pos;
            u.prev_heading = u.heading;
        }
        if !self.game_over {
            if self.time >= self.map.rules.bot_delay as f64 {
                crate::ai::run_bots(self, dt);
            }
        }
        self.update_units(dt);
        self.update_plants(dt);
        self.update_colonies(dt);
        self.update_projectiles(dt);
        self.update_bits(dt);
        self.update_creeps(dt);
        self.process_deaths();
        self.cleanup_units(dt);
        self.victory_timer += dt;
        if self.victory_timer >= 0.5 {
            self.victory_timer = 0.0;
            self.check_victory();
        }
    }

    /// Advance several ticks (helper for tests/benchmarks).
    pub fn run(&mut self, ticks: u32) {
        for _ in 0..ticks {
            self.step();
            self.events.clear();
        }
    }

    pub fn drain_events(&mut self) -> Vec<SimEvent> {
        std::mem::take(&mut self.events)
    }

    fn rebuild_spatial(&mut self) {
        self.spatial.clear();
        for u in self.units.iter().flatten() {
            if u.alive() {
                self.spatial.insert(u.pos, u.id.idx);
            }
        }
    }

    // -----------------------------------------------------------------------------------------
    // targeting helpers
    // -----------------------------------------------------------------------------------------
    fn weapon_of(&self, u: &Unit) -> Option<u16> {
        self.defs.units[u.kind as usize].weapon.as_ref().and_then(|w| self.defs.weapon(w))
    }

    fn can_target_unit(&self, w: &WeaponDef, team: u8, t: &Unit) -> bool {
        if !t.alive() || t.team == team {
            return false;
        }
        let tdef = &self.defs.units[t.kind as usize];
        if tdef.air && !w.targets.air {
            return false;
        }
        if !tdef.air && !w.targets.ground {
            return false;
        }
        // seeds cannot be hit; paralysis arrows never target plants (OpenSA InvalidTargets: Plant)
        if let Some(p) = &tdef.plant
            && (!p.targetable || w.paralyze.is_some())
        {
            return false;
        }
        // paralysis arrows do not re-target paralysed units
        if w.paralyze.is_some() && t.paralyzed > 0.0 {
            return false;
        }
        true
    }

    fn can_target_colony(&self, w: &WeaponDef, team: u8, c: &Colony) -> bool {
        if !c.active() || c.team == team {
            return false;
        }
        w.targets.colony || self.map.rules.melee_can_damage_colonies
    }

    pub fn target_pos(&self, t: Target) -> Option<Vec2> {
        match t {
            Target::Unit(id) => self.unit(id).filter(|u| u.alive()).map(|u| u.pos),
            Target::Colony(c) => self.colonies.get(c as usize).map(|c| c.pos),
        }
    }

    fn target_radius(&self, t: Target) -> f32 {
        match t {
            Target::Unit(id) => self.unit(id).map(|u| self.defs.units[u.kind as usize].radius).unwrap_or(0.3),
            Target::Colony(c) => self.colonies.get(c as usize).map(|c| self.defs.colonies[c.def as usize].half_extent).unwrap_or(3.0),
        }
    }

    fn target_valid(&self, w: &WeaponDef, team: u8, t: Target) -> bool {
        match t {
            Target::Unit(id) => self.unit(id).is_some_and(|u| self.can_target_unit(w, team, u)),
            Target::Colony(c) => self.colonies.get(c as usize).is_some_and(|c| self.can_target_colony(w, team, c)),
        }
    }

    /// Nearest valid enemy (unit or colony) within `range` of `pos` for a weapon.
    fn find_target(&mut self, pos: Vec2, team: u8, w: &WeaponDef, range: f32) -> Option<Target> {
        let mut best: Option<(f32, Target)> = None;
        self.scratch.clear();
        let mut scratch = std::mem::take(&mut self.scratch);
        self.spatial.query(pos, range, &mut scratch);
        for idx in scratch.iter() {
            if let Some(u) = self.units[*idx as usize].as_ref()
                && self.can_target_unit(w, team, u)
            {
                let d = u.pos.distance(pos) - self.defs.units[u.kind as usize].radius;
                if d <= range && best.is_none_or(|(bd, _)| d < bd) {
                    best = Some((d, Target::Unit(u.id)));
                }
            }
        }
        scratch.clear();
        self.scratch = scratch;
        // colonies are lower priority than units (OpenSA AutoTargetPriority lists units first)
        if best.is_none() {
            for c in &self.colonies {
                if self.can_target_colony(w, team, c) {
                    let d = c.pos.distance(pos) - self.defs.colonies[c.def as usize].half_extent;
                    if d <= range && best.is_none_or(|(bd, _)| d < bd) {
                        best = Some((d, Target::Colony(c.id)));
                    }
                }
            }
        }
        best.map(|(_, t)| t)
    }

    /// Point to test line of sight against: a plant fills its own (blocked) cell, so a shooter only
    /// needs to see the near edge of that cell.
    fn sight_point(&self, from: Vec2, t: Target, tp: Vec2) -> Vec2 {
        match t {
            Target::Unit(id) if self.unit(id).is_some_and(|u| self.defs.units[u.kind as usize].plant.as_ref().is_some_and(|p| p.blocks)) => tp - (tp - from).normalize_or_zero() * 0.75,
            _ => tp,
        }
    }

    /// Distance from `pos` to the edge of a target.
    fn edge_distance(&self, pos: Vec2, t: Target) -> f32 {
        match t {
            Target::Unit(id) => self.unit(id).map(|u| u.pos.distance(pos) - self.defs.units[u.kind as usize].radius).unwrap_or(f32::INFINITY),
            Target::Colony(c) => self.colonies.get(c as usize).map(|c| {
                let h = self.defs.colonies[c.def as usize].half_extent;
                let d = (pos - c.pos).abs() - Vec2::splat(h);
                d.max(Vec2::ZERO).length()
            }).unwrap_or(f32::INFINITY),
        }
    }

    // -----------------------------------------------------------------------------------------
    // units
    // -----------------------------------------------------------------------------------------
    fn update_units(&mut self, dt: f32) {
        let n = self.units.len();
        let mut hits: Vec<Hit> = Vec::new();
        let mut spawned_projectiles: Vec<Projectile> = Vec::new();
        for i in 0..n {
            let Some(u0) = self.units[i].as_ref() else { continue };
            if !u0.alive() || self.defs.units[u0.kind as usize].plant.is_some() {
                continue; // plants have their own update
            }
            let id = u0.id;
            let team = u0.team;
            let def = self.defs.units[u0.kind as usize].clone();
            let weapon_idx = self.weapon_of(u0);
            let weapon = weapon_idx.map(|w| self.defs.weapons[w as usize].clone());

            // --- timers
            {
                let u = self.units[i].as_mut().unwrap();
                u.reload = (u.reload - dt).max(0.0);
                u.scan_timer -= dt;
                u.replan_timer -= dt;
                if u.paralyzed > 0.0 {
                    u.paralyzed = (u.paralyzed - dt).max(0.0);
                    u.vel = Vec2::ZERO;
                    u.anim = Anim::Idle;
                    continue;
                }
            }

            // --- validate current target
            let mut target = self.units[i].as_ref().unwrap().target;
            if let (Some(t), Some(w)) = (target, &weapon)
                && !self.target_valid(w, team, t)
            {
                target = None;
                let u = self.units[i].as_mut().unwrap();
                u.target = None;
                u.attack_timer = None;
                if matches!(u.order, Order::Attack(_)) {
                    u.order = u.resume;
                    u.path.clear();
                    u.path_goal = None;
                }
            }

            // --- auto-targeting (idle, attack-move or aggressive stance)
            let order = self.units[i].as_ref().unwrap().order;
            let scan = self.units[i].as_ref().unwrap().scan_timer <= 0.0;
            if target.is_none()
                && scan
                && let Some(w) = &weapon
                && def.controllable
                && matches!(order, Order::Idle | Order::AttackMove(_) | Order::Collect(_))
            {
                let pos = self.units[i].as_ref().unwrap().pos;
                let range = if matches!(order, Order::Idle | Order::Collect(_)) && !def.aggressive { w.range.max(def.scan_range * 0.5) } else { def.scan_range.max(w.range) };
                if let Some(t) = self.find_target(pos, team, w, range) {
                    target = Some(t);
                    let u = self.units[i].as_mut().unwrap();
                    u.target = Some(t);
                    u.auto_target = true;
                    u.leash = u.pos;
                    u.chase_timer = 0.0;
                    u.path.clear();
                    u.path_goal = None;
                }
            }
            if scan {
                self.units[i].as_mut().unwrap().scan_timer = self.defs.rules.auto_target_interval;
            }

            // --- collect bits when idle
            if target.is_none() && matches!(order, Order::Idle) {
                let u = self.units[i].as_ref().unwrap();
                u_idle_bit_search(self, i, u.pos, dt);
            }

            // --- decide desired movement
            let u = self.units[i].as_ref().unwrap();
            let pos = u.pos;
            let mut desired_dir = Vec2::ZERO;
            let mut want_move = false;
            let mut arrived = false;
            let mut attack_now = false;
            let order = u.order;
            let mut goal: Option<Vec2> = None;
            if let (Some(t), Some(w)) = (target, &weapon) {
                let tp = self.target_pos(t).unwrap_or(pos);
                let dist = self.edge_distance(pos, t);
                let in_range = dist <= w.range && dist >= w.min_range;
                let visible = def.flying || self.grid.los(pos, self.sight_point(pos, t, tp)) || matches!(t, Target::Colony(_)) && dist < 2.0;
                if in_range && (visible || matches!(w.projectile, ProjectileKind::Bullet { arc, .. } if arc > 0.05)) {
                    attack_now = true;
                    self.units[i].as_mut().unwrap().chase_timer = 0.0;
                } else {
                    // Chase rules for auto-acquired targets (not explicit Attack orders):
                    //  * stand-ground units (aggressive = false) and anyone shooting at an air target
                    //    never chase; they drop the target after a short while out of range
                    //  * aggressive units chase, but only within 1.5x scan range of the point where
                    //    they spotted the target (leash), then give up and walk back
                    let target_is_air = matches!(t, Target::Unit(id) if self.unit(id).is_some_and(|o| self.defs.units[o.kind as usize].air));
                    let u = self.units[i].as_mut().unwrap();
                    let attack_moving = matches!(u.order, Order::AttackMove(_));
                    if u.auto_target && (!def.aggressive && !attack_moving || target_is_air) {
                        u.chase_timer += dt;
                        if u.chase_timer > 1.5 {
                            u.target = None;
                            u.chase_timer = 0.0;
                        }
                        goal = match u.order {
                            Order::Move(p) | Order::AttackMove(p) => Some(p),
                            _ => None,
                        };
                    } else if u.auto_target && !attack_moving && u.pos.distance(u.leash) > def.scan_range * 1.5 {
                        u.target = None;
                        let back = u.leash;
                        u.order = Order::Move(back);
                        goal = Some(back);
                    } else {
                        goal = Some(tp);
                    }
                }
            } else {
                match order {
                    Order::Move(p) | Order::AttackMove(p) => goal = Some(p),
                    Order::Collect(b) => {
                        if let Some(bit) = self.bit(b).filter(|b| b.landed()) {
                            goal = Some(bit.end);
                        } else {
                            let u = self.units[i].as_mut().unwrap();
                            u.order = Order::Idle;
                        }
                    }
                    _ => {}
                }
            }

            if let Some(g) = goal {
                let (dir, done) = self.steer_along_path(i, g, &def, dt);
                desired_dir = dir;
                want_move = !done;
                arrived = done;
            }

            // --- apply attack timing
            let u = self.units[i].as_mut().unwrap();
            if attack_now {
                let w = weapon.as_ref().unwrap();
                let tp = self.target_pos(target.unwrap()).unwrap_or(pos);
                let th = dir_to_heading(tp - pos);
                let u = self.units[i].as_mut().unwrap();
                u.heading = turn_towards(u.heading, th, def.turn_rate.to_radians() * dt);
                u.vel = Vec2::ZERO;
                u.path.clear();
                u.path_goal = None;
                let facing_ok = angle_diff(u.heading, th).abs() < 0.35;
                match u.attack_timer {
                    None => {
                        if u.reload <= 0.0 && facing_ok {
                            u.attack_timer = Some(0.0);
                            u.shot_released = false;
                            u.attack_seq = u.attack_seq.wrapping_add(1);
                            u.anim = Anim::Attack;
                            self.events.push(SimEvent::AttackStarted { unit: id, target: target.unwrap(), seq: u.attack_seq });
                        } else {
                            u.anim = Anim::Idle;
                        }
                    }
                    Some(t) => {
                        let t = t + dt;
                        u.attack_timer = Some(t);
                        u.anim = Anim::Attack;
                        if !u.shot_released && t >= w.fire_delay {
                            u.shot_released = true;
                            u.reload = w.reload;
                            let team = u.team;
                            let (fire_pos, fire_h) = (u.pos + heading_to_dir(u.heading) * def.radius * 0.8, def.altitude + 0.35);
                            self.fire_weapon(weapon_idx.unwrap(), team, Some(id), fire_pos, fire_h, target.unwrap(), &mut hits, &mut spawned_projectiles);
                        }
                        if t >= def.attack_anim_time.max(w.fire_delay + 0.05) {
                            let u = self.units[i].as_mut().unwrap();
                            u.attack_timer = None;
                            u.anim = Anim::Idle;
                        }
                    }
                }
                continue;
            } else if u.attack_timer.is_some() {
                u.attack_timer = None;
            }

            // --- movement integration
            if want_move {
                let speed = def.speed * if def.flying { 1.0 } else { self.grid.speed_mult(pos).max(0.25) };
                let th = dir_to_heading(desired_dir);
                let u = self.units[i].as_mut().unwrap();
                u.heading = turn_towards(u.heading, th, def.turn_rate.to_radians() * dt);
                // move along the heading but allow sideways slip so avoidance works
                let fwd = heading_to_dir(u.heading);
                let align = fwd.dot(desired_dir).max(0.0);
                let v = desired_dir * speed * (0.35 + 0.65 * align);
                u.vel = v;
                u.anim = Anim::Move;
                u.idle_time = 0.0;
            } else {
                let u = self.units[i].as_mut().unwrap();
                u.vel = Vec2::ZERO;
                u.anim = Anim::Idle;
                u.idle_time += dt;
                if arrived {
                    match u.order {
                        Order::Move(_) => u.order = Order::Idle,
                        Order::AttackMove(_) => {
                            u.order = Order::Idle;
                            u.resume = Order::Idle;
                        }
                        _ => {}
                    }
                }
            }
            // idle wander (OpenSA Wanders / TurnOnIdle): tiny random turns so armies look alive
            let u = self.units[i].as_mut().unwrap();
            if u.anim == Anim::Idle && u.target.is_none() {
                u.wander_timer -= dt;
                if u.wander_timer <= 0.0 {
                    u.wander_timer = self.rng.random_range(3.0..8.0);
                    u.heading += self.rng.random_range(-0.8..0.8);
                }
            }
        }

        // --- local avoidance + integration
        self.integrate_movement(dt);

        for h in hits {
            self.apply_hit(h);
        }
        for p in spawned_projectiles {
            self.events.push(SimEvent::ProjectileSpawned(p.id));
            self.projectiles.push(p);
        }
    }

    /// Follow/replan the path towards `goal`. Returns (desired direction, arrived).
    fn steer_along_path(&mut self, i: usize, goal: Vec2, def: &UnitDef, dt: f32) -> (Vec2, bool) {
        let rules_replan = self.defs.rules.replan_interval;
        let stuck_limit = self.defs.rules.stuck_time;
        let u = self.units[i].as_ref().unwrap();
        let pos = u.pos;
        let arrive_dist = (def.radius * 0.8).max(0.25);
        if def.flying {
            let d = goal - pos;
            if d.length() <= arrive_dist {
                return (Vec2::ZERO, true);
            }
            return (d.normalize(), false);
        }
        // re-plan when the goal moved, path is empty, or we are stuck
        let goal_moved = u.path_goal.is_none_or(|g| g.distance(goal) > 0.75);
        let need_plan = u.path_next >= u.path.len() && (goal_moved || u.replan_timer <= 0.0);
        let stuck = u.stuck_timer > stuck_limit;
        if (goal_moved && u.replan_timer <= 0.0) || need_plan || stuck {
            let path = self.grid.find_path(pos, goal);
            let u = self.units[i].as_mut().unwrap();
            u.replan_timer = rules_replan;
            u.stuck_timer = 0.0;
            u.progress_pos = pos;
            u.path_goal = Some(goal);
            match path {
                Some(p) => {
                    u.path = p;
                    u.path_next = 0;
                }
                None => {
                    u.path.clear();
                    u.path_next = 0;
                    // unreachable: give up on this goal
                    return (Vec2::ZERO, true);
                }
            }
        }
        let u = self.units[i].as_mut().unwrap();
        // progress tracking for stuck detection
        if (u.pos - u.progress_pos).length() > 0.2 {
            u.progress_pos = u.pos;
            u.stuck_timer = 0.0;
        } else {
            u.stuck_timer += dt;
        }
        while u.path_next < u.path.len() {
            let wp = u.path[u.path_next];
            let last = u.path_next + 1 == u.path.len();
            let d = wp - u.pos;
            let reach = if last { arrive_dist } else { 0.45 };
            if d.length() <= reach {
                u.path_next += 1;
                if last {
                    return (Vec2::ZERO, true);
                }
                continue;
            }
            return (d.normalize(), false);
        }
        // path consumed (or empty because goal is where we are)
        let d = goal - u.pos;
        if d.length() <= arrive_dist {
            (Vec2::ZERO, true)
        } else {
            (d.normalize_or_zero(), false)
        }
    }

    /// Separation from neighbours, wall sliding and position integration for every living unit.
    fn integrate_movement(&mut self, dt: f32) {
        let n = self.units.len();
        let sep_strength = self.defs.rules.separation_strength;
        let mut scratch = std::mem::take(&mut self.scratch);
        let mut new_pos: Vec<(usize, Vec2, Vec2)> = Vec::with_capacity(n);
        for i in 0..n {
            let Some(u) = self.units[i].as_ref() else { continue };
            if !u.alive() {
                continue;
            }
            let def = &self.defs.units[u.kind as usize];
            if def.plant.is_some() {
                continue; // rooted
            }
            let mut v = u.vel;
            // separation
            scratch.clear();
            self.spatial.query(u.pos, def.radius * 2.5 + 0.5, &mut scratch);
            let mut push = Vec2::ZERO;
            for j in scratch.iter() {
                let j = *j as usize;
                if j == i {
                    continue;
                }
                let Some(o) = self.units[j].as_ref() else { continue };
                if !o.alive() {
                    continue;
                }
                let odef = &self.defs.units[o.kind as usize];
                if odef.flying != def.flying || odef.plant.as_ref().is_some_and(|p| !p.blocks) {
                    continue;
                }
                let d = u.pos - o.pos;
                let min_d = def.radius + odef.radius;
                let dist = d.length();
                if dist < min_d && dist > 1e-4 {
                    let overlap = (min_d - dist) / min_d;
                    push += d / dist * overlap;
                } else if dist <= 1e-4 {
                    push += Vec2::new(((i as f32) * 0.7).sin(), ((i as f32) * 1.3).cos());
                }
            }
            if push != Vec2::ZERO {
                let moving = u.vel.length() > 1e-3;
                let strength = if moving { sep_strength * def.speed * 0.5 } else { sep_strength * def.speed * 0.25 };
                v += push.clamp_length_max(1.0) * strength;
                // a stationary unit being pushed should still respect its max speed
                v = v.clamp_length_max(def.speed.max(0.5) * if moving { 1.15 } else { 0.8 });
            }
            let mut p = u.pos + v * dt;
            if !def.flying {
                // wall sliding against blocked cells
                if self.grid.is_blocked_pos(p) {
                    let px = Vec2::new(p.x, u.pos.y);
                    let py = Vec2::new(u.pos.x, p.y);
                    if !self.grid.is_blocked_pos(px) {
                        p = px;
                    } else if !self.grid.is_blocked_pos(py) {
                        p = py;
                    } else {
                        p = u.pos;
                        if self.grid.is_blocked_pos(p) {
                            p = self.grid.nearest_free(p);
                        }
                    }
                }
            }
            if u.cruise.is_none() {
                p = self.grid.clamp(p); // cruising creeps may leave the map (update_creeps removes them)
            }
            new_pos.push((i, p, v));
        }
        for (i, p, v) in new_pos {
            let u = self.units[i].as_mut().unwrap();
            u.pos = p;
            u.vel = v;
        }
        scratch.clear();
        self.scratch = scratch;
    }

    // -----------------------------------------------------------------------------------------
    // weapons
    // -----------------------------------------------------------------------------------------
    #[allow(clippy::too_many_arguments)]
    fn fire_weapon(&mut self, weapon: u16, team: u8, source: Option<UnitId>, from: Vec2, from_h: f32, target: Target, hits: &mut Vec<Hit>, out: &mut Vec<Projectile>) {
        let w = self.defs.weapons[weapon as usize].clone();
        self.stats.shots += 1;
        if !w.fire_sound.is_empty() {
            self.events.push(SimEvent::Sound { id: w.fire_sound.clone(), pos: from });
        }
        let tp = self.target_pos(target).unwrap_or(from);
        for k in 0..w.volley.max(1) {
            let aim = if w.volley_spread_deg > 0.0 && w.volley > 1 {
                let ang = (k as f32 / w.volley as f32) * w.volley_spread_deg.to_radians() + self.rng.random_range(-0.2..0.2);
                let r = self.rng.random_range(0.5..w.range.max(0.6));
                from + Vec2::new(ang.cos(), ang.sin()) * r
            } else {
                self.inaccurate(&w, from, tp)
            };
            self.launch(weapon, team, source, from, from_h, aim, Some(target), None, hits, out);
        }
    }

    /// `aim` moved by the weapon's inaccuracy, which grows with the distance up to full range.
    fn inaccurate(&mut self, w: &WeaponDef, from: Vec2, aim: Vec2) -> Vec2 {
        if w.inaccuracy <= 0.0 {
            return aim;
        }
        let err = w.inaccuracy * (from.distance(aim) / w.range.max(0.1)).clamp(0.0, 1.0);
        if err <= 0.0 {
            return aim;
        }
        let a = self.rng.random_range(0.0..TAU);
        let r = self.rng.random_range(0.0..err);
        aim + Vec2::new(a.cos(), a.sin()) * r
    }

    /// One shot of `weapon` from `from` (at height `from_h`) to the ground point `aim`: an instant
    /// hit or a projectile. `target` is the victim of instant hits and what missiles home on;
    /// `heading` launches the shot that way instead of straight at the aim (Popcorn Plant whips).
    #[allow(clippy::too_many_arguments)]
    fn launch(&mut self, weapon: u16, team: u8, source: Option<UnitId>, from: Vec2, from_h: f32, aim: Vec2, target: Option<Target>, heading: Option<f32>, hits: &mut Vec<Hit>, out: &mut Vec<Projectile>) {
        let kind = self.defs.weapons[weapon as usize].projectile.clone();
        let speed = match &kind {
            ProjectileKind::Instant => {
                hits.push(Hit { pos: aim, weapon, team, source, direct: target });
                return;
            }
            ProjectileKind::Bullet { speed, .. } | ProjectileKind::Missile { speed, .. } | ProjectileKind::Bouncing { speed, .. } => *speed,
            ProjectileKind::Bomb { fall_speed } => *fall_speed,
        };
        let dist = from.distance(aim);
        let flight = match &kind {
            ProjectileKind::Bomb { fall_speed } => (from_h / fall_speed.max(0.1)).max(0.05),
            _ => (dist / speed.max(0.1)).max(0.05),
        };
        let bounces = if let ProjectileKind::Bouncing { bounces, .. } = &kind { *bounces } else { 0 };
        let id = self.next_projectile;
        self.next_projectile += 1;
        out.push(Projectile {
            id,
            weapon,
            team,
            source,
            target: if matches!(kind, ProjectileKind::Missile { .. }) { target } else { None },
            kind,
            pos: from,
            height: from_h,
            start: from,
            start_height: from_h,
            aim,
            t: 0.0,
            flight,
            speed,
            heading: heading.unwrap_or_else(|| dir_to_heading(aim - from)),
            alive: true,
            bounces_left: bounces,
            hop_len: dist,
        });
    }

    fn apply_hit(&mut self, h: Hit) {
        let fire_mult = self.team_firepower(h.team);
        let w = self.defs.weapons[h.weapon as usize].clone();
        if !w.effect.is_empty() || !w.impact_sound.is_empty() {
            self.events.push(SimEvent::Impact { pos: h.pos, effect: w.effect.clone(), sound: w.impact_sound.clone() });
        }
        if let Some(s) = &w.spawn {
            self.sprout(s, h.pos);
        }
        let melee_vs_colony = self.map.rules.melee_can_damage_colonies;
        // paralysis
        if let Some(p) = &w.paralyze {
            let mut victims = Vec::new();
            for u in self.units.iter().flatten() {
                let d = &self.defs.units[u.kind as usize];
                if u.alive() && u.team != h.team && !d.air && d.plant.is_none() && u.pos.distance(h.pos) <= p.radius + d.radius {
                    victims.push(u.id);
                }
            }
            for id in victims {
                if let Some(u) = self.unit_mut(id) {
                    u.paralyzed = p.duration;
                    u.attack_timer = None;
                    u.vel = Vec2::ZERO;
                }
                self.events.push(SimEvent::UnitParalyzed(id));
            }
        }
        if w.damage <= 0.0 {
            return;
        }
        let falloff = |d: f32| -> f32 {
            if w.spread <= 0.0 {
                return if d <= 0.0 { 1.0 } else { 0.0 };
            }
            let x = d / w.spread;
            let i = x.floor() as usize;
            if i + 1 >= w.falloff.len() {
                // the falloff list ends at the edge of the blast (OpenRA SpreadDamage range)
                let edge = (w.falloff.len().saturating_sub(1)) as f32;
                return if x <= edge { w.falloff.last().copied().unwrap_or(0.0) / 100.0 } else { 0.0 };
            }
            let f = x - i as f32;
            (w.falloff[i] * (1.0 - f) + w.falloff[i + 1] * f) / 100.0
        };
        let mut damaged: Vec<(UnitId, f32)> = Vec::new();
        if w.spread <= 0.0 {
            // single target hit
            if let Some(Target::Unit(id)) = h.direct
                && let Some(u) = self.unit(id)
                && u.alive()
            {
                damaged.push((id, w.damage * fire_mult));
            }
        } else {
            let radius = w.spread * (w.falloff.len().saturating_sub(1)) as f32;
            let mut scratch = std::mem::take(&mut self.scratch);
            scratch.clear();
            self.spatial.query(h.pos, radius + 1.0, &mut scratch);
            for idx in scratch.iter() {
                if let Some(u) = self.units[*idx as usize].as_ref()
                    && u.alive()
                {
                    let def = &self.defs.units[u.kind as usize];
                    if u.team == h.team && !w.friendly_fire {
                        continue;
                    }
                    if def.air && !w.targets.air || def.plant.as_ref().is_some_and(|p| !p.targetable) {
                        continue;
                    }
                    let d = (u.pos.distance(h.pos) - def.radius).max(0.0);
                    let f = falloff(d);
                    if f > 0.0 {
                        damaged.push((u.id, w.damage * f * fire_mult));
                    }
                }
            }
            scratch.clear();
            self.scratch = scratch;
            // a direct target always takes full damage even if the shot was slightly inaccurate
            if let Some(Target::Unit(id)) = h.direct
                && let Some(u) = self.unit(id)
                && u.alive()
                && !damaged.iter().any(|(d, _)| *d == id)
                && u.pos.distance(h.pos) <= def_radius(self, u) + w.spread * 2.0
            {
                damaged.push((id, w.damage * fire_mult));
            }
        }
        for (id, dmg) in damaged {
            self.damage_unit(id, dmg, h.team);
        }
        // colonies
        let can_hit_colony = w.targets.colony || melee_vs_colony;
        if can_hit_colony {
            let mut col_dmg: Vec<(u32, f32)> = Vec::new();
            for c in &self.colonies {
                if !c.active() || c.team == h.team {
                    continue;
                }
                let half = self.defs.colonies[c.def as usize].half_extent;
                let d = ((h.pos - c.pos).abs() - Vec2::splat(half)).max(Vec2::ZERO).length();
                let direct = matches!(h.direct, Some(Target::Colony(cid)) if cid == c.id);
                if direct {
                    col_dmg.push((c.id, w.damage * fire_mult));
                } else if w.spread > 0.0 {
                    let f = falloff(d);
                    if f > 0.0 {
                        col_dmg.push((c.id, w.damage * f * fire_mult));
                    }
                }
            }
            for (cid, dmg) in col_dmg {
                self.damage_colony(cid, dmg, h.team);
            }
        }
    }

    fn damage_unit(&mut self, id: UnitId, dmg: f32, by_team: u8) {
        if let Some(u) = self.unit(id)
            && self.cheats.invincible == Some(u.team)
        {
            return;
        }
        let Some(u) = self.unit_mut(id) else { return };
        if !u.alive() {
            return;
        }
        u.hp -= dmg;
        if u.hp <= 0.0 {
            self.kill_unit(id, Some(by_team));
        }
    }

    /// A living unit dies: death animation, statistics (`by_team` gets the kill), a plant frees
    /// its cell, and its death weapon / death spawn are queued for `process_deaths`.
    fn kill_unit(&mut self, id: UnitId, by_team: Option<u8>) {
        let Some(u) = self.unit_mut(id) else { return };
        if !u.alive() {
            return;
        }
        u.hp = 0.0;
        u.state = UnitState::Dying;
        u.anim = Anim::Death;
        u.death_timer = 0.0;
        u.vel = Vec2::ZERO;
        u.attack_timer = None;
        u.target = None;
        let (team, kind, pos) = (u.team, u.kind, u.pos);
        self.events.push(SimEvent::UnitDied(id));
        if self.defs.units[kind as usize].plant.as_ref().is_some_and(|p| p.blocks) {
            let cell = self.grid.cell_of(pos);
            self.grid.set_blocked(cell, false);
        }
        if let Some(by) = by_team {
            self.stats.units_killed += 1;
            if let Some(t) = self.teams.get_mut(team as usize) {
                t.losses += 1;
            }
            if let Some(t) = self.teams.get_mut(by as usize) {
                t.kills += 1;
            }
        }
        self.died.push(id);
    }

    /// Death weapons (a Death Lolly's blast, which can set off the next lolly) and death spawns
    /// (a withered seed becoming a Seed Ball, a Flying Machine's pilot) of this tick's dead.
    fn process_deaths(&mut self) {
        for _ in 0..8 {
            if self.died.is_empty() {
                return;
            }
            let died = std::mem::take(&mut self.died);
            let mut hits: Vec<Hit> = Vec::new();
            let mut out: Vec<Projectile> = Vec::new();
            for id in died {
                let Some(u) = self.unit(id) else { continue };
                let def = self.defs.units[u.kind as usize].clone();
                let (pos, team, heading) = (u.pos, u.team, u.heading);
                if let Some(widx) = def.death_weapon.as_ref().and_then(|w| self.defs.weapon(w)) {
                    let sound = self.defs.weapons[widx as usize].fire_sound.clone();
                    if !sound.is_empty() {
                        self.events.push(SimEvent::Sound { id: sound, pos });
                    }
                    self.launch(widx, team, Some(id), pos, 0.0, pos, None, None, &mut hits, &mut out);
                }
                if let Some(s) = &def.death_spawn
                    && self.rng.random_range(0.0..1.0) < s.chance
                    && let Some(kind) = self.defs.unit(&s.unit)
                    && self.grid.terrain_at(pos) != TerrainKind::Water
                    && self.grid.in_bounds(self.grid.cell_of(pos))
                {
                    if self.defs.units[kind as usize].plant.is_some() {
                        let h = self.rng.random_range(0.0..TAU);
                        self.spawn_unit(kind, 0, pos, h);
                    } else {
                        // a downed pilot carries on like a pirate
                        let nid = self.spawn_unit(kind, team, pos, heading);
                        if let Some(c) = self.colonies.iter().filter(|c| c.team != 0 && c.active()).min_by(|a, b| a.pos.distance(pos).total_cmp(&b.pos.distance(pos))) {
                            let target = c.pos;
                            self.issue_uncontrolled(nid, Order::AttackMove(target));
                        }
                    }
                }
            }
            for h in hits {
                self.apply_hit(h);
            }
            for p in out {
                self.events.push(SimEvent::ProjectileSpawned(p.id));
                self.projectiles.push(p);
            }
        }
    }

    /// A seed lands: it takes root if its cell is free open ground (OpenSA SpawnActor warhead).
    fn sprout(&mut self, unit: &str, pos: Vec2) {
        let Some(kind) = self.defs.unit(unit) else { return };
        let cell = self.grid.cell_of(pos);
        if !self.grid.in_bounds(cell) || self.grid.is_blocked(cell) {
            return;
        }
        let at = self.grid.center(cell);
        if self.living_units().any(|u| u.pos.distance(at) < 0.75 && !self.defs.units[u.kind as usize].flying) {
            return;
        }
        let heading = self.rng.random_range(0.0..TAU);
        self.spawn_unit(kind, 0, at, heading);
    }

    fn damage_colony(&mut self, cid: u32, dmg: f32, _by_team: u8) {
        if let Some(c) = self.colonies.get(cid as usize)
            && c.team != 0
            && self.cheats.invincible == Some(c.team)
        {
            return;
        }
        let Some(c) = self.colonies.get_mut(cid as usize) else { return };
        if !c.active() {
            return;
        }
        c.hp -= dmg;
        if c.hp <= 0.0 {
            c.hp = 0.0;
            self.defeat_colony(cid);
        }
    }

    fn defeat_colony(&mut self, cid: u32) {
        let n_teams = self.teams.len();
        let c = &mut self.colonies[cid as usize];
        c.team = 0;
        c.state = ColonyState::Defeated { timer: 0.0, launched: false, resolved: 0, picks: vec![0; n_teams] };
        c.production.progress = 0.0;
        for t in &mut c.turrets {
            t.target = None;
        }
        self.events.push(SimEvent::ColonyDefeated(cid));
        self.events.push(SimEvent::Sound { id: "colony_lost".into(), pos: self.colonies[cid as usize].pos });
    }

    // -----------------------------------------------------------------------------------------
    // colonies
    // -----------------------------------------------------------------------------------------
    fn update_colonies(&mut self, dt: f32) {
        let mut hits: Vec<Hit> = Vec::new();
        let mut spawned: Vec<Projectile> = Vec::new();
        let cap = self.unit_cap();
        for ci in 0..self.colonies.len() {
            let def = self.defs.colonies[self.colonies[ci].def as usize].clone();
            let (team, pos) = (self.colonies[ci].team, self.colonies[ci].pos);
            match self.colonies[ci].state.clone() {
                ColonyState::Active => {
                    // production
                    let mut producing = false;
                    if team != 0 && let Some(kind) = self.colonies[ci].production.kind {
                        let count = self.team_count(team);
                        if count < cap {
                            producing = true;
                            let bt = self.defs.units[kind as usize].build_time * def.build_time_multiplier * self.team_production_mult(team);
                            self.colonies[ci].production.progress += dt;
                            if self.colonies[ci].production.progress >= bt {
                                self.colonies[ci].production.progress = 0.0;
                                let exit = self.grid.nearest_free(pos + def.exit_offset);
                                let heading = dir_to_heading(def.exit_offset);
                                let id = self.spawn_unit(kind, team, exit, heading);
                                let rally = self.colonies[ci].rally;
                                self.colonies[ci].units_bred += 1;
                                self.issue(&[id], Order::Move(rally));
                            }
                        }
                    }
                    // regeneration (only while not producing, as in OpenSA)
                    if !producing && self.colonies[ci].hp < def.hp {
                        self.colonies[ci].hp = (self.colonies[ci].hp + def.regen_per_s * dt).min(def.hp);
                    }
                    // turrets
                    for ti in 0..def.turrets.len() {
                        let tdef = &def.turrets[ti];
                        let widx = self.defs.weapon(&tdef.weapon).unwrap();
                        let w = self.defs.weapons[widx as usize].clone();
                        let tpos = pos + tdef.offset;
                        let mut turret = self.colonies[ci].turrets[ti].clone();
                        turret.reload = (turret.reload - dt).max(0.0);
                        // validate / acquire target
                        if let Some(tid) = turret.target {
                            let ok = self.unit(tid).is_some_and(|u| self.can_target_unit(&w, team, u) && u.pos.distance(tpos) - self.defs.units[u.kind as usize].radius <= w.range);
                            if !ok {
                                turret.target = None;
                            }
                        }
                        if turret.target.is_none() && self.tick % 5 == ti as u64 % 5 {
                            // colonies never shoot colonies
                            let mut w2 = w.clone();
                            w2.targets.colony = false;
                            if let Some(Target::Unit(id)) = self.find_target(tpos, team, &w2, w.range) {
                                turret.target = Some(id);
                            }
                        }
                        if let Some(tid) = turret.target {
                            let up = self.unit(tid).map(|u| u.pos).unwrap_or(tpos);
                            let want = dir_to_heading(up - tpos);
                            turret.yaw = turn_towards(turret.yaw, want, tdef.turn_rate.to_radians() * dt);
                            if turret.reload <= 0.0 && angle_diff(turret.yaw, want).abs() < 0.2 {
                                turret.reload = w.reload;
                                turret.fire_seq = turret.fire_seq.wrapping_add(1);
                                self.events.push(SimEvent::TurretFired { colony: ci as u32, turret: ti });
                                let muzzle = tpos + heading_to_dir(turret.yaw) * 0.4;
                                self.fire_weapon(widx, team, None, muzzle, tdef.height, Target::Unit(tid), &mut hits, &mut spawned);
                            }
                        }
                        self.colonies[ci].turrets[ti] = turret;
                    }
                }
                ColonyState::Defeated { timer, launched, resolved, picks } => {
                    let timer = timer + dt;
                    let mut launched = launched;
                    if !launched && timer >= def.bits.fire_delay {
                        launched = true;
                        self.scatter_bits(ci as u32, &def);
                    }
                    if launched && resolved >= def.bits.count {
                        // resolve ownership: most picks wins, ties -> neutral
                        let mut best_team = 0u8;
                        let mut best = 0u32;
                        let mut tie = false;
                        for (t, n) in picks.iter().enumerate() {
                            if *n > best {
                                best = *n;
                                best_team = t as u8;
                                tie = false;
                            } else if *n == best && best > 0 {
                                tie = true;
                            }
                        }
                        if tie {
                            best_team = 0;
                        }
                        let c = &mut self.colonies[ci];
                        c.team = best_team;
                        c.hp = def.hp * def.bits.resurrect_health;
                        c.state = ColonyState::Active;
                        c.production.progress = 0.0;
                        if c.production.kind.is_none() {
                            c.production.kind = def.produces.first().and_then(|p| self.defs.unit(p));
                        }
                        self.stats.captures += 1;
                        if let Some(t) = self.teams.get_mut(best_team as usize)
                            && best_team != 0
                        {
                            t.takeovers += 1;
                        }
                        self.events.push(SimEvent::ColonyCaptured { colony: ci as u32, team: best_team });
                        self.events.push(SimEvent::Sound { id: "colony_captured".into(), pos });
                    } else {
                        self.colonies[ci].state = ColonyState::Defeated { timer, launched, resolved, picks };
                    }
                }
            }
        }
        for h in hits {
            self.apply_hit(h);
        }
        for p in spawned {
            self.events.push(SimEvent::ProjectileSpawned(p.id));
            self.projectiles.push(p);
        }
    }

    fn scatter_bits(&mut self, cid: u32, def: &ColonyDef) {
        let pos = self.colonies[cid as usize].pos;
        let mut placed = 0;
        let mut tries = 0;
        while placed < def.bits.count && tries < 400 {
            tries += 1;
            let a = self.rng.random_range(0.0..TAU);
            let r = self.rng.random_range(def.bits.min_range..def.bits.max_range + (tries / 50) as f32);
            let p = pos + Vec2::new(a.cos(), a.sin()) * r;
            let c = self.grid.cell_of(p);
            if self.grid.is_blocked(c) || !self.grid.in_bounds(c) {
                continue;
            }
            let end = self.grid.center(c);
            if self.bits.iter().any(|b| b.alive && b.end.distance(end) < 1.0) {
                continue;
            }
            let id = self.next_bit;
            self.next_bit += 1;
            let lifetime = self.rng.random_range(def.bits.lifetime_min..def.bits.lifetime_max);
            self.bits.push(Bit { id, colony: cid, start: pos, end, t: 0.0, flight: def.bits.flight_time, lifetime, alive: true, claimed: false });
            self.events.push(SimEvent::BitSpawned(id));
            placed += 1;
        }
        // if the map was too crowded to place all bits, count the missing ones as expired
        if placed < def.bits.count
            && let ColonyState::Defeated { resolved, picks, .. } = &mut self.colonies[cid as usize].state
        {
            *resolved += def.bits.count - placed;
            picks[0] += def.bits.count - placed;
        }
        self.events.push(SimEvent::ColonyScattered(cid));
        self.events.push(SimEvent::Sound { id: "colony_explode".into(), pos });
    }

    fn update_bits(&mut self, dt: f32) {
        let mut picks: Vec<(u32, u32, UnitId, u8)> = Vec::new(); // (bit, colony, unit, team)
        let mut expired: Vec<(u32, u32)> = Vec::new();
        for b in self.bits.iter_mut() {
            if !b.alive {
                continue;
            }
            b.t += dt;
            if !b.landed() {
                continue;
            }
            b.lifetime -= dt;
            if b.lifetime <= 0.0 {
                b.alive = false;
                expired.push((b.id, b.colony));
            }
        }
        // pickups
        let mut scratch = std::mem::take(&mut self.scratch);
        for bi in 0..self.bits.len() {
            let b = &self.bits[bi];
            if !b.alive || !b.landed() {
                continue;
            }
            let radius = self.defs.colonies[self.colonies[b.colony as usize].def as usize].bits.pickup_radius;
            scratch.clear();
            self.spatial.query(b.end, radius + 0.6, &mut scratch);
            let mut best: Option<(f32, UnitId, u8)> = None;
            for idx in scratch.iter() {
                if let Some(u) = self.units[*idx as usize].as_ref()
                    && u.alive()
                    && !self.defs.units[u.kind as usize].flying
                    && u.team != 0
                {
                    let d = u.pos.distance(b.end);
                    if d <= radius + self.defs.units[u.kind as usize].radius * 0.5 && best.is_none_or(|(bd, _, _)| d < bd) {
                        best = Some((d, u.id, u.team));
                    }
                }
            }
            if let Some((_, uid, team)) = best {
                picks.push((b.id, b.colony, uid, team));
                self.bits[bi].alive = false;
                self.bits[bi].claimed = true;
            }
        }
        scratch.clear();
        self.scratch = scratch;
        for (bit, colony, unit, team) in picks {
            if let ColonyState::Defeated { resolved, picks, .. } = &mut self.colonies[colony as usize].state {
                *resolved += 1;
                picks[team as usize] += 1;
            }
            let pos = self.bits.iter().find(|b| b.id == bit).map(|b| b.end).unwrap_or(Vec2::ZERO);
            self.events.push(SimEvent::BitPicked { bit, unit, team });
            self.events.push(SimEvent::Sound { id: "bit_pickup".into(), pos });
            if let Some(u) = self.unit_mut(unit)
                && matches!(u.order, Order::Collect(b) if b == bit)
            {
                u.order = Order::Idle;
            }
        }
        for (bit, colony) in expired {
            if let ColonyState::Defeated { resolved, picks, .. } = &mut self.colonies[colony as usize].state {
                *resolved += 1;
                picks[0] += 1;
            }
            self.events.push(SimEvent::BitExpired(bit));
        }
        self.bits.retain(|b| b.alive);
    }

    // -----------------------------------------------------------------------------------------
    // projectiles
    // -----------------------------------------------------------------------------------------
    fn update_projectiles(&mut self, dt: f32) {
        let mut hits: Vec<Hit> = Vec::new();
        let mut removed = Vec::new();
        let mut rehop: Vec<(usize, Vec2, bool)> = Vec::new();
        for (pi, p) in self.projectiles.iter_mut().enumerate() {
            if !p.alive {
                continue;
            }
            p.t += dt;
            match p.kind.clone() {
                ProjectileKind::Bullet { arc, .. } | ProjectileKind::Bouncing { arc, .. } => {
                    let f = (p.t / p.flight).clamp(0.0, 1.0);
                    p.pos = p.start.lerp(p.aim, f);
                    let apex = arc * p.hop_len;
                    p.height = p.start_height * (1.0 - f) + apex * (PI * f).sin();
                    p.heading = dir_to_heading(p.aim - p.start);
                    if f >= 1.0 {
                        if let ProjectileKind::Bouncing { bounce_factor, split, .. } = p.kind
                            && p.bounces_left > 0
                        {
                            p.bounces_left -= 1;
                            let dir = (p.aim - p.start).normalize_or_zero();
                            if split {
                                // one ball goes on 45 degrees to one side, a new one 45 degrees to the other
                                let (s, c) = std::f32::consts::FRAC_PI_4.sin_cos();
                                let a = Vec2::new(dir.x * c - dir.y * s, dir.x * s + dir.y * c);
                                let b = Vec2::new(dir.x * c + dir.y * s, -dir.x * s + dir.y * c);
                                // (the copy is taken before the original is re-aimed)
                                rehop.push((pi, p.aim + b * p.hop_len * bounce_factor, true));
                                rehop.push((pi, p.aim + a * p.hop_len * bounce_factor, false));
                            } else {
                                rehop.push((pi, p.aim + dir * p.hop_len * bounce_factor, false));
                            }
                            continue;
                        }
                        p.alive = false;
                        hits.push(Hit { pos: p.aim, weapon: p.weapon, team: p.team, source: p.source, direct: p.target });
                        removed.push(p.id);
                    }
                }
                ProjectileKind::Missile { accel, turn_rate, .. } => {
                    p.speed += accel * dt;
                    let tp = p.target.and_then(|t| match t {
                        Target::Unit(id) => self.units.get(id.idx as usize).and_then(|s| s.as_ref()).filter(|u| u.id == id && u.alive()).map(|u| u.pos),
                        Target::Colony(c) => self.colonies.get(c as usize).map(|c| c.pos),
                    });
                    let aim = tp.unwrap_or(p.aim);
                    p.aim = aim;
                    let want = dir_to_heading(aim - p.pos);
                    p.heading = turn_towards(p.heading, want, turn_rate.to_radians() * dt);
                    p.pos += heading_to_dir(p.heading) * p.speed * dt;
                    p.height = (p.height + (0.6 - p.height) * dt * 2.0).max(0.2);
                    if p.pos.distance(aim) <= 0.35 || p.t > 12.0 {
                        p.alive = false;
                        hits.push(Hit { pos: p.pos, weapon: p.weapon, team: p.team, source: p.source, direct: p.target });
                        removed.push(p.id);
                    }
                }
                ProjectileKind::Bomb { .. } => {
                    // dropped, so it keeps the sideways throw it was given and falls ever faster
                    let f = (p.t / p.flight).clamp(0.0, 1.0);
                    p.pos = p.start.lerp(p.aim, f);
                    p.height = p.start_height * (1.0 - f * f);
                    if f >= 1.0 {
                        p.alive = false;
                        hits.push(Hit { pos: p.aim, weapon: p.weapon, team: p.team, source: p.source, direct: None });
                        removed.push(p.id);
                    }
                }
                ProjectileKind::Instant => {
                    p.alive = false;
                    removed.push(p.id);
                }
            }
        }
        let mut split_off: Vec<Projectile> = Vec::new();
        for (pi, next, new_ball) in rehop {
            let next = self.grid.clamp(next);
            let mut p = self.projectiles[pi].clone();
            let landed = p.aim;
            p.start = landed;
            p.aim = next;
            p.hop_len = p.start.distance(p.aim);
            p.flight = (p.hop_len / p.speed.max(0.1)).max(0.05);
            p.t = 0.0;
            p.start_height = 0.0;
            p.heading = dir_to_heading(p.aim - p.start);
            if new_ball {
                p.id = self.next_projectile;
                self.next_projectile += 1;
                split_off.push(p);
            } else {
                self.projectiles[pi] = p;
                self.events.push(SimEvent::Sound { id: "bounce".into(), pos: landed });
            }
        }
        for p in split_off {
            self.events.push(SimEvent::ProjectileSpawned(p.id));
            self.projectiles.push(p);
        }
        self.projectiles.retain(|p| p.alive);
        for id in removed {
            self.events.push(SimEvent::ProjectileRemoved(id));
        }
        for h in hits {
            self.apply_hit(h);
        }
    }

    // -----------------------------------------------------------------------------------------
    // neutral flyers / pirates (Stage 4 hooks; harmless when the map disables them)
    // -----------------------------------------------------------------------------------------
    fn update_creeps(&mut self, dt: f32) {
        // flying creeps cross the map on a fixed heading and drop their weapon periodically
        let mut hits: Vec<Hit> = Vec::new();
        let mut spawned: Vec<Projectile> = Vec::new();
        let mut gone = Vec::new();
        let size = self.grid.size();
        for i in 0..self.units.len() {
            let Some(u) = self.units[i].as_ref() else { continue };
            if !u.alive() || u.cruise.is_none() {
                continue;
            }
            let id = u.id;
            let def = self.defs.units[u.kind as usize].clone();
            let dir = u.cruise.unwrap();
            let p = u.pos + dir * def.speed * dt;
            if p.x < -3.0 || p.y < -3.0 || p.x > size.x + 3.0 || p.y > size.y + 3.0 {
                gone.push(id);
                continue;
            }
            let u = self.units[i].as_mut().unwrap();
            u.pos = p;
            u.heading = dir_to_heading(dir);
            u.anim = Anim::Move;
            u.reload -= dt;
            u.phase += dt;
            let Some(widx) = def.weapon.as_ref().and_then(|w| self.defs.weapon(w)) else { continue };
            let Some(f) = def.flyer.clone() else {
                // no pattern: drop the weapon every reload, bombs straight down, the rest thrown ahead
                if u.reload <= 0.0 {
                    let w = self.defs.weapons[widx as usize].clone();
                    u.reload = w.reload;
                    let (pos, team) = (u.pos, u.team);
                    let aim = if matches!(w.projectile, ProjectileKind::Bomb { .. }) { pos } else { pos + dir * w.range.min(3.0) };
                    self.stats.shots += 1;
                    self.launch(widx, team, Some(id), pos, def.altitude, aim, None, None, &mut hits, &mut spawned);
                }
                continue;
            };
            // OpenSA bombing rhythm: drop for `drop_time`, rest for `rest_time`
            let cycle = f.drop_time + f.rest_time;
            let dropping = f.rest_time <= 0.0 || cycle <= 0.0 || u.phase % cycle < f.drop_time;
            if !dropping || u.reload > 0.0 {
                continue;
            }
            let aim_local = f.aims.get(u.drops as usize % f.aims.len().max(1)).copied().unwrap_or(Vec2::ZERO);
            u.drops = u.drops.wrapping_add(1);
            u.burst_left = u.burst_left.saturating_sub(1);
            if u.burst_left > 0 {
                u.reload = f.burst_gap;
            } else {
                u.burst_left = f.burst.max(1);
                u.reload = f.interval;
            }
            u.attack_seq = u.attack_seq.wrapping_add(1);
            let (pos, team, heading) = (u.pos, u.team, u.heading);
            // the flyer's frame: forward along its heading, right = forward x up
            let fwd = heading_to_dir(heading);
            let right = Vec2::new(-fwd.y, fwd.x);
            let spot = pos + right * aim_local.x + fwd * aim_local.y;
            let w = self.defs.weapons[widx as usize].clone();
            if !w.fire_sound.is_empty() {
                self.events.push(SimEvent::Sound { id: w.fire_sound.clone(), pos });
            }
            for _ in 0..f.shots.max(1) {
                let aim = self.inaccurate(&w, pos, spot);
                self.stats.shots += 1;
                self.launch(widx, team, Some(id), pos, def.altitude, aim, None, None, &mut hits, &mut spawned);
            }
            if let Some(ew) = f.extra_weapon.as_ref().and_then(|w| self.defs.weapon(w)) {
                let e = self.defs.weapons[ew as usize].clone();
                let aim = self.inaccurate(&e, pos, spot);
                self.launch(ew, team, Some(id), pos, def.altitude, aim, None, None, &mut hits, &mut spawned);
            }
        }
        for id in gone {
            self.remove_unit(id);
        }
        for h in hits {
            self.apply_hit(h);
        }
        for p in spawned {
            self.events.push(SimEvent::ProjectileSpawned(p.id));
            self.projectiles.push(p);
        }
        // the level's plants and flyers come and go
        if !self.map.rules.creeps.is_empty() {
            self.update_creep_pools(dt);
        } else if self.map.rules.flyers && !self.map.rules.flyer_kinds.is_empty() {
            self.flyer_timer -= dt;
            if self.flyer_timer <= 0.0 {
                self.flyer_timer = self.map.rules.flyer_interval * self.rng.random_range(0.8..1.2);
                let k = self.map.rules.flyer_kinds[self.rng.random_range(0..self.map.rules.flyer_kinds.len())].clone();
                if let Some(kind) = self.defs.unit(&k) {
                    self.spawn_flyer(kind);
                }
            }
        }
        if self.map.rules.pirates {
            self.pirate_timer -= dt;
            if self.pirate_timer <= 0.0 {
                self.pirate_timer = self.map.rules.pirate_interval * self.rng.random_range(0.8..1.3);
                self.spawn_pirates();
            }
        }
    }

    /// Spawn a neutral flyer that crosses the whole map. As in OpenSA's CreepFlyerSpawner it
    /// passes over a random cell on one of eight headings, entering at one edge and leaving at the
    /// opposite one.
    pub fn spawn_flyer(&mut self, kind: u16) -> UnitId {
        let size = self.grid.size();
        let through = Vec2::new(self.rng.random_range(0.0..size.x), self.rng.random_range(0.0..size.y));
        let heading = self.rng.random_range(0..8) as f32 * TAU / 8.0;
        let dir = heading_to_dir(heading);
        // back along the heading to the map edge
        let edge_t = |p: f32, d: f32, max: f32| if d > 1e-4 { p / d } else if d < -1e-4 { (p - max) / d } else { f32::INFINITY };
        let back = edge_t(through.x, dir.x, size.x).min(edge_t(through.y, dir.y, size.y));
        let start = through - dir * back;
        let id = self.spawn_unit(kind, 0, start, heading);
        let first = self.rng.random_range(0.2..1.0);
        if let Some(u) = self.unit_mut(id) {
            u.cruise = Some(dir);
            u.reload = first;
        }
        self.events.push(SimEvent::FlyerSpawn(id));
        id
    }

    /// Spawn timers of the level's creep pools: each pool tops itself up by one creep per interval
    /// (OpenSA PlantSpawner / CreepFlyerSpawner, with the original level's counts as the limits).
    fn update_creep_pools(&mut self, dt: f32) {
        let n = self.map.rules.creeps.len();
        if self.creep_timers.len() != n {
            self.creep_timers = (0..n)
                .map(|i| {
                    let (a, b) = self.map.rules.creeps[i].first;
                    if b > a { self.rng.random_range(a..b) } else { a }
                })
                .collect();
        }
        for i in 0..n {
            self.creep_timers[i] -= dt;
            if self.creep_timers[i] > 0.0 {
                continue;
            }
            let pool = self.map.rules.creeps[i].clone();
            let (a, b) = pool.interval;
            self.creep_timers[i] = if b > a { self.rng.random_range(a..b) } else { a.max(0.5) };
            let kinds: Vec<u16> = pool.units.iter().filter_map(|u| self.defs.unit(u)).collect();
            if kinds.is_empty() {
                continue;
            }
            let alive = self.living_units().filter(|u| kinds.contains(&u.kind)).count() as u32;
            if alive >= pool.count {
                continue;
            }
            let kind = kinds[self.rng.random_range(0..kinds.len())];
            let def = &self.defs.units[kind as usize];
            if def.flying {
                self.spawn_flyer(kind);
            } else if def.plant.is_some() {
                if let Some(cell) = self.free_plant_cell() {
                    let heading = self.rng.random_range(0.0..TAU);
                    self.spawn_unit(kind, 0, cell, heading);
                }
            } else {
                let p = self.free_plant_cell().unwrap_or(self.grid.size() * 0.5);
                let heading = self.rng.random_range(0.0..TAU);
                self.spawn_unit(kind, 0, p, heading);
            }
        }
    }

    /// A random free cell of open ground with nobody on it (OpenSA PlantSpawner: 100 tries).
    fn free_plant_cell(&mut self) -> Option<Vec2> {
        let size = self.grid.size();
        for _ in 0..100 {
            let c = IVec2::new(self.rng.random_range(0..size.x as i32), self.rng.random_range(0..size.y as i32));
            if self.grid.is_blocked(c) {
                continue;
            }
            let p = self.grid.center(c);
            if self.living_units().any(|u| !self.defs.units[u.kind as usize].flying && u.pos.distance(p) < 1.0) || self.bits.iter().any(|b| b.alive && b.end.distance(p) < 0.75) {
                continue;
            }
            return Some(p);
        }
        None
    }

    /// Pirate ants emerge from an ant hole (random free spot), 1..6 of them (OpenSA shares).
    pub fn spawn_pirates(&mut self) {
        let kinds: Vec<(u16, u32)> = [("neutral_bull_ant", 45), ("neutral_pirate_grenadier", 45), ("ant_bazooka_pirate", 10)]
            .iter()
            .filter_map(|(k, s)| self.defs.unit(k).map(|i| (i, *s)))
            .collect();
        if kinds.is_empty() {
            return;
        }
        let size = self.grid.size();
        let p = Vec2::new(self.rng.random_range(4.0..size.x - 4.0), self.rng.random_range(4.0..size.y - 4.0));
        let p = self.grid.nearest_free(p);
        let n = self.rng.random_range(1..=6);
        let total: u32 = kinds.iter().map(|k| k.1).sum();
        for i in 0..n {
            let mut r = self.rng.random_range(0..total);
            let mut kind = kinds[0].0;
            for (k, s) in &kinds {
                if r < *s {
                    kind = *k;
                    break;
                }
                r -= *s;
            }
            let ang = i as f32 * 1.1;
            let id = self.spawn_unit(kind, 0, p + Vec2::new(ang.cos(), ang.sin()) * 0.8, ang);
            // pirates wander towards the nearest colony
            if let Some(c) = self.colonies.iter().filter(|c| c.team != 0).min_by(|a, b| a.pos.distance(p).total_cmp(&b.pos.distance(p))) {
                let target = c.pos;
                self.issue_uncontrolled(id, Order::AttackMove(target));
            }
        }
        self.events.push(SimEvent::PirateSpawn { pos: p, count: n });
        self.events.push(SimEvent::Sound { id: "ant_hole".into(), pos: p });
    }

    /// Orders for creeps (bypasses the `controllable` check).
    pub fn issue_uncontrolled(&mut self, id: UnitId, order: Order) {
        self.apply_order(id, order);
    }

    // -----------------------------------------------------------------------------------------
    // neutral creep plants (OpenSA creep-plants.yaml, ^CoreNeutralTowerCreep)
    // -----------------------------------------------------------------------------------------
    /// Is an enemy of the creeps (any player's creature, or a player's colony) within `range` of
    /// `pos`? This is what sets off Seed Balls and Death Lollies (OpenSA ProximityExternalCondition
    /// on every creature and building, measured centre to centre).
    fn enemy_near(&self, pos: Vec2, range: f32) -> bool {
        let mut scratch = Vec::new();
        self.spatial.query(pos, range + 0.5, &mut scratch);
        let near_unit = scratch.iter().any(|idx| {
            self.units[*idx as usize].as_ref().is_some_and(|u| u.alive() && u.team != 0 && u.pos.distance(pos) <= range)
        });
        near_unit || self.colonies.iter().any(|c| c.active() && c.team != 0 && c.pos.distance(pos) <= range)
    }

    fn update_plants(&mut self, dt: f32) {
        let mut hits: Vec<Hit> = Vec::new();
        let mut out: Vec<Projectile> = Vec::new();
        let mut blow_up: Vec<UnitId> = Vec::new();
        let mut withered: Vec<UnitId> = Vec::new();
        for i in 0..self.units.len() {
            let Some(u) = self.units[i].as_ref() else { continue };
            if !u.alive() {
                continue;
            }
            let def = &self.defs.units[u.kind as usize];
            let Some(plant) = def.plant.clone() else { continue };
            let (id, pos, max_hp) = (u.id, u.pos, def.hp);
            let weapon_idx = self.weapon_of(u);
            let attack_anim = def.attack_anim_time;
            {
                let u = self.units[i].as_mut().unwrap();
                u.age += dt;
                u.reload = (u.reload - dt).max(0.0);
                u.scan_timer -= dt;
                u.vel = Vec2::ZERO;
                if plant.decay_per_s > 0.0 {
                    u.hp -= plant.decay_per_s * dt;
                    if u.hp <= 0.0 {
                        withered.push(id);
                        continue;
                    }
                } else if u.hp < max_hp {
                    u.hp = (u.hp + plant.regen_per_s * dt).min(max_hp);
                }
                // still growing, or hurt badly enough to stop (it heals and carries on)
                if u.age < plant.grow_time || u.hp < max_hp * plant.injured_below {
                    u.anim = Anim::Idle;
                    u.attack_timer = None;
                    u.target = None;
                    continue;
                }
            }
            match plant.attack {
                PlantAttack::Passive => {}
                PlantAttack::Mine { trigger } => {
                    if self.enemy_near(pos, trigger) {
                        blow_up.push(id);
                    }
                }
                PlantAttack::Burst { trigger, count, ref seed_weapon } => {
                    let Some(widx) = weapon_idx else { continue };
                    let triggered = self.enemy_near(pos, trigger);
                    let u = self.units[i].as_mut().unwrap();
                    if !triggered {
                        u.anim = Anim::Idle;
                        continue;
                    }
                    u.anim = Anim::Attack;
                    if u.reload > 0.0 {
                        continue;
                    }
                    let w = self.defs.weapons[widx as usize].clone();
                    u.reload = w.reload;
                    u.attack_seq = u.attack_seq.wrapping_add(1);
                    if !w.fire_sound.is_empty() {
                        self.events.push(SimEvent::Sound { id: w.fire_sound.clone(), pos });
                    }
                    // shrapnel thrown at random spots all round (OpenSA AimChance 0)
                    let mut shots: Vec<(u16, Vec2)> = Vec::new();
                    for _ in 0..count {
                        shots.push((widx, self.random_spot(pos, w.min_range, w.range)));
                    }
                    if let Some(sw) = seed_weapon.as_ref().and_then(|s| self.defs.weapon(s)) {
                        let r = self.defs.weapons[sw as usize].range;
                        shots.push((sw, self.random_spot(pos, 0.0, r)));
                    }
                    for (wi, aim) in shots {
                        self.stats.shots += 1;
                        self.launch(wi, 0, Some(id), pos, 0.45, aim, None, None, &mut hits, &mut out);
                    }
                }
                PlantAttack::Aimed | PlantAttack::Radial { .. } | PlantAttack::Vortex { .. } => {
                    let Some(widx) = weapon_idx else { continue };
                    let w = self.defs.weapons[widx as usize].clone();
                    // keep or find a target in range
                    let mut target = self.units[i].as_ref().unwrap().target;
                    if let Some(t) = target
                        && (!self.target_valid(&w, 0, t) || self.edge_distance(pos, t) > w.range)
                    {
                        target = None;
                    }
                    if target.is_none() && self.units[i].as_ref().unwrap().scan_timer <= 0.0 {
                        self.units[i].as_mut().unwrap().scan_timer = self.defs.rules.auto_target_interval;
                        target = self.find_target(pos, 0, &w, w.range);
                    }
                    let u = self.units[i].as_mut().unwrap();
                    u.target = target;
                    let Some(t) = target else {
                        u.anim = Anim::Idle;
                        u.attack_timer = None;
                        continue;
                    };
                    if let PlantAttack::Vortex { arms, deg_per_s } = plant.attack {
                        // a spinning spray: shots aimed at points circling the plant at full range
                        u.anim = Anim::Attack;
                        u.spin = (u.spin + deg_per_s.to_radians() * dt) % TAU;
                        if u.reload > 0.0 {
                            continue;
                        }
                        u.reload = w.reload;
                        u.attack_seq = u.attack_seq.wrapping_add(1);
                        let spin = u.spin;
                        for k in 0..arms.max(1) {
                            let a = spin + k as f32 * TAU / arms.max(1) as f32;
                            let aim = pos + heading_to_dir(a) * w.range;
                            self.stats.shots += 1;
                            self.launch(widx, 0, Some(id), pos, 0.5, aim, None, None, &mut hits, &mut out);
                        }
                        continue;
                    }
                    // wind up (attack animation), then shoot
                    match u.attack_timer {
                        None => {
                            if u.reload <= 0.0 {
                                u.attack_timer = Some(0.0);
                                u.shot_released = false;
                                u.attack_seq = u.attack_seq.wrapping_add(1);
                                u.anim = Anim::Attack;
                                self.events.push(SimEvent::AttackStarted { unit: id, target: t, seq: u.attack_seq });
                            } else {
                                u.anim = Anim::Idle;
                            }
                        }
                        Some(time) => {
                            let time = time + dt;
                            u.attack_timer = Some(time);
                            if !u.shot_released && time >= w.fire_delay {
                                u.shot_released = true;
                                u.reload = w.reload;
                                let base = u.heading;
                                match plant.attack {
                                    PlantAttack::Radial { count } => {
                                        // every direction at once; the homing shots curl round onto the target
                                        if !w.fire_sound.is_empty() {
                                            self.events.push(SimEvent::Sound { id: w.fire_sound.clone(), pos });
                                        }
                                        let tp = self.target_pos(t).unwrap_or(pos);
                                        for k in 0..count.max(1) {
                                            let h = base + k as f32 * TAU / count.max(1) as f32;
                                            let from = pos + heading_to_dir(h) * 0.35;
                                            let aim = self.inaccurate(&w, pos, tp);
                                            self.stats.shots += 1;
                                            self.launch(widx, 0, Some(id), from, 0.55, aim, Some(t), Some(h), &mut hits, &mut out);
                                        }
                                    }
                                    _ => self.fire_weapon(widx, 0, Some(id), pos, 0.55, t, &mut hits, &mut out),
                                }
                            }
                            let u = self.units[i].as_mut().unwrap();
                            if time >= attack_anim.max(w.fire_delay + 0.05) {
                                u.attack_timer = None;
                                u.anim = Anim::Idle;
                            }
                        }
                    }
                }
            }
        }
        for id in withered {
            self.kill_unit(id, None);
        }
        for id in blow_up {
            if self.unit(id).is_some_and(|u| u.alive()) {
                self.kill_unit(id, None);
            }
        }
        for h in hits {
            self.apply_hit(h);
        }
        for p in out {
            self.events.push(SimEvent::ProjectileSpawned(p.id));
            self.projectiles.push(p);
        }
    }

    /// A random ground point between `min` and `max` cells from `pos`, inside the map.
    fn random_spot(&mut self, pos: Vec2, min: f32, max: f32) -> Vec2 {
        let a = self.rng.random_range(0.0..TAU);
        let r = if max > min { self.rng.random_range(min..max) } else { max };
        self.grid.clamp(pos + heading_to_dir(a) * r)
    }

    // -----------------------------------------------------------------------------------------
    // deaths, victory
    // -----------------------------------------------------------------------------------------
    fn cleanup_units(&mut self, dt: f32) {
        let corpse_time = self.defs.rules.corpse_time;
        let mut remove = Vec::new();
        for u in self.units.iter_mut().flatten() {
            match u.state {
                UnitState::Dying => {
                    u.death_timer += dt;
                    let dt_len = 1.2f32;
                    if u.death_timer >= dt_len {
                        u.state = UnitState::Corpse;
                        u.death_timer = 0.0;
                    }
                }
                UnitState::Corpse => {
                    u.death_timer += dt;
                    if u.death_timer >= corpse_time {
                        remove.push(u.id);
                    }
                }
                UnitState::Alive => {}
            }
        }
        for id in remove {
            self.remove_unit(id);
        }
        // per-team counts
        for t in self.teams.iter_mut() {
            t.units_alive = 0;
            t.colonies = 0;
        }
        for u in self.units.iter().flatten() {
            if u.alive() && let Some(t) = self.teams.get_mut(u.team as usize) {
                t.units_alive += 1;
            }
        }
        for c in &self.colonies {
            if c.active() && let Some(t) = self.teams.get_mut(c.team as usize) {
                t.colonies += 1;
            }
        }
    }

    /// OpenSA rules: a team is defeated when it has no colonies and no units; a team wins when all
    /// colonies belong to it (none neutral/defeated) and every enemy has no units.
    fn check_victory(&mut self) {
        if self.game_over {
            return;
        }
        let mut newly_defeated = Vec::new();
        for t in self.teams.iter_mut().skip(1) {
            if !t.defeated && t.units_alive == 0 && t.colonies == 0 && t.def.controller != Controller::None {
                t.defeated = true;
                newly_defeated.push(t.def.id);
            }
        }
        for id in newly_defeated {
            self.events.push(SimEvent::TeamDefeated(id));
        }
        let counts = |c: &Colony| self.defs.colonies[c.def as usize].counts_for_victory;
        let any_unowned = self.colonies.iter().any(|c| counts(c) && (!c.active() || c.team == 0));
        if any_unowned {
            return;
        }
        let candidates: Vec<u8> = self.teams.iter().skip(1).filter(|t| !t.defeated && t.def.controller != Controller::None).map(|t| t.def.id).collect();
        for team in candidates {
            let all_colonies = self.colonies.iter().filter(|c| counts(c)).all(|c| c.team == team);
            let enemies_dead = self.teams.iter().skip(1).filter(|t| t.def.id != team && t.def.controller != Controller::None).all(|t| t.units_alive == 0 && t.colonies == 0);
            if all_colonies && enemies_dead {
                self.winner = Some(team);
                self.game_over = true;
                self.events.push(SimEvent::Victory(team));
                break;
            }
        }
    }

    // -----------------------------------------------------------------------------------------
    // queries for the game layer
    // -----------------------------------------------------------------------------------------
    /// Units of a team inside a world-space rectangle (selection boxes are done in screen space by
    /// the game layer; this is for tests and AI).
    pub fn units_in_circle(&self, center: Vec2, radius: f32) -> Vec<UnitId> {
        self.living_units().filter(|u| u.pos.distance(center) <= radius).map(|u| u.id).collect()
    }

    /// Nearest living unit to a point within `radius` (any team).
    pub fn pick_unit(&self, p: Vec2, radius: f32) -> Option<UnitId> {
        self.living_units()
            .map(|u| (u.pos.distance(p) - self.defs.units[u.kind as usize].radius, u.id))
            .filter(|(d, _)| *d <= radius)
            .min_by(|a, b| a.0.total_cmp(&b.0))
            .map(|(_, id)| id)
    }

    /// Colony whose footprint contains `p`.
    pub fn pick_colony(&self, p: Vec2) -> Option<u32> {
        self.colonies.iter().find(|c| (p - c.pos).abs().max_element() <= self.defs.colonies[c.def as usize].half_extent + 0.5).map(|c| c.id)
    }

    pub fn team_name(&self, team: u8) -> &str {
        self.teams.get(team as usize).map(|t| t.def.name.as_str()).unwrap_or("?")
    }

    pub fn cells_blocked(&self) -> Vec<IVec2> {
        self.grid.blocked_cells().collect()
    }
}

fn def_radius(w: &World, u: &Unit) -> f32 {
    w.defs.units[u.kind as usize].radius
}

/// Idle units walk to the nearest landed colony bit within the rule radius (OpenSA
/// TakeColonyBitOnIdle: idle delay then a scan every so often).
fn u_idle_bit_search(w: &mut World, i: usize, pos: Vec2, _dt: f32) {
    let u = w.units[i].as_ref().unwrap();
    if u.idle_time < 0.3 || w.tick % 10 != (i as u64) % 10 {
        return;
    }
    if w.defs.units[u.kind as usize].flying || u.team == 0 {
        return;
    }
    let radius = w.defs.rules.idle_bit_search_radius;
    let mut best: Option<(f32, u32, Vec2)> = None;
    for b in &w.bits {
        if b.alive && b.landed() {
            let d = b.end.distance(pos);
            if d <= radius && best.is_none_or(|(bd, _, _)| d < bd) {
                best = Some((d, b.id, b.end));
            }
        }
    }
    if let Some((_, id, _)) = best {
        let uid = w.units[i].as_ref().unwrap().id;
        w.apply_order(uid, Order::Collect(id));
    }
}

/// Convenience constructor used by tests and the game: load defs + map from the assets folder.
pub fn load_world(assets_dir: &std::path::Path, map_file: &str) -> Result<World, DataError> {
    let defs = Defs::load_dir(&assets_dir.join("data"))?;
    let map = MapDef::load(&assets_dir.join("data").join("maps").join(map_file))?;
    World::new(defs, map)
}

/// Map a team colour letter to an RGB triple (0..1) – shared by renderer and tests.
pub fn team_rgb(color: &str) -> [f32; 3] {
    // "#RRGGBB" / "RRGGBB" (converted OpenSA player colours)
    let hex = color.trim_start_matches('#');
    if hex.len() == 6 && let Ok(v) = u32::from_str_radix(hex, 16) {
        return [((v >> 16) & 0xff) as f32 / 255.0, ((v >> 8) & 0xff) as f32 / 255.0, (v & 0xff) as f32 / 255.0];
    }
    match color {
        "Y" => [0.72, 0.66, 0.28],
        "R" => [0.53, 0.16, 0.16],
        "G" => [0.22, 0.47, 0.09],
        "B" => [0.22, 0.35, 0.72],
        _ => [0.16, 0.16, 0.16],
    }
}

impl World {
    fn boosts(&self, team: u8, kind: crate::data::BoostKind) -> u32 {
        if team == 0 {
            return 0;
        }
        self.colonies.iter().filter(|c| c.active() && c.team == team && self.defs.colonies[c.def as usize].boost == Some(kind)).count() as u32
    }

    /// Damage multiplier for a team: +10 % per owned firepower booster (OpenSA FirepowerBooster).
    pub fn team_firepower(&self, team: u8) -> f32 {
        1.0 + 0.1 * self.boosts(team, crate::data::BoostKind::Firepower) as f32
    }

    /// Breed-time multiplier for a team: -10 % per owned production booster, floor 5 % (OpenSA).
    pub fn team_production_mult(&self, team: u8) -> f32 {
        let cheat = match self.cheats.fast_breed {
            Some((t, f)) if t == team && f > 0.0 => f,
            _ => 1.0,
        };
        (1.0 - 0.1 * self.boosts(team, crate::data::BoostKind::Production) as f32).max(0.05) / cheat
    }
}

/// Console cheats.
impl World {
    /// End the game with `team` as the winner.
    pub fn cheat_win(&mut self, team: u8) {
        if !self.game_over {
            self.winner = Some(team);
            self.game_over = true;
            self.events.push(SimEvent::Victory(team));
        }
    }

    /// Hand every colony, turret and booster on the map to `team` at full health.
    pub fn cheat_capture_all(&mut self, team: u8) {
        for ci in 0..self.colonies.len() {
            let def = self.defs.colonies[self.colonies[ci].def as usize].clone();
            let c = &mut self.colonies[ci];
            c.team = team;
            c.hp = def.hp;
            c.state = ColonyState::Active;
            if c.production.kind.is_none() {
                c.production.kind = def.produces.first().and_then(|p| self.defs.unit(p));
            }
            self.events.push(SimEvent::ColonyCaptured { colony: ci as u32, team });
        }
        for b in &mut self.bits {
            b.alive = false;
        }
    }

    /// Full health for every unit and colony of `team`.
    pub fn cheat_heal(&mut self, team: u8) {
        let hps: Vec<f32> = self.defs.units.iter().map(|d| d.hp).collect();
        for u in self.units.iter_mut().flatten() {
            if u.team == team && u.alive() {
                u.hp = hps[u.kind as usize];
            }
        }
        for c in &mut self.colonies {
            if c.team == team && c.active() {
                c.hp = self.defs.colonies[c.def as usize].hp;
            }
        }
    }

    /// Kill every living unit that does not belong to `team` (neutral creeps included).
    pub fn cheat_kill_enemies(&mut self, team: u8) {
        let ids: Vec<UnitId> = self.living_units().filter(|u| u.team != team).map(|u| u.id).collect();
        for id in ids {
            self.damage_unit(id, f32::MAX, team);
        }
    }

    /// Spawn `count` units of `kind` for `team` around `pos`.
    pub fn cheat_spawn(&mut self, kind: u16, team: u8, pos: Vec2, count: u32) {
        for i in 0..count {
            let ang = i as f32 * 2.399963;
            let r = 1.5 * (i as f32 / count.max(1) as f32).sqrt() * (count as f32).sqrt().max(1.0);
            let p = pos + Vec2::new(ang.cos(), ang.sin()) * r;
            self.spawn_unit(kind, team, p, 0.0);
        }
    }
}

/// Lookup used by the AI module.
impl World {
    pub fn colonies_of(&self, team: u8) -> impl Iterator<Item = &Colony> {
        self.colonies.iter().filter(move |c| c.team == team && c.active())
    }

    pub fn nearest_enemy_colony(&self, team: u8, from: Vec2) -> Option<&Colony> {
        self.colonies.iter().filter(|c| c.team != team).min_by(|a, b| a.pos.distance(from).total_cmp(&b.pos.distance(from)))
    }

    pub fn nearest_enemy_unit(&self, team: u8, from: Vec2, radius: f32) -> Option<&Unit> {
        self.living_units().filter(|u| u.team != team && u.team != 0 || (u.team == 0 && team != 0 && u.pos.distance(from) < radius * 0.5)).filter(|u| u.pos.distance(from) <= radius).min_by(|a, b| a.pos.distance(from).total_cmp(&b.pos.distance(from)))
    }
}
