# Blender asset pipeline

All models, rigs, animations, exports and preview renders are produced by repeatable Python
scripts. They run inside Blender (GUI: *Scripting* workspace → run script) or headless through the
`bpy` wheel, which is what was used for the committed assets (Blender 5.2.2 LTS):

```bash
python3 -m venv .venv-bpy
.venv-bpy/bin/pip install bpy==5.2.2 pillow
.venv-bpy/bin/python blender/scripts/build_ant.py ant_soldier
.venv-bpy/bin/python blender/scripts/build_colony.py colony_ant
```

The colonies in the game come from Tripo models instead (`colony_tripo.py`, notes in
`docs/ASSET_NOTES.md`): `blender -b --factory-startup --python blender/scripts/colony_tripo.py --
colony_spider --src <tripo model.obj>` (`--fit-only` for the sprite fit alone).

Each build writes:

| Output | Path |
|---|---|
| editable source | `blender/blend/<asset>.blend` (IK rigs keep the `_ik` actions; baked FK clips are on NLA tracks) |
| game asset | `assets/models/<asset>.glb` (+Y up, named clips `idle`/`move`/`attack`/`death`, materials `M_*`) |
| previews | `blender/previews/<asset>_{front,back,left,right,threequarter}.jpg` and `<asset>_sheet.jpg` |
| textures | `assets/textures/<asset>/<object>_{color,orm,normal}.jpg` (baked, also packed into the `.blend` and embedded in the GLB) |

`salib.py` holds the shared conventions (scale, axes, materials, leg rigs, walk cycles, baking,
export settings). `_selftest_salib.py` is a quick smoke test of the pipeline (IK bake + 4-clip export).

## Realism pass

`salib.finalize_asset` runs the realism layer before export: procedural PBR materials
(`procedural_material`, kinds chitin / metal / glossy / membrane / fur / organic / earth / wood /
stone / petal / emissive), one level of subdivision per body part plus bevels on boxes and a faint
displacement (`Body.join`, `detail_object`, `bevel_object`), smart-projected UVs and Cycles bakes of
colour, ORM and tangent normals (`bake_object_textures`), then image-based export materials that keep
the `M_*` names (`build_baked_materials`). The procedural originals stay in the `.blend` as
`M_*_proc`; edit them and run the script again to re-bake. `SA_REALISM=0` rebuilds the original
flat-shaded models. A full unit takes about 2.5 minutes on 4 CPU cores (bake 32 samples at 1024²,
five 64-sample previews); the `.blend` files need Blender 4.2 or newer (5.2 was used).

Headless rendering needs Mesa (`libegl1 libgl1 libosmesa6`) on Linux; Cycles runs on the CPU.
