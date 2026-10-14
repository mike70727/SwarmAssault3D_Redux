//! Settings dialog (main menu and in-game options): sound volume slider, sound on/off, fullscreen
//! and vsync toggles. Changes apply at once and are written back to `assets/data/settings.ron`.

use bevy::prelude::*;
use bevy::ui::RelativeCursorPosition;
use bevy::ui_widgets::Activate;
use bevy::window::{MonitorSelection, PresentMode, PrimaryWindow, WindowMode};

use crate::AppState;
use crate::audio::AudioLibrary;
use crate::settings::Settings;
use crate::ui::{DIM, GOLD, TEXT, UiAssets, dialog_button, dialog_panel, shadow};

#[derive(Component)]
pub struct SettingsOverlay;

#[derive(Component, Clone, Copy)]
enum SettingsAction {
    VolumeDown,
    VolumeUp,
    ToggleSound,
    ToggleFullscreen,
    ToggleVsync,
    Close,
}

#[derive(Component)]
struct VolumeTrack;
#[derive(Component)]
struct VolumeFill;
#[derive(Component)]
struct VolumeText;

/// Set by the console's "settings" command (automated screenshots).
#[derive(Resource, Default)]
pub struct SettingsRequest(pub bool);

pub struct SettingsMenuPlugin;

impl Plugin for SettingsMenuPlugin {
    fn build(&self, app: &mut App) {
        app.init_resource::<SettingsRequest>()
            .add_systems(Update, (settings_request, volume_track_click, settings_escape, apply_settings))
            .add_systems(OnExit(AppState::InGame), close_on_exit)
            .add_systems(OnExit(AppState::Menu), close_on_exit)
            .add_observer(on_settings);
    }
}

/// Opens the dialog over whatever is on screen (menu or paused game).
pub fn open_settings(commands: &mut Commands, ui: &UiAssets, settings: &Settings) {
    let on = |b: bool| if b { "ON" } else { "OFF" };
    commands
        .spawn((
            SettingsOverlay,
            Node { position_type: PositionType::Absolute, width: percent(100), height: percent(100), justify_content: JustifyContent::Center, align_items: AlignItems::Center, ..default() },
            BackgroundColor(Color::srgba(0.0, 0.0, 0.0, 0.45)),
            GlobalZIndex(13),
        ))
        .with_children(|p| {
            p.spawn(dialog_panel(ui)).with_children(|panel| {
                panel.spawn((Text::new("SETTINGS"), ui.text(30.0), TextColor(GOLD), shadow(), Node { margin: UiRect::bottom(px(10)), ..default() }));
                panel.spawn((Text::new("Sound volume"), ui.text(14.0), TextColor(TEXT), shadow()));
                panel.spawn(Node { flex_direction: FlexDirection::Row, align_items: AlignItems::Center, column_gap: px(6), margin: UiRect::bottom(px(8)), ..default() }).with_children(|row| {
                    dialog_button(row, ui, "-", 44.0, SettingsAction::VolumeDown);
                    row.spawn((
                        VolumeTrack,
                        RelativeCursorPosition::default(),
                        Node { width: px(220), height: px(16), border: UiRect::all(px(1)), padding: UiRect::all(px(1)), ..default() },
                        BackgroundColor(Color::srgb(0.03, 0.03, 0.03)),
                        BorderColor::all(Color::srgb(0.55, 0.52, 0.46)),
                    ))
                    .with_children(|track| {
                        track.spawn((VolumeFill, ImageNode { image: ui.bar.clone(), image_mode: NodeImageMode::Stretch, ..default() }, Node { width: percent(settings.master_volume * 100.0), height: percent(100), ..default() }));
                    });
                    dialog_button(row, ui, "+", 44.0, SettingsAction::VolumeUp);
                    row.spawn((VolumeText, Text::new(format!("{:.0} %", settings.master_volume * 100.0)), ui.text(14.0), TextColor(TEXT), shadow(), Node { width: px(50), ..default() }));
                });
                dialog_button(panel, ui, &format!("Sound: {}", on(settings.sound_enabled)), 300.0, SettingsAction::ToggleSound);
                dialog_button(panel, ui, &format!("Fullscreen: {}", on(settings.fullscreen)), 300.0, SettingsAction::ToggleFullscreen);
                dialog_button(panel, ui, &format!("VSync: {}", on(settings.vsync)), 300.0, SettingsAction::ToggleVsync);
                panel.spawn((Text::new("Saved to assets/data/settings.ron (resolution and shadows are set there)"), ui.text(11.0), TextColor(DIM), shadow(), Node { margin: UiRect::axes(px(0), px(6)), ..default() }));
                dialog_button(panel, ui, "Close  (Esc)", 300.0, SettingsAction::Close);
            });
        });
}

fn close_on_exit(mut commands: Commands, overlays: Query<Entity, With<SettingsOverlay>>) {
    close_settings(&mut commands, &overlays);
}

pub fn close_settings(commands: &mut Commands, overlays: &Query<Entity, With<SettingsOverlay>>) {
    for e in overlays.iter() {
        commands.entity(e).despawn();
    }
}

