/**
 * Deterministic random generator for stable per-cell visual variation.
 */
export class CellRandom {
  /**
   * @param {{x: number, y: number}} cell Grid cell coordinates.
   */
  constructor(cell) {
    this.value = (cell.x * 374761393 + cell.y * 668265263) >>> 0;
  }

  /**
   * @returns {number} A deterministic value in the [0, 1) range.
   */
  next() {
    this.value = (this.value + 0x6d2b79f5) >>> 0;
    let result = this.value;
    result = Math.imul(result ^ (result >>> 15), result | 1);
    result ^= result + Math.imul(result ^ (result >>> 7), result | 61);
    return ((result ^ (result >>> 14)) >>> 0) / 4294967296;
  }
}
