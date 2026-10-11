/** The classroom's eye: which frames are worth reading, run rather than read. */
import assert from "node:assert/strict";

const {
  compare, PIXEL_CHANGED, CAMERA_PIXEL_CHANGED, CAMERA_MIN_CHANGED_PIXELS,
  MOTION_BUSY, CAMERA_MOTION_BUSY, isBusy, hasChanged, blurOtherFacesOnCanvas,
} = await import("../../guardian/ui/teach/capture.js");

const cases = [];
const test = (name, fn) => cases.push([name, fn]);
const W = 160, H = 90;
const screen = (shade = 30) => { const d = new Uint8ClampedArray(W * H * 4); for (let i = 0; i < d.length; i += 4) d.set([shade, shade, shade, 255], i); return d; };
const paint = (d, x0, y0, w, h, rgb) => { for (let y = y0; y < y0 + h; y++) for (let x = x0; x < x0 + w; x++) d.set([...rgb, 255], (y * W + x) * 4); return d; };

test("a screen at rest changes no pixel and is not sent", () => {
  const { motion, changed } = compare(screen(), screen());
  assert.equal(changed, 0);
  assert.equal(motion, 0);
});

test("the first frame has nothing to be compared with", () => {
  assert.deepEqual(compare(null, screen()), { motion: 0, changed: 0 });
});

test("a choice in one small field is a change, though the screen barely moves", () => {
  // A dropdown's words, about 8 by 2 of 160 by 90: the mean is tiny, the pixels are not.
  const before = paint(screen(), 120, 30, 8, 2, [60, 60, 60]);
  const after = paint(screen(), 120, 30, 8, 2, [200, 200, 200]);
  const { motion, changed } = compare(before, after);
  assert.ok(motion < 1, `motion ${motion} stays under a cursor's`);
  assert.equal(changed, 16);
});

test("a cursor fading by a few levels is not a change", () => {
  const before = paint(screen(), 10, 10, 1, 2, [30, 30, 30]);
  const after = paint(screen(), 10, 10, 1, 2, [30 + PIXEL_CHANGED, 30 + PIXEL_CHANGED, 30 + PIXEL_CHANGED]);
  assert.equal(compare(before, after).changed, 0);
});

test("scrolling a whole screen is busy", () => {
  const before = screen(30);
  const after = paint(screen(30), 0, 0, W, H / 2, [90, 90, 90]);
  assert.ok(compare(before, after).motion >= MOTION_BUSY);
});

test("a camera that sways slightly is at a pause, while a gesture is busy", () => {
  assert.ok(CAMERA_MOTION_BUSY > MOTION_BUSY);
  assert.equal(isBusy(4.5, "screen"), true);
  assert.equal(isBusy(4.5, "camera"), false);
  assert.equal(isBusy(CAMERA_MOTION_BUSY + 1, "camera"), true);
});

test("sensor noise and slight camera sway do not count as a changed camera frame, while writing on a whiteboard does", () => {
  assert.ok(CAMERA_PIXEL_CHANGED > PIXEL_CHANGED);
  assert.ok(CAMERA_MIN_CHANGED_PIXELS > 100);
  const base = screen(40);
  // Sensor noise (+20 levels across 500 pixels) triggers screen PIXEL_CHANGED (12) but not CAMERA_PIXEL_CHANGED (32).
  const noisy = paint(screen(40), 10, 10, 50, 10, [60, 60, 60]);
  assert.equal(compare(base, noisy, "screen").changed, 500);
  assert.equal(compare(base, noisy, "camera").changed, 0);
  // Slight edge sway (200 pixels above 32) is below CAMERA_MIN_CHANGED_PIXELS, while a whiteboard stroke (450 pixels) is sent.
  const sway = paint(screen(40), 10, 10, 20, 10, [180, 180, 180]);
  const stroke = paint(screen(40), 10, 10, 45, 10, [180, 180, 180]);
  assert.equal(compare(base, sway, "camera").changed, 0);
  assert.equal(compare(base, stroke, "camera").changed, 450);
  assert.equal(hasChanged(200, "camera"), false);
  assert.equal(hasChanged(450, "camera"), true);
  assert.equal(hasChanged(1, "screen"), true);
});

test("when the browser provides FaceDetector, faces of other people are blurred on the canvas before the frame leaves the page", async () => {
  const drawn = [];
  const canvas = {
    width: 200,
    height: 120,
    getContext: () => ({
      save: () => {},
      restore: () => {},
      drawImage: (_src, x, y, w, h) => drawn.push({ x, y, w, h }),
      filter: "none",
    }),
  };
  class FakeFaceDetector {
    async detect() {
      return [
        { boundingBox: { x: 10, y: 10, width: 60, height: 60 } },
        { boundingBox: { x: 120, y: 20, width: 30, height: 30 } },
      ];
    }
  }
  const res = await blurOtherFacesOnCanvas(canvas, FakeFaceDetector);
  assert.equal(res.blurredOnPage, true);
  assert.equal(res.otherFaces, 1);
  assert.equal(drawn.length, 1);
  assert.equal(drawn[0].x, 120);
});

let failed = 0;
for (const [name, fn] of cases) {
  try {
    await fn();
    console.log(`ok   ${name}`);
  } catch (err) {
    failed++;
    console.log(`FAIL ${name}\n     ${err.message.split("\n")[0]}`);
  }
}
console.log(`\n${cases.length - failed} passed, ${failed} failed`);
process.exit(failed ? 1 : 0);

