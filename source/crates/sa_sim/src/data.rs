//! Editable game data (RON files in `assets/data`).
//!
//! Every numeric statistic carries a `source` string. Values converted from the OpenSA
//! re-implementation are tagged "opensa"; they are *not* verified original Swarm Assault values
//! (see docs/GAMEPLAY_RESEARCH.md).

use std::collections::{BTreeMap, HashMap};
use std::path::Path;

use glam::Vec2;
use serde::{Deserialize, Serialize};

#[derive(Serialize, Deserialize, Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub enum Family {
    Ant,
    Beetle,
    Spider,
    Scorpion,
    Wasp,
    Neutral,
}

#[derive(Serialize, Deserialize, Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub enum Role {
    Light,
    Medium,
    Heavy,
    Creep,
    Flyer,
}

#[derive(Serialize, Deserialize, Clone, Debug)]
#[serde(default)]
pub struct TargetFlags {
    pub ground: bool,
    pub air: bool,
    pub colony: bool,
}

impl Default for TargetFlags {
    fn default() -> Self {
        Self { ground: true, air: false, colony: false }
    }
}

#[derive(Serialize, Deserialize, Clone, Debug, PartialEq)]
pub enum ProjectileKind {
    /// Damage is applied immediately when the weapon fires (bites, machine guns, sniper shots).
    Instant,
    /// Straight or lobbed shot towards the aim point. `arc` is the apex height as a fraction of
    /// the travel distance (0 = straight bullet, ~0.35 = grenade lob).
    Bullet { speed: f32, arc: f32 },
    /// Homing projectile that steers towards its target.
    Missile { speed: f32, accel: f32, turn_rate: f32 },
    /// Dropped from a flyer: falls straight down from the flyer's altitude.
    Bomb { fall_speed: f32 },
    /// Bouncing ball (Desert Fly bombs, Flying Machine gobstoppers): lobbed, bounces `bounces`
    /// times (each bounce travels `bounce_factor` of the previous hop) and explodes at rest.
    Bouncing { speed: f32, arc: f32, bounces: u32, bounce_factor: f32 },
}

#[derive(Serialize, Deserialize, Clone, Debug)]
pub struct Paralyze {
    pub duration: f32,
    pub radius: f32,
}

#[derive(Serialize, Deserialize, Clone, Debug)]
#[serde(default)]
pub struct WeaponDef {
    pub name: String,
    /// Maximum range in cells (measured to the target's edge).
    pub range: f32,
    pub min_range: f32,
    /// Seconds between shots.
    pub reload: f32,
    /// Damage per hit (OpenSA units; unit HP uses the same scale).
    pub damage: f32,
    /// Splash radius step in cells; 0 = single target only.
    pub spread: f32,
    /// Damage percentage at distance 0, 1x spread, 2x spread, ...
    pub falloff: Vec<f32>,
    /// Random aim error radius in cells at maximum range.
    pub inaccuracy: f32,
    pub projectile: ProjectileKind,
    pub targets: TargetFlags,
    pub paralyze: Option<Paralyze>,
    /// Seconds after the attack animation starts before the shot is released.
    pub fire_delay: f32,
    /// Number of projectiles fired per attack (Beetle Shrapnel = 10).
    pub volley: u32,
    /// Random direction spread of a volley in degrees (360 = all around).
    pub volley_spread_deg: f32,
    /// Visual effect id for the impact (render hook).
    pub effect: String,
    /// Audio hook ids.
    pub fire_sound: String,
    pub impact_sound: String,
    /// Can the weapon hurt units of the firing team through splash?
    pub friendly_fire: bool,
    pub source: String,
}

impl Default for WeaponDef {
    fn default() -> Self {
        Self {
            name: String::new(),
            range: 1.5,
            min_range: 0.0,
            reload: 1.0,
            damage: 100.0,
            spread: 0.0,
            falloff: vec![100.0, 37.0, 14.0, 5.0, 0.0],
            inaccuracy: 0.0,
            projectile: ProjectileKind::Instant,
            targets: TargetFlags::default(),
            paralyze: None,
            fire_delay: 0.1,
            volley: 1,
            volley_spread_deg: 0.0,
            effect: "hit_small".into(),
            fire_sound: String::new(),
            impact_sound: String::new(),
            friendly_fire: false,
            source: String::new(),
        }
    }
}

