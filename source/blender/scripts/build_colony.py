"""Builds the five faction colonies: colony_ant, colony_beetle, colony_spider, colony_scorpion,
colony_wasp.

Fourth iteration (model crew, second shift).  Every layout below is fitted to the original 144-px
colony sprites (reference/models/colony_<family>/colony_body_<team>.png, 24 px = 1 cell), which are
orthographic renders from the south at ~60 deg elevation (tower-top rims 24 x 21 px; the ant's rope
rings have aspect 0.87).  With the frame centre = colony centre a point projects to the sprite as
    u = X,   v (down) = -(0.866 Y + 0.5 Z)        (cells; Blender X east, Y north, Z up)
so a sprite feature fixes 0.866 Y + 0.5 Z; heights come from second constraints (ring radii, feet on
the ground, wall faces) and from the original 3-D renders of the loading screens (reference/models/
_common: ant = loading 0 top, spider = loading 1 bottom-left, beetle = loading 2 bottom).
Turret positions: OpenSA's Turreted offsets (forward F, right R in WDist) map to the sprite as
u = R/1024, v = -0.632 F/1024 (calibrated on the four measured ant/spider tower tops); that puts the
beetle turret on its cap (top 1.72), the scorpion turret on the honeycomb-topped tower and the wasp
turret on the big west cell.  colonies.ron offsets = (pivot x, -pivot y), height = barrel axis z.

Shared contract: origin at the centre of the 6x6 footprint on the ground, Z up, the turret objects
Turret_1.. have their origin on the yaw axis at the tower top, barrels point -Y (sim south) at
rest; `idle` clip on the body, `turret_fire` (recoil) on the <Turret>_Barrels children.
Team-coloured parts use M_Colony (and M_Colony.<variant> - the game tints by the name before the
dot); their textures bake light grey, the colour is the glTF factor replaced at runtime
(M_Colony.dark / .tower are darkened bakes = a darker shade of the team colour).

Usage: blender -b --factory-startup --python build_colony.py -- colony_ant [colony_beetle ...]
       flags: --all (every colony), --quick (no bake/export: only the sprite-view check renders).
Set SA_COLONY_QA_DIR to a folder to get, per colony, <name>_spriteview.png (with turrets),
<name>_spriteview_body.png (body only, transparent: silhouette overlay against the body sprite) and a
side-by-side sprite/model image (SA_COLONY_REF_DIR = the folder holding colony_<family>/colony_body_Y.png).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import salib  # noqa: E402
from colony_ant import build_ant_colony  # noqa: E402
from colony_beetle import build_beetle_colony  # noqa: E402
from colony_scorpion import build_scorpion_colony  # noqa: E402
from colony_spider import build_spider_colony  # noqa: E402
from colony_wasp import build_wasp_colony  # noqa: E402

BUILDERS = {
    "colony_ant": build_ant_colony,
    "colony_beetle": build_beetle_colony,
    "colony_spider": build_spider_colony,
    "colony_scorpion": build_scorpion_colony,
    "colony_wasp": build_wasp_colony,
}

if __name__ == "__main__":
    flags = [a for a in salib.script_args() if a.startswith("-")]
    args = [a for a in salib.script_args() if not a.startswith("-")] or (list(BUILDERS) if "--all" in flags else ["colony_ant"])
    quick = "--quick" in flags
    for a in args:
        if a not in BUILDERS:
            raise SystemExit(f"unknown colony {a}; choose from {list(BUILDERS)}")
        BUILDERS[a](quick=quick)
        print("BUILT", a, "(quick)" if quick else "", flush=True)
