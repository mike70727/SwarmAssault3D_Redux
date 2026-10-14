# Asset notes: what was modelled, what was inferred, what is uncertain

Every asset is produced by a repeatable `bpy` script (`blender/scripts/*.py`) that writes the
editable `.blend`, the exported `.glb` and the preview renders (`blender/previews/<asset>_*.jpg`
plus a `<asset>_sheet.jpg` contact sheet) and, since the realism pass, the baked textures in
`assets/textures/<asset>/`. See `blender/README.md` for how to run them.

General conventions (all assets): 1 unit = 1 map cell, Z up in Blender, rest pose faces −Y
(Bevy +Z), origin on the ground under the body centre, materials `M_Team` (team tint, replaced at
runtime), `M_Black` (true chitin black), `M_Dark` (team-darkened), `M_Accent` (metal), `M_Eye`,
`M_Wing` (translucent), colony `M_Colony` (team tint, lighter) / `M_Ground` / `M_Neutral`.
Walking units have IK-driven legs (coxa–femur–tibia) baked to FK clips; flyers have wing bones.
Clips: `idle`, `move` (or `fly` for flyers), `attack`, `death`; colonies `idle` + `turret_fire`.

Status: every entry below is **built, exported, previewed and loaded by the game** (the Bevy asset
loader reports each model and its clip names at start-up; see docs/TEST_REPORT.md).

## Realism pass (second iteration of every model)

The first versions were flat-shaded primitives and read as cartoons. Every model was rebuilt
through the same scripts with a realism layer in `salib.py` (switch it off with `SA_REALISM=0`):

* **Geometry** – every body part is Catmull-Clark subdivided once before joining (wings and
  planes excepted), box-like mechanical parts get bevelled edges instead, the joined mesh receives a
  faint procedural displacement and angle-based smooth shading. Colony mounds, towers and turrets
  go through the same step.
* **Procedural surfaces** (`salib.procedural_material`, kept in every `.blend` as `M_*_proc`
  materials with fake users so they can be edited and re-baked): chitin (broad colour variation,
  per-plate brightness, bulging Voronoi plates, fine grain, crevice dirt from an ambient-occlusion
  node, clear coat, slight subsurface), metal, glossy (eyes, stings), membrane (wings with
  Voronoi venation, translucent), fur (sheen + fine high-frequency bump: spiders, moth, fly), organic
  (mushrooms, flowers, grass), earth (colony mounds), wood (flying machine, scorpion gun), stone
  (rocks), petal, emissive (colony bits).
* **Team colour** – `M_Team`/`M_Colony` surfaces are neutral light grey multiplied by an RGB node
  named `TeamTint`; the bake sets it to white so the colour map carries only surface detail and the
  colour is exported as glTF `baseColorFactor`. The game replaces that factor with the owner's team
  colour while keeping the textures (`crates/sa_game/src/views.rs::tinted_material`).