#[derive(Serialize, Deserialize, Clone, Debug)]
#[serde(default)]
pub struct UnitDef {
    pub name: String,
    pub family: Family,
    pub role: Role,
    pub hp: f32,
    /// Cells per second.
    pub speed: f32,
    /// Turn rate in degrees per second.
    pub turn_rate: f32,
    /// Collision/selection radius in cells.
    pub radius: f32,
    /// Auto-target scan radius in cells.
    pub scan_range: f32,
    /// Seconds a colony needs to breed one of these.
    pub build_time: f32,
    pub weapon: Option<String>,
    /// Moves over obstacles/terrain (wasps and neutral flyers).
    pub flying: bool,
    /// Counts as an air target (neutral flyers). Wasps are `flying` but *not* `air` in OpenSA:
    /// ground weapons (even bites) can hit them.
    pub air: bool,
    pub altitude: f32,
    /// Neutral flyers cannot receive orders.
    pub controllable: bool,
    /// Does the unit chase targets it auto-acquires (OpenSA "AttackAnything" stance)?
    pub aggressive: bool,
    /// Melee attackers cannot damage colonies unless the map rule overrides it.
    pub melee: bool,
    pub model: String,
    pub model_scale: f32,
    /// Length of the attack animation in seconds (the sim re-triggers it per shot).
    pub attack_anim_time: f32,
    pub death_time: f32,
    pub source: String,
}

impl Default for UnitDef {
    fn default() -> Self {
        Self {
            name: String::new(),
            family: Family::Ant,
            role: Role::Light,
            hp: 1000.0,
            speed: 2.0,
            turn_rate: 540.0,
            radius: 0.35,
            scan_range: 6.0,
            build_time: 5.0,
            weapon: None,
            flying: false,
            air: false,
            altitude: 0.0,
            controllable: true,
            aggressive: true,
            melee: false,
            model: String::new(),
            model_scale: 1.0,
            attack_anim_time: 0.4,
            death_time: 1.2,
            source: String::new(),
        }
    }
}

#[derive(Serialize, Deserialize, Clone, Debug)]
#[serde(default)]
pub struct TurretDef {
    /// Offset from the colony centre in cells (x east, y south).
    pub offset: Vec2,
    pub weapon: String,
    /// Degrees per second.
    pub turn_rate: f32,
    /// Name of the turret node in the colony model (render hook).
    pub node: String,
    /// Height of the barrel above ground (render hook for projectiles).
    pub height: f32,
}

impl Default for TurretDef {
    fn default() -> Self {
        Self { offset: Vec2::ZERO, weapon: String::new(), turn_rate: 720.0, node: "Turret_1".into(), height: 0.8 }
    }
}

#[derive(Serialize, Deserialize, Clone, Debug)]
#[serde(default)]
pub struct BitRules {
    pub count: u32,
    pub fire_delay: f32,
    pub min_range: f32,
    pub max_range: f32,
    pub lifetime_min: f32,
    pub lifetime_max: f32,
    /// HP fraction the colony restarts with after a capture.
    pub resurrect_health: f32,
    pub pickup_radius: f32,
    pub flight_time: f32,
}

impl Default for BitRules {
    fn default() -> Self {
        Self {
            count: 9,
            fire_delay: 3.0,
            min_range: 5.0,
            max_range: 10.0,
            lifetime_min: 20.0,
            lifetime_max: 30.0,
            resurrect_health: 0.25,
            pickup_radius: 0.6,
            flight_time: 1.2,
        }
    }
}

#[derive(Serialize, Deserialize, Clone, Debug)]
#[serde(default)]
pub struct ColonyDef {
    pub name: String,
    pub family: Family,
    pub hp: f32,
    /// HP per second regained while not producing.
    pub regen_per_s: f32,
    /// Half size of the blocked footprint square in cells (OpenSA: 6x6 cells -> 3.0).
    pub half_extent: f32,
    /// Corner cells of the footprint square that stay walkable (rounded footprint).
    pub corner_cut: i32,
    pub turrets: Vec<TurretDef>,
    pub produces: Vec<String>,
    /// Multiplier on unit build time (Ant colonies: 0.75 faction bonus).
    pub build_time_multiplier: f32,
    pub exit_offset: Vec2,
    pub rally_offset: Vec2,
    pub model: String,
    pub bits: BitRules,
    pub source: String,
    /// Must be owned to win and blocks victory while neutral (OpenSA `Colony` trait: colonies,
    /// colony turrets, boosters). False for neutral creep structures such as popcorn plants.
    pub counts_for_victory: bool,
    /// Team-wide bonus granted to the owner (OpenSA boosters: +10 % firepower / -10 % breed time
    /// per structure).
    pub boost: Option<BoostKind>,
}

