// The shared pointer loop (avatars v5 §C, kept for the v7 Lensbots): one requestAnimationFrame loop owns
// the pointer and every live robot on the page. It reads the pointer once per frame, keeps each robot's box in a cache that
// scroll and resize invalidate, and only touches the robots an IntersectionObserver says are on screen
// (those off screen also get their CSS animations paused). It stops while the tab is hidden, when
// nothing is on screen, and when robots are calm (html.calm). Per frame it writes a handful of CSS
// variables (--ex/--ey for the eyes, --lx/--lr for the lean); every other motion is a CSS animation.
// It also fires the pointer micro-events (a double-take on a fast pass, a look-around when the pointer
// leaves the window) and the random idle life (a double blink, a saccade, a look at the camera, a
// slow tilt, a focus whirr, a skeptical lid) by flashing a class on the SVG.
import { EVENT_MS, type RobotEvent } from "./moments";

export const LIVE_OVER_PX = 32; // a robot drawn at this size or smaller only blinks
const VIEW = 48;
const EYE_MAX = 1.5; // units: how far a pupil may slide
const EASE = 0.16; // of the way to the target per frame
const POINTER_FRESH_MS = 4000;
const FAST_SPEED = 2.4; // px per ms: a pass this fast earns a double-take
const DOUBLE_TAKE_GAP_MS = 2600;
const ANY_DOUBLE_TAKE_GAP_MS = 1500;
const IDLE_TICK_MS = 250;
const LIFE_WAIT_MS: readonly [number, number] = [900, 2200];
const LIFE: ReadonlyArray<readonly [RobotEvent, number]> = [["dblblink", 2], ["saccade", 4], ["camera", 1], ["tilt", 1.2], ["whirr", 1.2], ["hmm", 0.6]];
const CAMERA_MS = 1700;
const GLANCE_MS: readonly [number, number] = [500, 900];
const GLANCE_GAP_MS: readonly [number, number] = [2500, 6000];
const OBSERVER_MARGIN = "48px";
const MAX_LEAN = 1.5;
const MAX_TILT = 6;
const OFFSCREEN_CLASS = "robot--offscreen";
const CALM_CLASS = "calm";
const DEFAULT_EYE_Y = 20;

interface Entry {
  ex: number;
  ey: number;
  lx: number;
  lr: number;
  wrote: boolean;
  rect: DOMRect | null;
  visible: boolean;
  glanceAt: number;
  glancing: boolean;
  gx: number;
  gy: number;
  dblAt: number;
  cameraUntil: number;
}

const live = new Map<SVGSVGElement, Entry>();
const pointer = { x: Number.NaN, y: Number.NaN, t: 0, movedAt: -1e9, speed: 0 };
let rectsDirty = true;
let running = false;
let idleTimer: ReturnType<typeof setTimeout> | null = null;
let lifeTimer: ReturnType<typeof setTimeout> | null = null;
let lastDbl = -1e9;
let observer: IntersectionObserver | null = null;
let listening = false;
const flashes = new WeakMap<SVGSVGElement, Map<string, ReturnType<typeof setTimeout>>>();

const clamp = (value: number, low: number, high: number) => Math.max(low, Math.min(high, value));
const between = ([low, high]: readonly [number, number]) => low + Math.random() * (high - low);

export const isCalm = (): boolean => document.documentElement.classList.contains(CALM_CLASS);

// Eyes track only while they are open, wide or focused: not sad, happy, narrowed or closed.
const TRACKING_FACES = new Set(["open", "wide", "focus"]);
const faceTracks = (svg: SVGSVGElement): boolean => TRACKING_FACES.has(svg.dataset.face ?? "");

/** A micro-event: a class for a moment, beside whatever else is running. */
export function flashEvent(svg: SVGSVGElement, name: RobotEvent): void {
  const className = `robot--ev-${name}`;
  const box = flashes.get(svg) ?? new Map<string, ReturnType<typeof setTimeout>>();
  const pending = box.get(className);
  if (pending !== undefined) clearTimeout(pending);
  svg.classList.remove(className);
  void svg.getBoundingClientRect(); // so a repeated event restarts its animation
  svg.classList.add(className);
  box.set(className, setTimeout(() => svg.classList.remove(className), EVENT_MS[name]));
  flashes.set(svg, box);
}

function schedule(): void {
  if (running || document.hidden || isCalm()) return;
  running = true;
  requestAnimationFrame(frame);
}

