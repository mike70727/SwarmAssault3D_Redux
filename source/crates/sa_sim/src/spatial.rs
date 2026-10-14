//! Uniform spatial hash for neighbour queries (rebuilt every tick).

use std::collections::HashMap;

use glam::Vec2;

#[derive(Debug, Clone)]
pub struct SpatialHash {
    cell: f32,
    cells: HashMap<(i32, i32), Vec<u32>>,
}

impl Default for SpatialHash {
    fn default() -> Self {
        Self::new(2.0)
    }
}

impl SpatialHash {
    pub fn new(cell: f32) -> Self {
        Self { cell: cell.max(0.25), cells: HashMap::new() }
    }

    pub fn clear(&mut self) {
        for v in self.cells.values_mut() {
            v.clear();
        }
    }

    #[inline]
    fn key(&self, p: Vec2) -> (i32, i32) {
        ((p.x / self.cell).floor() as i32, (p.y / self.cell).floor() as i32)
    }

    pub fn insert(&mut self, p: Vec2, id: u32) {
        self.cells.entry(self.key(p)).or_default().push(id);
    }

    /// Push the ids of every entry whose cell intersects the circle (callers filter by distance).
    pub fn query(&self, p: Vec2, radius: f32, out: &mut Vec<u32>) {
        let min = self.key(p - radius);
        let max = self.key(p + radius);
        for y in min.1..=max.1 {
            for x in min.0..=max.0 {
                if let Some(v) = self.cells.get(&(x, y)) {
                    out.extend_from_slice(v);
                }
            }
        }
    }
}