#[derive(Serialize, Deserialize, Clone, Copy, Debug, PartialEq, Eq)]
pub enum BoostKind {
    Firepower,
    Production,
}

impl Default for ColonyDef {
    fn default() -> Self {
        Self {
            name: String::new(),
            family: Family::Ant,
            hp: 100000.0,
            regen_per_s: 2500.0,
            half_extent: 3.0,
            corner_cut: 1,
            turrets: Vec::new(),
            produces: Vec::new(),
            build_time_multiplier: 1.0,
            exit_offset: Vec2::new(0.0, 3.6),
            rally_offset: Vec2::new(0.0, 6.0),
            model: String::new(),
            bits: BitRules::default(),
            source: String::new(),
            counts_for_victory: true,
            boost: None,
        }
    }
}

#[derive(Serialize, Deserialize, Clone, Debug)]
#[serde(default)]
pub struct Rules {
    /// Simulation ticks per second.
    pub tick_hz: f32,
    /// Max living units per team (assumption A3).
    pub unit_cap: u32,
    /// Idle units walk to colony bits within this many cells (OpenSA TakeColonyBitOnIdle).
    pub idle_bit_search_radius: f32,
    /// Seconds between auto-target scans.
    pub auto_target_interval: f32,
    /// Seconds a corpse stays on the ground.
    pub corpse_time: f32,
    /// Seconds between path re-plans while chasing.
    pub replan_interval: f32,
    /// Seconds a unit may make no progress before re-planning.
    pub stuck_time: f32,
    /// Separation strength for local crowd avoidance.
    pub separation_strength: f32,
    pub source: String,
}

impl Default for Rules {
    fn default() -> Self {
        Self {
            tick_hz: 30.0,
            unit_cap: 60,
            idle_bit_search_radius: 10.0,
            auto_target_interval: 0.25,
            corpse_time: 8.0,
            replan_interval: 0.6,
            stuck_time: 0.8,
            separation_strength: 6.0,
            source: "assumptions, see docs/GAMEPLAY_RESEARCH.md".into(),
        }
    }
}

#[derive(Serialize, Deserialize, Clone, Copy, Debug, PartialEq, Eq)]
pub enum TerrainKind {
    Clear,
    Rock,
    Vegetation,
    Water,
}

#[derive(Serialize, Deserialize, Clone, Debug)]
pub struct TerrainPatch {
    pub kind: TerrainKind,
    pub center: Vec2,
    pub radius: f32,
}

#[derive(Serialize, Deserialize, Clone, Debug)]
#[serde(default)]
pub struct Obstacle {
    /// Model/asset id (e.g. "rock_large", "grass_tuft", "flower").
    pub kind: String,
    pub pos: Vec2,
    pub radius: f32,
    pub yaw: f32,
    pub scale: f32,
    /// Blocks ground movement when true.
    pub blocking: bool,
}

impl Default for Obstacle {
    fn default() -> Self {
        Self { kind: "rock".into(), pos: Vec2::ZERO, radius: 0.5, yaw: 0.0, scale: 1.0, blocking: true }
    }
}

#[derive(Serialize, Deserialize, Clone, Debug)]
#[serde(default)]
pub struct ColonySpawn {
    pub colony: String,
    /// 0 = neutral.
    pub team: u8,
    pub pos: Vec2,
    pub produce: Option<String>,
    /// Start as an already-defeated colony that scatters bits (for testing capture).
    pub defeated: bool,
}

impl Default for ColonySpawn {
    fn default() -> Self {
        Self { colony: "colony_ant".into(), team: 0, pos: Vec2::ZERO, produce: None, defeated: false }
    }
}

#[derive(Serialize, Deserialize, Clone, Debug)]
#[serde(default)]
pub struct UnitSpawn {
    pub unit: String,
    pub team: u8,
    pub pos: Vec2,
    pub count: u32,
    pub spread: f32,
}

impl Default for UnitSpawn {
    fn default() -> Self {
        Self { unit: "ant_soldier".into(), team: 1, pos: Vec2::ZERO, count: 1, spread: 1.5 }
    }
}

#[derive(Serialize, Deserialize, Clone, Copy, Debug, PartialEq, Eq)]
pub enum Controller {
    Human,
    Bot,
    None,
}

