//! Every map file in assets/data/maps must parse, build a world (all colony/unit/model ids resolve)
//! and run for a while without panicking; the human team must own something at the start.

use std::path::PathBuf;

use sa_sim::{Controller, Defs, MapDef, World};

fn assets() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../assets")
}

#[test]
fn every_level_loads_and_runs() {
    let defs = Defs::load_dir(&assets().join("data")).expect("data files");
    let dir = assets().join("data/maps");
    let mut files: Vec<PathBuf> = std::fs::read_dir(&dir).unwrap().flatten().map(|e| e.path()).filter(|p| p.extension().and_then(|x| x.to_str()) == Some("ron")).collect();
    files.sort();
    assert!(files.len() >= 120, "expected the converted level set, found {} maps", files.len());
    let mut campaign = 0;
    for p in &files {
        let text = std::fs::read_to_string(p).unwrap();
        let map = MapDef::from_str(&text).unwrap_or_else(|e| panic!("{}: {e}", p.display()));
        if map.category == "campaign" {
            campaign += 1;
            assert!(map.number.is_some(), "{}: campaign level without number", p.display());
            assert!(map.cells.is_some(), "{}: converted level without cell terrain", p.display());
        }
        let mut w = World::new(defs.clone(), map).unwrap_or_else(|e| panic!("{}: {e}", p.display()));
        let human = w.teams.iter().find(|t| t.def.controller == Controller::Human).map(|t| t.def.id).unwrap_or_else(|| panic!("{}: no human team", p.display()));
        let owns = w.colonies.iter().any(|c| c.team == human) || w.living_units().any(|u| u.team == human);
        assert!(owns, "{}: the human team starts with nothing", p.display());
        // something to fight: an enemy team, or (levels like 003 "Take Neutral Colony") a colony that
        // is not ours yet
        let enemies = w.teams.iter().skip(1).filter(|t| t.def.id != human && t.def.controller != Controller::None).count();
        let foreign = w.colonies.iter().any(|c| c.team != human);
        assert!(enemies >= 1 || foreign, "{}: nothing to fight or capture", p.display());
        for _ in 0..120 {
            w.step();
        }
        assert!(!w.game_over, "{}: the game ended within 4 s of simulated time", p.display());
    }
    assert_eq!(campaign, 100, "all 100 campaign levels present");
}