function targetFor(svg: SVGSVGElement, entry: Entry, now: number, fresh: boolean, dx: number, dy: number, dist: number, width: number): [number, number] {
  if (now < entry.cameraUntil || !faceTracks(svg)) return [0, 0];
  if (fresh) {
    const reach = EYE_MAX * (dist / (dist + width * 0.5));
    return [(dx / dist) * reach, (dy / dist) * reach];
  }
  if (now > entry.glanceAt) {
    entry.glancing = !entry.glancing;
    entry.gx = entry.glancing ? (Math.random() - 0.5) * 2 * EYE_MAX * 0.8 : 0;
    entry.gy = entry.glancing ? (Math.random() - 0.5) * EYE_MAX * 0.6 : 0;
    entry.glanceAt = now + (entry.glancing ? between(GLANCE_MS) : between(GLANCE_GAP_MS));
  }
  return [entry.gx, entry.gy];
}

interface FrameResult {
  busy: boolean;
  nearest: SVGSVGElement | null;
}

function step(svg: SVGSVGElement, entry: Entry, now: number, fresh: boolean, fast: boolean, result: FrameResult, nearestDist: { value: number }): void {
  if (rectsDirty || !entry.rect) entry.rect = svg.getBoundingClientRect();
  const rect = entry.rect;
  const cx = rect.left + rect.width / 2;
  const eyeY = Number(svg.dataset.ey) || DEFAULT_EYE_Y; // the eye line on the 48-unit grid, kept current by the component
  const cy = rect.top + rect.height * (eyeY / VIEW);
  const dx = pointer.x - cx;
  const dy = pointer.y - cy;
  const dist = Math.hypot(dx, dy) || 1;
  const [tx, ty] = targetFor(svg, entry, now, fresh, dx, dy, dist, rect.width);
  const tracking = fresh && faceTracks(svg) && now >= entry.cameraUntil;
  if (tracking && fast && now - entry.dblAt > DOUBLE_TAKE_GAP_MS && dist < rect.width * 4 && dist < nearestDist.value) {
    result.nearest = svg;
    nearestDist.value = dist;
  }
  const over = fresh && pointer.x > rect.left - 4 && pointer.x < rect.right + 4 && pointer.y > rect.top - 4 && pointer.y < rect.bottom + 4;
  const lx = over ? clamp((dx / rect.width) * 3, -MAX_LEAN, MAX_LEAN) : 0;
  const lr = over ? clamp((dx / rect.width) * 12, -MAX_TILT, MAX_TILT) : (fresh ? clamp(dx / (rect.width * 4), -1, 1) * 2.5 : 0);
  entry.ex += (tx - entry.ex) * EASE;
  entry.ey += (ty - entry.ey) * EASE;
  const moving = Math.abs(tx - entry.ex) > 0.01 || Math.abs(ty - entry.ey) > 0.01;
  if (moving || entry.wrote) {
    svg.style.setProperty("--ex", entry.ex.toFixed(2));
    svg.style.setProperty("--ey", entry.ey.toFixed(2));
    entry.wrote = moving;
  }
  if (Math.abs(lx - entry.lx) > 0.05 || Math.abs(lr - entry.lr) > 0.1) {
    entry.lx = lx;
    entry.lr = lr;
    svg.style.setProperty("--lx", lx.toFixed(2));
    svg.style.setProperty("--lr", lr.toFixed(1));
  }
  result.busy = result.busy || moving || over;
}

function frame(now: number): void {
  running = false;
  if (document.hidden || isCalm()) return;
  const fresh = now - pointer.movedAt < POINTER_FRESH_MS;
  const fast = pointer.speed > FAST_SPEED && now - lastDbl > ANY_DOUBLE_TAKE_GAP_MS;
  const result: FrameResult = { busy: false, nearest: null };
  const nearestDist = { value: Number.POSITIVE_INFINITY };
  for (const [svg, entry] of live) {
    if (entry.visible) step(svg, entry, now, fresh, fast, result, nearestDist);
  }
  if (result.nearest) doubleTake(result.nearest, now);
  rectsDirty = false;
  pointer.speed *= 0.85;
  if (result.busy || fresh) {
    schedule();
  } else {
    if (idleTimer !== null) clearTimeout(idleTimer);
    idleTimer = setTimeout(schedule, IDLE_TICK_MS); // idle: only the glances are due
  }
}

/** A fast pass: only the nearest robot does a double-take, toward where the pointer went. */
function doubleTake(svg: SVGSVGElement, now: number): void {
  const entry = live.get(svg);
  if (!entry?.rect) return;
  entry.dblAt = now;
  lastDbl = now;
  svg.style.setProperty("--dtx", pointer.x > entry.rect.left + entry.rect.width / 2 ? "1.5" : "-1.5");
  flashEvent(svg, "dbl");
}

