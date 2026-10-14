//! "Get the original art and sound": the 1999 game's pictures, animations and sounds, downloaded
//! when the player asks for them, the way OpenSA's content installer does it (its
//! `mods/sa/installer/downloads.yaml`): the archive OpenSA's mirror list points to, refused unless
//! it has the SHA-1 OpenSA pins, and only the data files of its `Game` and `Start` folders unpacked
//! into `original_game\Swarm Assault` next to the game, where `original::find` looks.
//!
//! Nothing of the original ships with Swarm Assault 3D Redux: the files only ever land on the
//! player's PC. The original is read once at start-up (`original::OriginalPlugin`), so the game
//! restarts itself to use them.

use std::io::Read;
use std::path::{Path, PathBuf};
use std::sync::{Arc, Mutex};
use std::time::Duration;

use bevy::prelude::*;

use crate::AppState;
use crate::ui::{DIM, UiAssets, dialog_button, shadow};

/// OpenSA's list of download mirrors (one address a line), at the revision its installer pins.
const MIRROR_LIST: &str = "https://gist.githubusercontent.com/Dzierzan/842bbd4f1beb35c3ba840373d615f118/raw/c350afb07edd4f4222502a5d9dc2936abb7945cc";
/// What that list held on 2026-10-14, tried when it cannot be read. Project Perfect Mod hosts the
/// archive for OpenSA: Banshee put it up at Dzierzan's request (PPM forum, "OpenSA - a recreation
/// of Swarm Assault game", 22 Dec 2020, the file's date on the server).
const MIRRORS: [&str; 2] = ["https://www.ppmsite.com/downloads/SwarmAssault.zip", "http://openra.baxxster.no/mods/SwarmAssault.zip"];
/// SHA-1 of the archive (OpenSA's downloads.yaml): any other file is refused.
const SHA1: &str = "e3f2e9231752a42581f15d52f090f7d96d716876";
/// Its size in bytes: the progress bar's 100%, and the most that is read.
const SIZE: u64 = 20_636_014;
/// The files taken from it (`original.rs` reads them); its intro and victory movies stay out.
/// `Game/Game.DDF` comes last: a folder that has it counts as a complete copy.
const FILES: [&str; 14] = [
    "Game/Game.ANI",
    "Game/Game.SDF",
    "Game/Game.MIN",
    "Game/Loading00.DDF",
    "Game/Loading01.DDF",
    "Game/Loading02.DDF",
    "Start/Start.DDF",
    "Start/Start.ANI",
    "Start/Start.SDF",
    "Start/Start.MIN",
    "Start/SwarmAssaultLogo.DDF",
    "Start/G5Logo.DDF",
    "Start/PublisherLogo.DDF",
    "Game/Game.DDF",
];

/// Where a download stands.
#[derive(Clone, Debug, Default, PartialEq)]
pub enum Phase {
    #[default]
    Idle,
    /// Reading the mirror list, or connecting to a mirror.
    Connecting,
    Downloading {
        got: u64,
        total: u64,
    },
    /// Checking the archive and writing the files.
    Unpacking,
    /// The files are in this folder; they are used from the next start.
    Done(PathBuf),
    Failed(String),
}

impl Phase {
    pub fn running(&self) -> bool {
        matches!(self, Phase::Connecting | Phase::Downloading { .. } | Phase::Unpacking)
    }
}

/// The download, shared with the thread that does it.
#[derive(Resource, Clone, Default)]
pub struct OriginalDownload(Arc<Mutex<Phase>>);

impl OriginalDownload {
    pub fn phase(&self) -> Phase {
        self.0.lock().unwrap_or_else(|e| e.into_inner()).clone()
    }

    /// Starts the download on its own thread (nothing happens while one is running).
    pub fn start(&self) {
        let mut phase = self.0.lock().unwrap_or_else(|e| e.into_inner());
        if phase.running() {
            return;
        }
        *phase = Phase::Connecting;
        let state = self.0.clone();
        let target = crate::user_path("original_game/Swarm Assault");
        info!("downloading the original game's art and sound into {}", shown(&target));
        std::thread::spawn(move || {
            let result = run(&state, &target);
            match &result {
                Ok(()) => info!("the original game's files are in {}", shown(&target)),
                Err(e) => warn!("downloading the original game failed: {e}"),
            }
            set(&state, result.map_or_else(Phase::Failed, |()| Phase::Done(target)));
        });
    }
}

