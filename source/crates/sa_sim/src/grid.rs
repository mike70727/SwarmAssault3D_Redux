//! Navigation grid: blocked cells, terrain speed multipliers, line of sight and A* paths.

use std::cmp::Ordering;
use std::collections::BinaryHeap;

use glam::{IVec2, Vec2};
use serde::{Deserialize, Serialize};

use crate::data::TerrainKind;

#[derive(Serialize, Deserialize, Clone, Debug)]
pub struct NavGrid {
    pub w: i32,
    pub h: i32,
    blocked: Vec<bool>,
    terrain: Vec<TerrainKind>,
}

const DIRS: [(i32, i32, f32); 8] = [
    (1, 0, 1.0),
    (-1, 0, 1.0),
    (0, 1, 1.0),
    (0, -1, 1.0),
    (1, 1, std::f32::consts::SQRT_2),
    (1, -1, std::f32::consts::SQRT_2),
    (-1, 1, std::f32::consts::SQRT_2),
    (-1, -1, std::f32::consts::SQRT_2),
];

#[derive(Copy, Clone, PartialEq)]
struct Node {
    f: f32,
    idx: u32,
}

impl Eq for Node {}

impl Ord for Node {
    fn cmp(&self, other: &Self) -> Ordering {
        // min-heap on f
        other.f.partial_cmp(&self.f).unwrap_or(Ordering::Equal).then_with(|| other.idx.cmp(&self.idx))
    }
}

impl PartialOrd for Node {
    fn partial_cmp(&self, other: &Self) -> Option<Ordering> {
        Some(self.cmp(other))
    }
}

impl NavGrid {
    pub fn new(w: u32, h: u32) -> Self {
        let n = (w * h) as usize;
        Self { w: w as i32, h: h as i32, blocked: vec![false; n], terrain: vec![TerrainKind::Clear; n] }
    }

    #[inline]
    fn idx(&self, x: i32, y: i32) -> usize {
        (y * self.w + x) as usize
    }

    #[inline]
    pub fn in_bounds(&self, c: IVec2) -> bool {
        c.x >= 0 && c.y >= 0 && c.x < self.w && c.y < self.h
    }

    #[inline]
    pub fn cell_of(&self, p: Vec2) -> IVec2 {
        IVec2::new(p.x.floor() as i32, p.y.floor() as i32)
    }

    #[inline]
    pub fn center(&self, c: IVec2) -> Vec2 {
        Vec2::new(c.x as f32 + 0.5, c.y as f32 + 0.5)
    }

    pub fn size(&self) -> Vec2 {
        Vec2::new(self.w as f32, self.h as f32)
    }

    pub fn clamp(&self, p: Vec2) -> Vec2 {
        p.clamp(Vec2::splat(0.1), self.size() - 0.1)
    }

    /// Blocked for ground movement (out of bounds counts as blocked).
    #[inline]
    pub fn is_blocked(&self, c: IVec2) -> bool {
        !self.in_bounds(c) || self.blocked[self.idx(c.x, c.y)] || self.terrain[self.idx(c.x, c.y)] == TerrainKind::Water
    }

    #[inline]
    pub fn is_blocked_pos(&self, p: Vec2) -> bool {
        self.is_blocked(self.cell_of(p))
    }

    pub fn set_blocked(&mut self, c: IVec2, b: bool) {
        if self.in_bounds(c) {
            let i = self.idx(c.x, c.y);
            self.blocked[i] = b;
        }
    }

    pub fn block_circle(&mut self, center: Vec2, radius: f32) {
        let r = radius.max(0.0);
        let min = self.cell_of(center - r);
        let max = self.cell_of(center + r);
        for y in min.y..=max.y {
            for x in min.x..=max.x {
                let c = IVec2::new(x, y);
                if self.in_bounds(c) && (self.center(c) - center).length() <= r + 0.35 {
                    self.set_blocked(c, true);
                }
            }
        }
    }

    /// Block a square footprint of `half` cells around `center`, cutting `corner_cut` cells off
    /// each corner so the shape is roughly round like the colony sprites.
    pub fn block_square(&mut self, center: Vec2, half: f32, corner_cut: i32) {
        let min = self.cell_of(center - half + 0.01);
        let max = self.cell_of(center + half - 0.01);
        for y in min.y..=max.y {
            for x in min.x..=max.x {
                let dx = (x - min.x).min(max.x - x);
                let dy = (y - min.y).min(max.y - y);
                if dx + dy < corner_cut {
                    continue;
                }
                self.set_blocked(IVec2::new(x, y), true);
            }
        }
    }

    pub fn unblock_square(&mut self, center: Vec2, half: f32) {
        let min = self.cell_of(center - half + 0.01);
        let max = self.cell_of(center + half - 0.01);
        for y in min.y..=max.y {
            for x in min.x..=max.x {
                self.set_blocked(IVec2::new(x, y), false);
            }
        }
    }