function onPointerMove(event: PointerEvent | MouseEvent): void {
  const now = performance.now();
  const dt = Math.max(1, now - pointer.t);
  if (Number.isFinite(pointer.x)) {
    pointer.speed = pointer.speed * 0.5 + (Math.hypot(event.clientX - pointer.x, event.clientY - pointer.y) / dt) * 0.5;
  }
  pointer.x = event.clientX;
  pointer.y = event.clientY;
  pointer.t = now;
  pointer.movedAt = now;
  schedule();
}

/** The pointer leaves the window: a short look-around, then back to idle. */
function onPointerLeft(): void {
  if (pointer.movedAt < 0) return;
  pointer.movedAt = -1e9;
  pointer.speed = 0;
  let index = 0;
  for (const [svg, entry] of live) {
    if (entry.visible && faceTracks(svg)) setTimeout(() => flashEvent(svg, "around"), (index++ % 12) * 60);
  }
  schedule();
}

function invalidate(): void {
  rectsDirty = true;
  schedule();
}

/** Random life: now and then one visible robot does one small idle thing. */
function lifeTick(): void {
  lifeTimer = setTimeout(lifeTick, between(LIFE_WAIT_MS));
  if (document.hidden || isCalm()) return;
  const candidates = [...live].filter(([svg, entry]) => entry.visible && faceTracks(svg)).map(([svg]) => svg);
  if (candidates.length === 0) return;
  const svg = candidates[Math.floor(Math.random() * candidates.length)];
  const total = LIFE.reduce((sum, [, weight]) => sum + weight, 0);
  let pick = Math.random() * total;
  for (const [name, weight] of LIFE) {
    pick -= weight;
    if (pick <= 0) return playIdle(svg, name);
  }
}

function playIdle(svg: SVGSVGElement, name: RobotEvent): void {
  const entry = live.get(svg);
  if (!entry) return;
  if (name === "saccade") {
    entry.glancing = false;
    entry.glanceAt = 0;
    schedule();
    return;
  }
  if (name === "camera") entry.cameraUntil = performance.now() + CAMERA_MS;
  flashEvent(svg, name);
}

function listen(): void {
  if (listening) return;
  listening = true;
  window.addEventListener("pointermove", onPointerMove, { passive: true });
  document.documentElement.addEventListener("mouseleave", onPointerLeft);
  window.addEventListener("pointerout", (event) => { if (!event.relatedTarget) onPointerLeft(); });
  window.addEventListener("scroll", invalidate, { passive: true });
  window.addEventListener("resize", invalidate);
  document.addEventListener("visibilitychange", () => { if (!document.hidden) invalidate(); });
}

function observe(): IntersectionObserver | null {
  if (observer) return observer;
  if (typeof IntersectionObserver === "undefined") return null;
  observer = new IntersectionObserver((entries) => {
    for (const seen of entries) {
      const entry = live.get(seen.target as SVGSVGElement);
      if (entry) entry.visible = seen.isIntersecting;
      seen.target.classList.toggle(OFFSCREEN_CLASS, !seen.isIntersecting);
    }
    schedule();
  }, { rootMargin: OBSERVER_MARGIN });
  return observer;
}

/** A live robot joins the loop; the function given takes it out again. Its `data-ey` is its eye line on the 48-unit grid. */
export function registerLookAt(svg: SVGSVGElement): () => void {
  listen();
  if (lifeTimer === null) lifeTimer = setTimeout(lifeTick, between(LIFE_WAIT_MS));
  live.set(svg, {
    ex: 0, ey: 0, lx: 0, lr: 0, wrote: false, rect: null, visible: false,
    glanceAt: performance.now() + 1500 + Math.random() * 4000, glancing: false, gx: 0, gy: 0, dblAt: -1e9, cameraUntil: 0,
  });
  observe()?.observe(svg);
  invalidate();
  return () => {
    observer?.unobserve(svg);
    live.delete(svg);
    svg.classList.remove(OFFSCREEN_CLASS);
    for (const name of ["--ex", "--ey", "--lx", "--lr", "--dtx"]) svg.style.removeProperty(name);
  };
}

/** Everything back to the start, for tests that stand in their own observer and frame loop. */
export function resetLookAtForTests(): void {
  observer?.disconnect();
  observer = null;
  live.clear();
  running = false;
  rectsDirty = true;
  lastDbl = -1e9;
  pointer.x = Number.NaN;
  pointer.y = Number.NaN;
  pointer.t = 0;
  pointer.movedAt = -1e9;
  pointer.speed = 0;
  if (idleTimer !== null) clearTimeout(idleTimer);
  if (lifeTimer !== null) clearTimeout(lifeTimer);
  idleTimer = null;
  lifeTimer = null;
}