#[derive(Serialize, Deserialize, Clone, Debug)]
#[serde(default)]
pub struct TeamDef {
    pub id: u8,
    pub name: String,
    /// "Y", "R", "G", "B" (original team colour letters) or "X" for neutral.
    pub color: String,
    pub controller: Controller,
    pub bot_profile: String,
}

impl Default for TeamDef {
    fn default() -> Self {
        Self { id: 1, name: "Yellow".into(), color: "Y".into(), controller: Controller::Human, bot_profile: "medium".into() }
    }
}

#[derive(Serialize, Deserialize, Clone, Debug)]
#[serde(default)]
pub struct MapRules {
    /// PROVISIONAL (docs/GAMEPLAY_RESEARCH.md A6): lets melee units damage colonies.
    pub melee_can_damage_colonies: bool,
    pub unit_cap: Option<u32>,
    /// Neutral flyers wander across the map when true (Stage 4).
    pub flyers: bool,
    /// Pirate ant holes spawn pirates (Stage 4).
    pub pirates: bool,
    pub flyer_kinds: Vec<String>,
    pub flyer_interval: f32,
    pub pirate_interval: f32,
    /// Seconds before bot teams start acting (OpenSA campaign scripts: 6 s on normal difficulty).
    pub bot_delay: f32,
}

impl Default for MapRules {
    fn default() -> Self {
        Self {
            melee_can_damage_colonies: false,
            unit_cap: None,
            flyers: false,
            pirates: false,
            flyer_kinds: Vec::new(),
            flyer_interval: 50.0,
            pirate_interval: 45.0,
            bot_delay: 0.0,
        }
    }
}

#[derive(Serialize, Deserialize, Clone, Debug)]
#[serde(default)]
pub struct MapDef {
    pub name: String,
    pub width: u32,
    pub height: u32,
    /// "normal", "desert", "swamp" or "candy" (ground palette).
    pub tileset: String,
    pub seed: u64,
    pub terrain: Vec<TerrainPatch>,
    pub obstacles: Vec<Obstacle>,
    pub colonies: Vec<ColonySpawn>,
    pub units: Vec<UnitSpawn>,
    pub teams: Vec<TeamDef>,
    pub rules: MapRules,
    pub description: String,
    /// Per-cell terrain, `height` rows of `width` characters (whitespace ignored): '.' clear,
    /// 'r' rock, 'v' vegetation, 'w' water. Applied before the `terrain` patches. Converted
    /// levels use this; hand-made maps may leave it out.
    pub cells: Option<String>,
    /// Initial camera focus in map cells (converted from the level's start camera).
    pub camera: Option<Vec2>,
    /// "campaign", "custom", "conquest" or "demo" (level list grouping).
    pub category: String,
    /// Campaign level number (1-100) used for ordering.
    pub number: Option<u32>,
    pub author: String,
    /// Original ground layout, `height` rows of `width` cells of three hex digits each: the
    /// tileset template id (two digits) and which quarter of its 48x48 picture covers the cell (one
    /// digit). Written by tools/add_ground_tiles.py; the pictures come from the player's own copy of
    /// the original game at run time.
    pub tiles: Option<String>,
}

impl Default for MapDef {
    fn default() -> Self {
        Self {
            name: "unnamed".into(),
            width: 64,
            height: 64,
            tileset: "normal".into(),
            seed: 1,
            terrain: Vec::new(),
            obstacles: Vec::new(),
            colonies: Vec::new(),
            units: Vec::new(),
            teams: Vec::new(),
            rules: MapRules::default(),
            description: String::new(),
            cells: None,
            camera: None,
            category: "demo".into(),
            number: None,
            author: String::new(),
            tiles: None,
        }
    }
}

/// Raw file contents of `units.ron`.
#[derive(Serialize, Deserialize, Clone, Debug, Default)]
pub struct UnitsFile {
    pub units: BTreeMap<String, UnitDef>,
    pub weapons: BTreeMap<String, WeaponDef>,
}

/// Raw file contents of `colonies.ron`.
#[derive(Serialize, Deserialize, Clone, Debug, Default)]
pub struct ColoniesFile {
    pub colonies: BTreeMap<String, ColonyDef>,
}

/// Raw file contents of `rules.ron`.
#[derive(Serialize, Deserialize, Clone, Debug, Default)]
pub struct RulesFile {
    pub rules: Rules,
}