* **Bakes** (Cycles, CPU) per exported object into `assets/textures/<asset>/<object>_{color,orm,normal}.jpg`:
  albedo with occlusion (sRGB JPEG), ORM (G = roughness, B = metallic, glTF layout; metallic is
  baked through a temporary emission pass), tangent-space normals (OpenGL +Y). Units 1024², colony
  bodies 1024² with 512² turrets/barrels, props 512². The textures are packed into the `.blend`
  files (self-contained) and embedded in the GLBs (JPEG, so the game enables Bevy's `jpeg` feature).
  Tangents are not exported; Bevy generates them for normal-mapped meshes.
* **Export materials** keep the `M_*` names (a second object of the same colony gets `M_Colony.001`,
  the game matches on the name before the dot) with the three textures wired to a Principled BSDF.
* Rigs, clips and conventions are unchanged; previews are rendered from the baked materials, so
  the contact sheets show exactly what the GLB contains.

Known limitations of the pass: UV layouts are automatic (smart projection, many islands), the
textures have no mip-maps in the game (Bevy loads glTF images without them, so the finest grain can
shimmer at the far zoom levels), and the surfaces are stylised interpretations of chitin rather than
scans.

## Interface chrome (`build_ui_chrome.py`)

The sidebar of the original was a pre-rendered 3-D panel, so ours is too: `build_ui_chrome.py`
builds the pieces in pixel units (1 Blender unit = 1 pixel, orthographic camera, Cycles with
denoising) and renders them at 2x before downsampling to `assets/ui/`:

* `sidebar.png` (226x1080): a displaced stone slab with a procedural granite material (dark
  brown-olive mottling, marbled streaks, reddish flecks), the bevelled steel pipe frame and
  dividers, the hexagonal emblem plate with its three honeycomb cells, the timer pill, the radar
  rim and screen at (13,108) 202x202, the pipe behind the button row, the bar rail with three
  slots and bolts, the LED loop and mount, and below the original 448 pixels a selection screen
  between two dividers. Positions follow OpenSA's `chrome.yaml` / `ingame-player.yaml`.
* `button.png` / `button_pressed.png` (50x50): the breeding buttons, raised brushed steel with a
  dark rim; the pressed one is flatter and darker.
* `dbutton_{normal,hover,pressed,disabled}.png` (160x32, 9-slice border 12): bronze dialog buttons.
* `dialog.png` (160x160, 9-slice border 30): stone frame with a pipe border and a dark green glass.
* `blackbar.png` (128x46, 9-slice border 20): the black command/message bar with a steel rim.
* `bar.png` / `bar_dim.png` (52x12): the red breeding bars (lit and idle).
* `led.png` / `led_red.png` / `led_off.png` (20x20).
* `emblem_<family>.png` (82x82): the faction insignia, a coloured plate in the original's shape
  (rounded square, circle with a shield ring, eight-point star with a web, hexagon with honeycomb
  cells, crumpled blob) with the family's light unit appended from its `.blend`, flattened and
  recoloured as a relief.
* `icon_<unit>.png` (128x128, `render_icons.py`): transparent top-down icons of the 21 units for
  the breeding buttons and the selection screen.
* `cursor_{arrow,attack,select}.png` (32x32, `tools/make_ui_art.py`): red pixel cursors.

Fonts: FreeSans Bold (`assets/fonts/`, GNU FreeFont, licence alongside).

## Ants (`build_ant.py`)

| Asset | From the references | Inferred / uncertain |
|---|---|---|
| ant_soldier | round head, two large curved mandibles that open in the attack frames, antennae, small thorax with six splayed legs, petiole, large oval gaster, all team-coloured with darker leg tips | leg joint layout and radius (sprites show 1-px legs), eye placement, body height, mandible thickness |
| ant_grenadier | same ant with a grey box pack and launcher tube on the thorax (grey square on the back in the sprites), smaller mandibles | pack shape (portrait shows a rounded grey pack), launcher orientation |
| ant_bazooka | same ant with a long grey tube along the right side of the body pointing forward over the head | tube length/diameter, mount block |
| neutral_bull_ant | black ant, 12 % larger, mandibles 35 % larger (prominent in sprite UNANTSOX) | exact size ratio |
| neutral_pirate_grenadier | black grenadier with pale-blue eyes (portrait) | – |

## Beetles (`build_beetle.py`)

| Asset | From the references | Inferred / uncertain |
|---|---|---|
| beetle_ladybug | team-coloured dome shell with seven black spots (positions taken from the top-down sprite), centre seam, small black head, short legs | underside, leg count hidden by the shell |
| beetle_shrapnel | dome with a black Y-shaped marking, grey launcher cylinder on top, long black legs | the Y is reconstructed from a 48-px sprite; launcher height |
| beetle_cannon | elongated ground-beetle body: long team-coloured elytra, black pronotum/head, long legs, grey cannon lying along the back with the barrel forward | barrel length (sprite shows a thin line), mount box |

## Spiders (`build_spider.py`)

| Asset | From the references | Inferred / uncertain |
|---|---|---|
| spider_black_widow | glossy black body, eight very long legs, team-coloured hourglass on top of the abdomen (yellow mark in sprite/portrait) | the hourglass is on top so it is visible from the game camera (real widows carry it underneath) |
| spider_sniper | brown hairy body, round team-coloured abdomen, long rifle with scope along the back | rifle details |
| spider_missile | black body, team-coloured abdomen, grey box launcher with two tubes on the back | launcher size |

## Scorpions (`build_scorpion.py`)

| Asset | From the references | Inferred / uncertain |
|---|---|---|
| scorpion_savage | team-coloured scorpion: two big claws (3 joints + movable finger), eight legs, 5-segment tail arching over the body, orange emissive sting | segment counts, claw proportions |
| scorpion_spear_gun | tail ends in a brown harpoon gun with a grey barrel instead of the sting (portrait) | gun shape |
| scorpion_ninja | black legs/claws (dark palette in the sprites), team body, light-grey star launcher on the tail | star launcher shape; the sprites show light-blue stars |

## Wasps (`build_flyers.py`)

| Asset | From the references | Inferred / uncertain |
|---|---|---|
| wasp_assault | black head/thorax, banded abdomen (team colour + black), two translucent wings, six tucked legs, antennae, small gun under the thorax | band count, wing shape (sprites show a blurred wing disc) |
| wasp_paralysis | 30 % longer abdomen, green-tipped arrow launcher (green dot in portrait) | – |
| wasp_sonic | stockier body, horn-shaped emitter at the front | – |

Wasps fly at 0.7 cells above ground; in OpenSA they are not air targets (ground weapons hit them),
which the data files reproduce (`flying: true, air: false`).

## Neutral flyers (`build_flyers.py`)

| Asset | From the references | Inferred / uncertain |
|---|---|---|
| neutral_dragonfly | long thin blue-grey segmented abdomen, four narrow wings, big green eyes | segment count |
| neutral_desert_fly | round grey fly, huge green compound eyes, two wings, dark legs | – |
| neutral_spawn_moth | furry tan body, two large patterned wings per side with dark eye-spots, feathery antennae | wing pattern simplified to spots |
| neutral_flying_machine | dark wooden hull, mast with a four-blade pink rotor, pirate-ant pilot, tail fin | hull shape (sprite is a dark blob under the pink rotor) |

## Colonies (`build_colony.py`)

Second iteration (the first versions were loose interpretations): every colony now follows the
layout of its 144-px original sprite (`Quick_References/Buildings/<Family>_Colony_Y/Colony_Body.png`,
24 px = 1 cell, oblique view), with the sprite's proportions read off the image.

| Asset | Sprite features reproduced | Still approximate |
|---|---|---|
| colony_ant | rocky dark mound with embedded boulders, three coiled team-coloured rings around it, two tall flat-topped cylinder towers (turrets on top), a curved ramp in the south-east | ring segments are full rings; rock texture is procedural |
| colony_beetle | spiky yellow ball: central ball with eight bulging vertical plates separated by dark grooves, seamed top plate with a rim, 26 long spikes all around and short spikes on top | the sprite's plates carry relief lines |
| colony_spider | pale striped mound wrapped by ten thick knobbly legs meeting at a crowned summit hub with a dark hole, two pale cylinder towers with hexagonal sniper turrets | legs are jointed tubes rather than smooth curves |
| colony_scorpion | armoured fortress: bevelled plated base, vaulted dark entrance with a grate under an arch, tall honeycomb back slab with three white slits, four spiked pillars, riveted claw-like plates with pincers on both sides | honeycomb is a procedural cell material, not geometry |
| colony_wasp | nine rimmed hexagonal cells of different heights with eggs in their sunken tops over a rocky base, a large slanted slab with four raised panels and a dark edge on the right | cell count and heights estimated from the sprite |

Orientation: the sprite coordinates (image down = south = simulation +y) are mirrored in Blender
(`join_into(..., mirror_y=True)`, outward normals recalculated) because Blender +Y exports to
glTF -Z, i.e. simulation -y. In-game close-ups: `docs/screenshots/colony2_*_ingame.jpg`.

Original (first iteration) notes follow.

| Asset | From the references | Inferred / uncertain |
|---|---|---|
| colony_ant | dark earth mound, yellow ribs/arches, ring-shaped entrance, two tall yellow towers with twin-barrel turrets, curved wall on the south-east | tower height, rib thickness; turret offsets read from the oblique 144-px sprite (±0.4 cells) |
| colony_beetle | big spiny dome with dark ribs, top plate and ring, one heavy cannon turret on top | spine count |
| colony_spider | dark mound wrapped by eight yellow leg-like tubes from the summit to the ground, summit cap with a hole, two pale towers with sniper turrets | leg curvature |
| colony_scorpion | blocky fortress: stacked pale blocks, a bar-cage dome, grey pipes, a dark grate, rivets, one twin spear turret | block arrangement is approximate |
| colony_wasp | cluster of hexagonal cells of different heights, slanted slab with raised panels, machine-gun turret on a pillar | cell layout |

Turret nodes are named `Turret_1`/`Turret_2` (child `Barrel` meshes) and are rotated by the game
from the simulation's turret yaw; the `turret_fire` clip is a 0.27 s barrel recoil.

## Level structures (`build_structures.py`)

Added for the converted levels (OpenSA actors that are not full colonies). All share the colony
conventions: static `ColonyBody`, rotating `Turret_1` with two barrels, clips `idle` + `turret_fire`.

| Asset | From the references | Inferred / uncertain |
|---|---|---|
| turret_ant / turret_beetle / turret_spider / turret_scorpion / turret_wasp | one-cell colony turrets of each family: the twin-barrel turret of the colony on a small base in the family's style (ribbed disc, spined dark disc, pale tower on four legs, blocky posts, hexagonal cell) | the OpenSA sprites were not in the reference pack; the bases are designed to match the colony models |
| turret_tesla | metal base, black pole with four coil rings, glowing blue-white sphere turret | entirely inferred from the name ("Tesla Coil Turret"); weapon values assumed |
| popcorn_plant | green stalk and leaves, golden husk, cluster of popcorn kernels as the "turret" (it shoots popcorn at everything nearby) | shape inferred from the OpenSA rules (neutral creep tower, 8 radial armaments) |
| booster_firepower / booster_production | 3x2-cell rock mound with glowing red crystals / green pods | inferred from the OpenSA descriptions ("increases firepower / production of all team units by 10 %") |

## Candy decorations (`build_candy.py`)

The candy tileset levels use OpenSA's `plant_jelly_bean`, `plant_gumnut`, `plant_choc_chip`,
`plant_smarty` and `plant_jaffa` decorations; they are modelled as glossy sweets (`candy_*`
props, about one cell, blocking like every OpenSA decoration).

## Environment (`build_environment.py`)

rock_large, rock_small (displaced icospheres), mushroom (stem, red cap with white dots, from
OBMUSHWH), flower (stem, leaves, six petals, from OBFLOWER), grass_tuft (nine blades, OBGRASS),
colony_bit (emissive golden gem, OpenSA colonybit sprite), ant_hole (sand ring with a dark hole,
ANTHOLE). Candy/plant hazards of the other tilesets are not modelled.