    /// Load per-cell terrain from a text grid: `h` rows of `w` characters, whitespace ignored.
    /// '.' clear, 'r' rock, 'v' vegetation, 'w' water.
    pub fn set_cells(&mut self, text: &str) -> Result<(), String> {
        let chars: Vec<char> = text.chars().filter(|c| !c.is_whitespace()).collect();
        let n = (self.w * self.h) as usize;
        if chars.len() != n {
            return Err(format!("cells: expected {} characters ({}x{}), found {}", n, self.w, self.h, chars.len()));
        }
        for (i, c) in chars.iter().enumerate() {
            self.terrain[i] = match c {
                '.' => TerrainKind::Clear,
                'r' => TerrainKind::Rock,
                'v' => TerrainKind::Vegetation,
                'w' => TerrainKind::Water,
                other => return Err(format!("cells: unknown terrain character {other:?}")),
            };
        }
        Ok(())
    }

    pub fn terrain_kind(&self, c: IVec2) -> TerrainKind {
        if self.in_bounds(c) { self.terrain[self.idx(c.x, c.y)] } else { TerrainKind::Clear }
    }

    pub fn paint_terrain(&mut self, center: Vec2, radius: f32, kind: TerrainKind) {
        let min = self.cell_of(center - radius);
        let max = self.cell_of(center + radius);
        for y in min.y..=max.y {
            for x in min.x..=max.x {
                let c = IVec2::new(x, y);
                if self.in_bounds(c) && (self.center(c) - center).length() <= radius {
                    let i = self.idx(x, y);
                    self.terrain[i] = kind;
                }
            }
        }
    }

    pub fn terrain_at(&self, p: Vec2) -> TerrainKind {
        let c = self.cell_of(p);
        if self.in_bounds(c) { self.terrain[self.idx(c.x, c.y)] } else { TerrainKind::Clear }
    }

    /// Ground speed multiplier for a position (OpenSA locomotor: clear 100%, rock 75%, veg 50%).
    pub fn speed_mult(&self, p: Vec2) -> f32 {
        match self.terrain_at(p) {
            TerrainKind::Clear => 1.0,
            TerrainKind::Rock => 0.75,
            TerrainKind::Vegetation => 0.5,
            TerrainKind::Water => 0.0,
        }
    }

    /// Supercover line test: every cell touched by the segment a-b must be free.
    pub fn los(&self, a: Vec2, b: Vec2) -> bool {
        let d = b - a;
        let steps = ((d.x.abs().max(d.y.abs())) * 2.5).ceil().max(1.0) as i32;
        for i in 0..=steps {
            let t = i as f32 / steps as f32;
            let p = a + d * t;
            if self.is_blocked_pos(p) {
                return false;
            }
            // also test the cell corners around the sample so thin diagonals do not slip through
            let c = self.cell_of(p);
            let fx = p.x - p.x.floor();
            let fy = p.y - p.y.floor();
            if fx < 0.05 && self.is_blocked(c + IVec2::new(-1, 0)) {
                return false;
            }
            if fy < 0.05 && self.is_blocked(c + IVec2::new(0, -1)) {
                return false;
            }
        }
        true
    }

    /// Nearest free cell centre to `p` (spiral search), `p` itself if free.
    pub fn nearest_free(&self, p: Vec2) -> Vec2 {
        let c = self.cell_of(p);
        if !self.is_blocked(c) {
            return self.clamp(p);
        }
        for r in 1..((self.w.max(self.h)) as i32) {
            let mut best: Option<(f32, IVec2)> = None;
            for y in (c.y - r)..=(c.y + r) {
                for x in (c.x - r)..=(c.x + r) {
                    if (x - c.x).abs() != r && (y - c.y).abs() != r {
                        continue;
                    }
                    let cc = IVec2::new(x, y);
                    if !self.is_blocked(cc) {
                        let d = (self.center(cc) - p).length_squared();
                        if best.is_none_or(|(bd, _)| d < bd) {
                            best = Some((d, cc));
                        }
                    }
                }
            }
            if let Some((_, cc)) = best {
                return self.center(cc);
            }
        }
        self.clamp(p)
    }

    fn heuristic(a: IVec2, b: IVec2) -> f32 {
        let dx = (a.x - b.x).abs() as f32;
        let dy = (a.y - b.y).abs() as f32;
        (dx + dy) + (std::f32::consts::SQRT_2 - 2.0) * dx.min(dy)
    }