/// Resolved definitions with stable indices (what the simulation uses at runtime).
#[derive(Serialize, Deserialize, Clone, Debug, Default)]
pub struct Defs {
    pub units: Vec<UnitDef>,
    pub unit_ids: Vec<String>,
    pub unit_index: HashMap<String, u16>,
    pub weapons: Vec<WeaponDef>,
    pub weapon_ids: Vec<String>,
    pub weapon_index: HashMap<String, u16>,
    pub colonies: Vec<ColonyDef>,
    pub colony_ids: Vec<String>,
    pub colony_index: HashMap<String, u16>,
    pub rules: Rules,
}

#[derive(Debug)]
pub enum DataError {
    Io(std::io::Error),
    Parse(String),
    Missing(String),
}

impl std::fmt::Display for DataError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            DataError::Io(e) => write!(f, "io error: {e}"),
            DataError::Parse(e) => write!(f, "parse error: {e}"),
            DataError::Missing(e) => write!(f, "missing definition: {e}"),
        }
    }
}

impl std::error::Error for DataError {}

impl From<std::io::Error> for DataError {
    fn from(e: std::io::Error) -> Self {
        DataError::Io(e)
    }
}

fn parse_ron<T: for<'de> Deserialize<'de>>(text: &str, what: &str) -> Result<T, DataError> {
    ron::from_str(strip_bom(text)).map_err(|e| DataError::Parse(format!("{what}: {e}")))
}

/// Text without a leading UTF-8 byte-order mark (Notepad and PowerShell add one when they save a
/// data file, and the RON parser rejects it).
pub fn strip_bom(text: &str) -> &str {
    text.strip_prefix('\u{feff}').unwrap_or(text)
}

impl Defs {
    pub fn from_files(units: UnitsFile, colonies: ColoniesFile, rules: Rules) -> Result<Self, DataError> {
        let mut d = Defs { rules, ..Default::default() };
        for (id, w) in units.weapons {
            d.weapon_index.insert(id.clone(), d.weapons.len() as u16);
            d.weapon_ids.push(id);
            d.weapons.push(w);
        }
        for (id, u) in units.units {
            if let Some(w) = &u.weapon
                && !d.weapon_index.contains_key(w)
            {
                return Err(DataError::Missing(format!("weapon '{w}' used by unit '{id}'")));
            }
            d.unit_index.insert(id.clone(), d.units.len() as u16);
            d.unit_ids.push(id);
            d.units.push(u);
        }
        for (id, c) in colonies.colonies {
            for t in &c.turrets {
                if !d.weapon_index.contains_key(&t.weapon) {
                    return Err(DataError::Missing(format!("turret weapon '{}' in colony '{id}'", t.weapon)));
                }
            }
            for p in &c.produces {
                if !d.unit_index.contains_key(p) {
                    return Err(DataError::Missing(format!("produced unit '{p}' in colony '{id}'")));
                }
            }
            d.colony_index.insert(id.clone(), d.colonies.len() as u16);
            d.colony_ids.push(id);
            d.colonies.push(c);
        }
        Ok(d)
    }

    /// Parse the three data files from strings (used by the game crate and tests).
    pub fn from_strs(units: &str, colonies: &str, rules: &str) -> Result<Self, DataError> {
        let u: UnitsFile = parse_ron(units, "units.ron")?;
        let c: ColoniesFile = parse_ron(colonies, "colonies.ron")?;
        let r: RulesFile = parse_ron(rules, "rules.ron")?;
        Self::from_files(u, c, r.rules)
    }

    /// Load `units.ron`, `colonies.ron` and `rules.ron` from a directory.
    pub fn load_dir(dir: &Path) -> Result<Self, DataError> {
        let u = std::fs::read_to_string(dir.join("units.ron"))?;
        let c = std::fs::read_to_string(dir.join("colonies.ron"))?;
        let r = std::fs::read_to_string(dir.join("rules.ron"))?;
        Self::from_strs(&u, &c, &r)
    }

    pub fn unit(&self, id: &str) -> Option<u16> {
        self.unit_index.get(id).copied()
    }

    pub fn weapon(&self, id: &str) -> Option<u16> {
        self.weapon_index.get(id).copied()
    }

    pub fn colony(&self, id: &str) -> Option<u16> {
        self.colony_index.get(id).copied()
    }
}

impl MapDef {
    pub fn from_str(text: &str) -> Result<Self, DataError> {
        parse_ron(text, "map")
    }

    pub fn load(path: &Path) -> Result<Self, DataError> {
        let t = std::fs::read_to_string(path)?;
        Self::from_str(&t)
    }
}