fn on_settings(ev: On<Activate>, actions: Query<&SettingsAction>, mut settings: ResMut<Settings>, overlays: Query<Entity, With<SettingsOverlay>>, mut commands: Commands) {
    let Ok(action) = actions.get(ev.entity) else { return };
    match action {
        SettingsAction::VolumeDown => settings.master_volume = ((settings.master_volume * 10.0).round() / 10.0 - 0.1).clamp(0.0, 1.0),
        SettingsAction::VolumeUp => settings.master_volume = ((settings.master_volume * 10.0).round() / 10.0 + 0.1).clamp(0.0, 1.0),
        SettingsAction::ToggleSound => settings.sound_enabled = !settings.sound_enabled,
        SettingsAction::ToggleFullscreen => settings.fullscreen = !settings.fullscreen,
        SettingsAction::ToggleVsync => settings.vsync = !settings.vsync,
        SettingsAction::Close => close_settings(&mut commands, &overlays),
    }
}

/// Clicking (or dragging) on the volume track sets the volume directly.
fn volume_track_click(buttons: Res<ButtonInput<MouseButton>>, tracks: Query<&RelativeCursorPosition, With<VolumeTrack>>, mut settings: ResMut<Settings>) {
    if !buttons.pressed(MouseButton::Left) {
        return;
    }
    for rel in &tracks {
        // Bevy measures the cursor from the track's centre (-0.5..0.5): shift it to 0..1
        if let Some(n) = rel.normalized.map(|n| n + Vec2::splat(0.5))
            && (0.0..=1.0).contains(&n.y)
            && (-0.02..=1.02).contains(&n.x)
        {
            let v = (n.x.clamp(0.0, 1.0) * 20.0).round() / 20.0;
            if (v - settings.master_volume).abs() > 0.001 {
                settings.master_volume = v;
            }
        }
    }
}

fn settings_escape(keys: Res<ButtonInput<KeyCode>>, controls: Res<crate::controls::Controls>, overlays: Query<Entity, With<SettingsOverlay>>, mut commands: Commands) {
    if !overlays.is_empty() && controls.just_pressed(&keys, "menu") {
        close_settings(&mut commands, &overlays);
    }
}

fn settings_request(mut request: ResMut<SettingsRequest>, overlays: Query<Entity, With<SettingsOverlay>>, mut commands: Commands, ui: Res<UiAssets>, settings: Res<Settings>) {
    if std::mem::take(&mut request.0) && overlays.is_empty() {
        open_settings(&mut commands, &ui, &settings);
    }
}

/// Applies changed settings (audio, window), saves the file and refreshes the dialog's labels.
#[allow(clippy::type_complexity, clippy::too_many_arguments)]
fn apply_settings(
    settings: Res<Settings>,
    lib: Option<ResMut<AudioLibrary>>,
    mut windows: Query<&mut Window, With<PrimaryWindow>>,
    mut fill: Query<&mut Node, With<VolumeFill>>,
    mut texts: ParamSet<(Query<&mut Text, With<VolumeText>>, Query<(&SettingsAction, &Children)>, Query<&mut Text>)>,
    mut last_saved: Local<Option<(u32, bool, bool, bool)>>,
) {
    if !settings.is_changed() {
        return;
    }
    if let Some(mut lib) = lib {
        lib.master_volume = settings.master_volume;
        lib.enabled = settings.sound_enabled;
    }
    for mut w in &mut windows {
        let mode = if settings.fullscreen { WindowMode::BorderlessFullscreen(MonitorSelection::Current) } else { WindowMode::Windowed };
        if w.mode != mode {
            w.mode = mode;
        }
        let present = if settings.vsync { PresentMode::AutoVsync } else { PresentMode::AutoNoVsync };
        if w.present_mode != present {
            w.present_mode = present;
        }
    }
    let key = ((settings.master_volume * 100.0).round() as u32, settings.sound_enabled, settings.fullscreen, settings.vsync);
    if *last_saved != Some(key) {
        if last_saved.is_some() {
            settings.save();
        }
        *last_saved = Some(key);
    }
    for mut n in &mut fill {
        n.width = percent(settings.master_volume * 100.0);
    }
    let vol_label = format!("{:.0} %", settings.master_volume * 100.0);
    for mut t in texts.p0().iter_mut() {
        t.0 = vol_label.clone();
    }
    let on = |b: bool| if b { "ON" } else { "OFF" };
    let labels: Vec<(Entity, String)> = texts
        .p1()
        .iter()
        .filter_map(|(a, children)| {
            let label = match a {
                SettingsAction::ToggleSound => format!("Sound: {}", on(settings.sound_enabled)),
                SettingsAction::ToggleFullscreen => format!("Fullscreen: {}", on(settings.fullscreen)),
                SettingsAction::ToggleVsync => format!("VSync: {}", on(settings.vsync)),
                _ => return None,
            };
            children.first().map(|c| (*c, label))
        })
        .collect();
    for (e, label) in labels {
        if let Ok(mut t) = texts.p2().get_mut(e) {
            t.0 = label;
        }
    }
}