    /// A* over free cells with 8-connectivity and no corner cutting. Returns the cell list from
    /// `start` (exclusive) to `goal` (inclusive).
    pub fn astar(&self, start: IVec2, goal: IVec2, max_expansions: usize) -> Option<Vec<IVec2>> {
        if !self.in_bounds(start) || !self.in_bounds(goal) || self.is_blocked(goal) {
            return None;
        }
        if start == goal {
            return Some(vec![goal]);
        }
        let n = (self.w * self.h) as usize;
        let mut g = vec![f32::INFINITY; n];
        let mut came = vec![u32::MAX; n];
        let mut closed = vec![false; n];
        let si = self.idx(start.x, start.y) as u32;
        let gi = self.idx(goal.x, goal.y) as u32;
        g[si as usize] = 0.0;
        let mut open = BinaryHeap::new();
        open.push(Node { f: Self::heuristic(start, goal), idx: si });
        let mut expansions = 0usize;
        while let Some(Node { idx, .. }) = open.pop() {
            if closed[idx as usize] {
                continue;
            }
            closed[idx as usize] = true;
            if idx == gi {
                break;
            }
            expansions += 1;
            if expansions > max_expansions {
                return None;
            }
            let cx = idx as i32 % self.w;
            let cy = idx as i32 / self.w;
            for (dx, dy, cost) in DIRS {
                let nx = cx + dx;
                let ny = cy + dy;
                let nc = IVec2::new(nx, ny);
                if self.is_blocked(nc) {
                    continue;
                }
                if dx != 0 && dy != 0 && (self.is_blocked(IVec2::new(cx + dx, cy)) || self.is_blocked(IVec2::new(cx, cy + dy))) {
                    continue; // no corner cutting
                }
                let ni = self.idx(nx, ny);
                if closed[ni] {
                    continue;
                }
                let terrain_cost = match self.terrain[ni] {
                    TerrainKind::Clear => 1.0,
                    TerrainKind::Rock => 1.3,
                    TerrainKind::Vegetation => 1.9,
                    TerrainKind::Water => 1000.0,
                };
                let ng = g[idx as usize] + cost * terrain_cost;
                if ng < g[ni] {
                    g[ni] = ng;
                    came[ni] = idx;
                    open.push(Node { f: ng + Self::heuristic(nc, goal), idx: ni as u32 });
                }
            }
        }
        if came[gi as usize] == u32::MAX {
            return None;
        }
        let mut path = Vec::new();
        let mut cur = gi;
        while cur != si {
            path.push(IVec2::new(cur as i32 % self.w, cur as i32 / self.w));
            cur = came[cur as usize];
        }
        path.reverse();
        Some(path)
    }

    /// Plan a smoothed waypoint path (positions, excluding `from`) from `from` to `to`.
    /// Returns `None` when `to` is unreachable; the final waypoint is `to` itself if its cell is
    /// free, otherwise the nearest free cell centre.
    pub fn find_path(&self, from: Vec2, to: Vec2) -> Option<Vec<Vec2>> {
        let goal_pos = self.nearest_free(to);
        if self.los(from, goal_pos) {
            return Some(vec![goal_pos]);
        }
        let start = self.cell_of(self.nearest_free(from));
        let goal = self.cell_of(goal_pos);
        let cells = self.astar(start, goal, 20_000)?;
        let mut pts: Vec<Vec2> = cells.iter().map(|c| self.center(*c)).collect();
        if let Some(last) = pts.last_mut() {
            *last = goal_pos;
        }
        // string pulling: skip ahead as long as line of sight holds
        let mut out = Vec::with_capacity(pts.len());
        let mut cur = from;
        let mut i = 0;
        while i < pts.len() {
            let mut best = i;
            let mut j = i + 1;
            let limit = (i + 40).min(pts.len());
            while j < limit {
                if self.los(cur, pts[j]) {
                    best = j;
                }
                j += 1;
            }
            out.push(pts[best]);
            cur = pts[best];
            i = best + 1;
        }
        Some(out)
    }

    pub fn blocked_cells(&self) -> impl Iterator<Item = IVec2> + '_ {
        (0..self.h).flat_map(move |y| (0..self.w).map(move |x| IVec2::new(x, y))).filter(|c| self.blocked[self.idx(c.x, c.y)])
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn path_around_wall() {
        let mut g = NavGrid::new(20, 20);
        for y in 2..18 {
            g.set_blocked(IVec2::new(10, y), true);
        }
        let p = g.find_path(Vec2::new(2.5, 10.5), Vec2::new(17.5, 10.5)).expect("path");
        assert!(p.len() >= 2, "should route around the wall: {p:?}");
        assert_eq!(p.last().copied(), Some(Vec2::new(17.5, 10.5)));
        // every leg must have line of sight
        let mut cur = Vec2::new(2.5, 10.5);
        for w in &p {
            assert!(g.los(cur, *w), "leg {cur:?}->{w:?} crosses a wall");
            cur = *w;
        }
    }

    #[test]
    fn unreachable_goal() {
        let mut g = NavGrid::new(10, 10);
        for x in 0..10 {
            g.set_blocked(IVec2::new(x, 5), true);
        }
        assert!(g.find_path(Vec2::new(1.5, 1.5), Vec2::new(8.5, 8.5)).is_none());
    }

    #[test]
    fn straight_when_visible() {
        let g = NavGrid::new(10, 10);
        let p = g.find_path(Vec2::new(1.0, 1.0), Vec2::new(8.0, 8.0)).unwrap();
        assert_eq!(p, vec![Vec2::new(8.0, 8.0)]);
    }
}