fn set(state: &Mutex<Phase>, phase: Phase) {
    *state.lock().unwrap_or_else(|e| e.into_inner()) = phase;
}

/// A path as the player knows it (without Windows' `\\?\` prefix).
fn shown(p: &Path) -> String {
    let s = p.display().to_string();
    s.strip_prefix(r"\\?\").map(str::to_string).unwrap_or(s)
}

/// The site of a download address, for messages.
fn host(url: &str) -> &str {
    let rest = url.split_once("://").map_or(url, |(_, r)| r);
    rest.split('/').next().unwrap_or(rest)
}

/// Download, check and unpack into `target`, trying each mirror until one sends the right file.
fn run(state: &Mutex<Phase>, target: &Path) -> Result<(), String> {
    let agent: ureq::Agent = ureq::Agent::config_builder()
        .timeout_connect(Some(Duration::from_secs(20)))
        .timeout_recv_response(Some(Duration::from_secs(60)))
        .timeout_recv_body(Some(Duration::from_secs(900)))
        .user_agent(concat!("SwarmAssault3DRedux/", env!("CARGO_PKG_VERSION")))
        .build()
        .into();
    let mut mirrors = read_mirror_list(&agent);
    for m in MIRRORS {
        if !mirrors.iter().any(|x| x == m) {
            mirrors.push(m.to_string());
        }
    }
    let mut why = Vec::new();
    for url in &mirrors {
        set(state, Phase::Connecting);
        match fetch(&agent, url, state) {
            Ok(zip) if sha1_smol::Sha1::from(&zip).digest().to_string() == SHA1 => {
                set(state, Phase::Unpacking);
                return unpack_files(&zip, target);
            }
            Ok(_) => why.push(format!("{} sent a different file", host(url))),
            Err(e) => why.push(e),
        }
    }
    Err(why.join("; "))
}

fn read_mirror_list(agent: &ureq::Agent) -> Vec<String> {
    match agent.get(MIRROR_LIST).call().and_then(|mut r| r.body_mut().read_to_string()) {
        Ok(text) => parse_mirrors(&text),
        Err(e) => {
            warn!("could not read OpenSA's mirror list ({e}): trying the known mirrors");
            Vec::new()
        }
    }
}

/// The download addresses of a mirror list (one a line; anything else is skipped).
fn parse_mirrors(text: &str) -> Vec<String> {
    text.lines().map(str::trim).filter(|l| l.starts_with("https://") || l.starts_with("http://")).map(str::to_string).collect()
}

fn fetch(agent: &ureq::Agent, url: &str, state: &Mutex<Phase>) -> Result<Vec<u8>, String> {
    let site = host(url);
    let mut response = agent.get(url).call().map_err(|e| format!("{site}: {e}"))?;
    // ureq's limit refuses the read that finds the end of a body of exactly `limit` bytes, hence +1
    let mut body = response.body_mut().with_config().limit(SIZE + 1).reader();
    let mut zip = Vec::with_capacity(SIZE as usize);
    let mut buf = vec![0u8; 1 << 16];
    loop {
        let n = body.read(&mut buf).map_err(|e| format!("{site}: {e}"))?;
        if n == 0 {
            return Ok(zip);
        }
        zip.extend_from_slice(&buf[..n]);
        set(state, Phase::Downloading { got: zip.len() as u64, total: SIZE });
    }
}

/// One file of a zip archive, from the archive's central directory.
#[derive(Clone, Debug)]
struct ZipEntry {
    name: String,
    flags: u16,
    method: u16,
    crc: u32,
    packed: usize,
    size: usize,
    /// Offset of the file's local header.
    header: usize,
}

fn le16(d: &[u8], p: usize) -> Result<u16, String> {
    d.get(p..p + 2).map(|b| u16::from_le_bytes([b[0], b[1]])).ok_or_else(|| "the archive is cut short".to_string())
}

fn le32(d: &[u8], p: usize) -> Result<u32, String> {
    d.get(p..p + 4).map(|b| u32::from_le_bytes([b[0], b[1], b[2], b[3]])).ok_or_else(|| "the archive is cut short".to_string())
}

/// The files listed in a zip archive's central directory.
fn zip_entries(zip: &[u8]) -> Result<Vec<ZipEntry>, String> {
    // the end-of-central-directory record sits in the last 22 bytes, plus a comment of up to 64 KiB
    let lowest = zip.len().saturating_sub(22 + 0xFFFF);
    let eocd = (lowest..zip.len().saturating_sub(21)).rev().find(|&p| zip[p..p + 4] == [0x50, 0x4b, 0x05, 0x06]).ok_or("not a zip archive")?;
    let count = le16(zip, eocd + 10)? as usize;
    let mut p = le32(zip, eocd + 16)? as usize;
    let mut out = Vec::with_capacity(count);
    for _ in 0..count {
        if le32(zip, p)? != 0x0201_4b50 {
            return Err("the archive's file list is damaged".into());
        }
        let name_len = le16(zip, p + 28)? as usize;
        let skip = le16(zip, p + 30)? as usize + le16(zip, p + 32)? as usize;
        let name = zip.get(p + 46..p + 46 + name_len).ok_or("the archive is cut short")?;
        out.push(ZipEntry {
            name: String::from_utf8_lossy(name).into_owned(),
            flags: le16(zip, p + 8)?,
            method: le16(zip, p + 10)?,
            crc: le32(zip, p + 16)?,
            packed: le32(zip, p + 20)? as usize,
            size: le32(zip, p + 24)? as usize,
            header: le32(zip, p + 42)? as usize,
        });
        p += 46 + name_len + skip;
    }
    Ok(out)
}

/// A file's contents (stored or deflated), checked against its size and CRC-32.
fn read_entry(zip: &[u8], e: &ZipEntry) -> Result<Vec<u8>, String> {
    if e.flags & 1 != 0 {
        return Err(format!("{} is encrypted", e.name));
    }
    if le32(zip, e.header)? != 0x0403_4b50 {
        return Err(format!("{} is damaged", e.name));
    }
    let start = e.header + 30 + le16(zip, e.header + 26)? as usize + le16(zip, e.header + 28)? as usize;
    let packed = zip.get(start..start + e.packed).ok_or("the archive is cut short")?;
    let data = match e.method {
        0 => packed.to_vec(),
        8 => {
            let mut out = Vec::with_capacity(e.size);
            flate2::read::DeflateDecoder::new(packed).take(e.size as u64 + 1).read_to_end(&mut out).map_err(|err| format!("{} is damaged: {err}", e.name))?;
            out
        }
        m => return Err(format!("{} is packed with method {m}, which is not supported", e.name)),
    };
    let mut crc = flate2::Crc::new();
    crc.update(&data);
    if data.len() != e.size || crc.sum() != e.crc {
        return Err(format!("{} is damaged", e.name));
    }
    Ok(data)
}

/// Writes the original's data files (`FILES`) from the archive into `target`. Every file is read
/// and checked before the first one is written; each is written beside its place and then moved
/// there, so a cut-off write never leaves a half file under the real name.
fn unpack_files(zip: &[u8], target: &Path) -> Result<(), String> {
    let entries = zip_entries(zip)?;
    let mut files = Vec::with_capacity(FILES.len());
    for name in FILES {
        let e = entries.iter().find(|e| e.name.eq_ignore_ascii_case(name)).ok_or_else(|| format!("{name} is missing from the download"))?;
        files.push((name, read_entry(zip, e)?));
    }
    for (name, data) in files {
        let path = name.split('/').fold(target.to_path_buf(), |p, part| p.join(part));
        let dir = path.parent().unwrap_or(target);
        let part = dir.join(format!("{}.part", name.rsplit('/').next().unwrap_or(name)));
        std::fs::create_dir_all(dir)
            .and_then(|()| std::fs::write(&part, &data))
            .and_then(|()| std::fs::rename(&part, &path))
            .map_err(|e| format!("could not write {}: {e}", shown(&path)))?;
    }
    Ok(())
}

/// Starts a new copy of the game with the same arguments; the caller then quits this one.
pub fn restart() -> bool {
    let Ok(exe) = std::env::current_exe() else { return false };
    match std::process::Command::new(&exe).args(std::env::args_os().skip(1)).spawn() {
        Ok(_) => true,
        Err(e) => {
            error!("could not restart {}: {e}", exe.display());
            false
        }
    }
}

/// The main menu's download button (its label follows the download).
#[derive(Component)]
pub struct DownloadButton;

/// The line under it: what the button does, then the download's progress.
#[derive(Component)]
pub struct DownloadStatus;

/// Whether the game's own main menu (shown when no copy of the original was found) offers the
/// download: not when the player turned the original off with `SA_NO_ORIGINAL`.
pub fn offered() -> bool {
    !std::env::var("SA_NO_ORIGINAL").is_ok_and(|v| v != "0")
}

fn button_label(phase: &Phase) -> String {
    match phase {
        Phase::Idle => "Get the original art and sound  (20 MB download)".into(),
        Phase::Done(_) => "Restart the game to use them".into(),
        Phase::Failed(_) => "Try the download again".into(),
        _ => "Downloading the original art and sound...".into(),
    }
}

fn status_text(phase: &Phase) -> String {
    match phase {
        Phase::Idle => "None of the 1999 game's files come with Swarm Assault 3D Redux. This downloads its pictures and sounds \
                        (the archive OpenSA uses, from the same mirrors) into original_game\\Swarm Assault next to the game, on this PC only."
            .into(),
        Phase::Connecting => "Connecting to the download mirror...".into(),
        Phase::Downloading { got, total } => format!("Downloading...  {:.1} of {:.1} MB", *got as f64 / 1e6, *total as f64 / 1e6),
        Phase::Unpacking => "Checking the download and unpacking it...".into(),
        Phase::Done(dir) => format!("Done: the original's art and sound are in {}. The game uses them from its next start.", shown(dir)),
        Phase::Failed(e) => format!("The download did not work ({e}). Try again later, or copy your own Swarm Assault into original_game\\Swarm Assault next to the game."),
    }
}

/// The download button and its line, for the main menu's panel.
pub fn spawn_offer(panel: &mut ChildSpawnerCommands, ui: &UiAssets, download: &OriginalDownload) {
    let phase = download.phase();
    dialog_button(panel, ui, &button_label(&phase), 664.0, (crate::menu::MenuAction::GetOriginal, DownloadButton));
    panel.spawn((
        DownloadStatus,
        Text::new(status_text(&phase)),
        ui.text(12.0),
        TextColor(DIM),
        shadow(),
        TextLayout { justify: bevy::text::Justify::Center, ..default() },
        Node { max_width: px(664), margin: UiRect::bottom(px(4)), ..default() },
    ));
}

/// Keeps the button and its line in step with the download (text only changes when it differs).
fn update_offer(download: Res<OriginalDownload>, buttons: Query<&Children, With<DownloadButton>>, lines: Query<Entity, With<DownloadStatus>>, mut texts: Query<&mut Text>) {
    if buttons.is_empty() && lines.is_empty() {
        return;
    }
    let phase = download.phase();
    let (label, line) = (button_label(&phase), status_text(&phase));
    for children in &buttons {
        for child in children.iter() {
            if let Ok(mut t) = texts.get_mut(child)
                && t.0 != label
            {
                t.0 = label.clone();
            }
        }
    }
    for e in &lines {
        if let Ok(mut t) = texts.get_mut(e)
            && t.0 != line
        {
            t.0 = line.clone();
        }
    }
}

pub struct OriginalDownloadPlugin;

impl Plugin for OriginalDownloadPlugin {
    fn build(&self, app: &mut App) {
        app.init_resource::<OriginalDownload>().add_systems(Update, update_offer.run_if(in_state(AppState::Menu)));
    }
}

#[cfg(test)]
mod tests {
    use std::io::Write;

    use super::*;

    /// A zip archive of stored (`false`) or deflated (`true`) files, laid out the way zip tools
    /// write one.
    fn make_zip(files: &[(&str, &[u8], bool)]) -> Vec<u8> {
        let (mut out, mut central) = (Vec::new(), Vec::new());
        for (name, data, deflate) in files {
            let packed = if *deflate {
                let mut enc = flate2::write::DeflateEncoder::new(Vec::new(), flate2::Compression::default());
                enc.write_all(data).unwrap();
                enc.finish().unwrap()
            } else {
                data.to_vec()
            };
            let mut crc = flate2::Crc::new();
            crc.update(data);
            let method: u16 = if *deflate { 8 } else { 0 };
            let offset = out.len() as u32;
            let sizes = [crc.sum(), packed.len() as u32, data.len() as u32];
            out.extend_from_slice(&0x0403_4b50u32.to_le_bytes());
            out.extend_from_slice(&[20, 0, 0, 0]); // version needed, flags
            out.extend_from_slice(&method.to_le_bytes());
            out.extend_from_slice(&[0; 4]); // time, date
            sizes.iter().for_each(|v| out.extend_from_slice(&v.to_le_bytes()));
            out.extend_from_slice(&(name.len() as u16).to_le_bytes());
            out.extend_from_slice(&[0; 2]); // extra field length
            out.extend_from_slice(name.as_bytes());
            out.extend_from_slice(&packed);
            central.extend_from_slice(&0x0201_4b50u32.to_le_bytes());
            central.extend_from_slice(&[20, 0, 20, 0, 0, 0]); // made by, needed, flags
            central.extend_from_slice(&method.to_le_bytes());
            central.extend_from_slice(&[0; 4]); // time, date
            sizes.iter().for_each(|v| central.extend_from_slice(&v.to_le_bytes()));
            central.extend_from_slice(&(name.len() as u16).to_le_bytes());
            central.extend_from_slice(&[0; 12]); // extra, comment, disk, attributes
            central.extend_from_slice(&offset.to_le_bytes());
            central.extend_from_slice(name.as_bytes());
        }
        let at = out.len() as u32;
        out.extend_from_slice(&central);
        out.extend_from_slice(&0x0605_4b50u32.to_le_bytes());
        out.extend_from_slice(&[0; 4]); // disk numbers
        out.extend_from_slice(&(files.len() as u16).to_le_bytes());
        out.extend_from_slice(&(files.len() as u16).to_le_bytes());
        out.extend_from_slice(&(central.len() as u32).to_le_bytes());
        out.extend_from_slice(&at.to_le_bytes());
        out.extend_from_slice(&[0; 2]); // comment length
        out
    }

    fn scratch(name: &str) -> PathBuf {
        let dir = std::env::temp_dir().join(format!("sa3d_download_test_{}_{name}", std::process::id()));
        let _ = std::fs::remove_dir_all(&dir);
        dir
    }

    /// Every file under `dir`, as forward-slash paths relative to it.
    fn tree(dir: &Path) -> Vec<String> {
        let mut out = Vec::new();
        let mut stack = vec![dir.to_path_buf()];
        while let Some(d) = stack.pop() {
            for e in std::fs::read_dir(&d).into_iter().flatten().flatten() {
                if e.path().is_dir() {
                    stack.push(e.path());
                } else {
                    out.push(e.path().strip_prefix(dir).unwrap().to_string_lossy().replace('\\', "/"));
                }
            }
        }
        out.sort();
        out
    }

    #[test]
    fn reads_stored_and_deflated_files() {
        let big: Vec<u8> = (0..50_000u32).map(|i| (i % 251) as u8).collect();
        let zip = make_zip(&[("readme.txt", b"hello", false), ("Game/Game.SDF", &big, true)]);
        let entries = zip_entries(&zip).unwrap();
        assert_eq!(entries.iter().map(|e| e.name.as_str()).collect::<Vec<_>>(), ["readme.txt", "Game/Game.SDF"]);
        assert_eq!(read_entry(&zip, &entries[0]).unwrap(), b"hello");
        assert_eq!(entries[1].method, 8);
        assert!(entries[1].packed < big.len(), "the test file should really be compressed");
        assert_eq!(read_entry(&zip, &entries[1]).unwrap(), big);
    }

    #[test]
    fn a_damaged_file_is_refused() {
        let mut zip = make_zip(&[("a.txt", b"hello world", false)]);
        let at = zip.windows(5).position(|w| w == b"hello").unwrap();
        zip[at] = b'j';
        let entries = zip_entries(&zip).unwrap();
        assert!(read_entry(&zip, &entries[0]).is_err());
        assert!(zip_entries(b"not a zip at all").is_err());
        assert!(zip_entries(&zip[..zip.len() - 30]).is_err(), "a cut-off archive");
    }

    #[test]
    fn unpacks_the_data_files_and_nothing_else() {
        let mut files: Vec<(String, Vec<u8>, bool)> = FILES.iter().map(|f| (f.to_string(), format!("data of {f}").into_bytes(), true)).collect();
        files.push(("Movies/G5Logo.avi".into(), b"a movie".to_vec(), false));
        files.push(("../outside.txt".into(), b"must not be written".to_vec(), false));
        files.push(("Game/.directory".into(), b"[Dolphin]".to_vec(), false));
        let refs: Vec<(&str, &[u8], bool)> = files.iter().map(|(n, d, z)| (n.as_str(), d.as_slice(), *z)).collect();
        let zip = make_zip(&refs);
        let dir = scratch("unpack");
        let target = dir.join("original_game").join("Swarm Assault");
        unpack_files(&zip, &target).unwrap();
        let mut want: Vec<String> = FILES.iter().map(|f| f.to_string()).collect();
        want.sort();
        assert_eq!(tree(&target), want, "exactly the data files, no movies, no leftover .part files");
        assert_eq!(tree(&dir).len(), FILES.len(), "nothing written outside the target folder");
        assert_eq!(std::fs::read(target.join("Game").join("Game.DDF")).unwrap(), b"data of Game/Game.DDF");
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn nothing_is_written_when_a_file_is_missing() {
        let files: Vec<(&str, &[u8], bool)> = FILES.iter().filter(|f| **f != "Start/Start.SDF").map(|f| (*f, f.as_bytes(), false)).collect();
        let zip = make_zip(&files);
        let dir = scratch("missing");
        let err = unpack_files(&zip, &dir).unwrap_err();
        assert!(err.contains("Start/Start.SDF"), "{err}");
        assert!(tree(&dir).is_empty());
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn mirror_list_keeps_only_web_addresses() {
        let list = "https://www.ppmsite.com/downloads/SwarmAssault.zip\r\n\r\n# a note\n  http://openra.baxxster.no/mods/SwarmAssault.zip  \nfile:///etc/passwd\n";
        assert_eq!(parse_mirrors(list), ["https://www.ppmsite.com/downloads/SwarmAssault.zip", "http://openra.baxxster.no/mods/SwarmAssault.zip"]);
        assert_eq!(host("https://www.ppmsite.com/downloads/SwarmAssault.zip"), "www.ppmsite.com");
    }

    #[test]
    fn the_last_file_written_is_the_one_the_game_looks_for() {
        assert_eq!(FILES.last(), Some(&"Game/Game.DDF"));
    }

    /// The real thing: downloads the 20.6 MB archive from the mirrors into a scratch folder (or
    /// `SA_DOWNLOAD_TEST_DIR`) and checks the game finds and opens the result.
    /// `cargo test -p swarm_assault_3d -- --ignored real_download`
    #[test]
    #[ignore]
    fn real_download() {
        let dir = std::env::var("SA_DOWNLOAD_TEST_DIR").map(PathBuf::from).unwrap_or_else(|_| scratch("real"));
        let target = dir.join("original_game").join("Swarm Assault");
        let state = Mutex::new(Phase::Idle);
        let t = std::time::Instant::now();
        run(&state, &target).unwrap();
        println!("downloaded and unpacked in {:.1} s into {}", t.elapsed().as_secs_f32(), target.display());
        let mut want: Vec<String> = FILES.iter().map(|f| f.to_string()).collect();
        want.sort();
        assert_eq!(tree(&target), want);
        assert_eq!(std::fs::metadata(target.join("Game").join("Game.DDF")).unwrap().len(), 9_114_936);
        let game = crate::original::Ddf::open(&target.join("Game").join("Game.DDF")).expect("Game.DDF opens");
        assert!(game.names().count() > 1000, "Game.DDF holds the game's pictures");
    }
}
