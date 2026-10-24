/**
 * Central gameplay tuning. Everything that affects feel or fairness lives here so
 * the spawner's fairness model and the player controller always agree.
 */
export const LANES = [-2.6, 0, 2.6] as const;
export const LANE_WIDTH = 2.6;

/** Car centre heights for the three vertical states. */
export const HEIGHT = {
  LOW: 0.48,
  NORMAL: 1.0,
  HIGH: 3.05,
  /** Roadster Jump apex */
  SUPER: 5.6,
  /** Mythic HYPER JUMP apex (event prize / shop item) */
  HYPER: 7.4,
  /** SKY ESCAPE (emergency item) cruising height */
  ESCAPE: 9.6,
} as const;

/** Car hitbox half-extents (already slightly forgiving vs. the visual model). */
export const CAR_HALF = { x: 0.7, y: 0.36, z: 1.0 } as const;
/** In the LOW state the car is compressed, so its hitbox is shorter. */
export const CAR_HALF_Y_LOW = 0.28;

export const TIMING = {
  laneChange: 0.22, // seconds to slide one lane (ease-in-out: smooth start and stop)
  laneBuffer: 0.12, // queued lane input lifetime
  // FLY UP phases
  upAntic: 0.06,
  upExec: 0.2,
  upHold: 0.52,
  upRecover: 0.3,
  // FLY DOWN phases
  downAntic: 0.05,
  downExec: 0.14,
  downHold: 0.52,
  downRecover: 0.24,
  verticalBuffer: 0.16,
  /** an UP swipe made just before touching down is kept this long and fires on landing */
  landBuffer: 0.34,
  jumpRest: 0.03, // seconds on the ground after landing before the next jump
  // ROADSTER JUMP (power-up): a rocket hop over two beats with a 360° roll
  superAntic: 0.1,
  superExec: 0.36,
  superHold: 1.0,
  superRecover: 0.5,
  // HYPER JUMP (mythic item): higher, longer, double roll, golden trail
  hyperExec: 0.42,
  hyperHold: 1.7,
  hyperRecover: 0.55,
  // SKY ESCAPE: straight up, cruise above everything, slow glide down
  escExec: 0.7,
  escHold: 3.2,
  escRecover: 2.1,
  // AIR DASH: 2-lane hop sideways while airborne, with a flip
  dashDur: 0.34,
};

/**
 * Step 06.5 AIR DASH (road collectible, fires the moment it is picked up): only on the two outer
 * lanes; the car lifts to HIGH, opens the spoiler, rolls exactly once (360°, sideways around its
 * length axis) while it crosses exactly two lanes to the opposite outer lane, then lands there.
 * exec / hold / recover = vertical phases (s); lateralStart / lateral = when and how long the
 * sideways move (and the roll) runs; maxExtend = most extra hover (s) when the landing spot is
 * briefly blocked; grace = protection after touch-down (s); clearAhead / clearBehind = metres of the
 * destination lane that must be free around the touch-down point (spawner + runtime check).
 */
/**
 * Step 06.5 road-item balance (Endless / Track 2 power-up slot). `weights` = relative chance per slot;
 * per speed level: `weights` multipliers (EASY: more survival help, HARD: less) and `heartEvery` × the
 * heart spacing (HEARTS.everyExp: < 1 = hearts more often). Air Dash < Turbo, Life rare.
 */
export const ITEM_BALANCE = {
  weights: { magnet: 3, shield: 3, turbo: 0.7, mystery: 0.5, double: 2, dash: 0.45 } as Record<string, number>,
  level: {
    easy: { weights: { shield: 1.3, dash: 1.1 } as Record<string, number>, heartEvery: 0.8 },
    normal: { weights: {} as Record<string, number>, heartEvery: 1 },
    hard: { weights: { shield: 0.75, mystery: 0.8 } as Record<string, number>, heartEvery: 1.25 },
  },
};

export const AIR_DASH = { exec: 0.26, hold: 0.5, recover: 0.3, lateralStart: 0.06, lateral: 0.62, maxExtend: 0.45, grace: 0.25, clearAhead: 0.6, clearBehind: 4 };

/** Player speed levels chosen on the home screen (3 audiences: new, regular, expert). */
export type SpeedLevel = 'easy' | 'normal' | 'hard';

/** v2: everyone gets the same on-road power-up strength (no garage upgrades — EXP stays fair) */
export const V2_POWERUPS = { engine: 2, shield: 2, magnet: 2 };

/**
 * v2 coin economy (docs/GAME-DESIGN.md §4): coin lines on the road. Specials cost 2,000–6,000, so
 * coins are scarce on Endless (~40 / min for a good player) and generous on Bonus roads.
 */
/** v2 hearts: every EXP race starts with 1; a heart lies on the road about every `everyExp` EXP */
export const HEARTS = { everyExp: 1000, max: 3 };
/** v4.6.1 (owner): classes C / B / A unlock no car → their first-time promotion gives coins + 1 special */
export const CLASS_REWARD: Partial<Record<'C' | 'B' | 'A', { coins: number; item: 'super' | 'hyper' | 'escape' }>> = {
  C: { coins: 300, item: 'super' },
  B: { coins: 500, item: 'hyper' },
  A: { coins: 800, item: 'escape' },
};

/**
 * v2.2 random rewards: mystery boxes on the road and every energy ring flown through.
 * Weights per reward; coins = a random amount from `coins`. Hearts only while one is missing.
 */
export const GIFTS = {
  box: { coins: [20, 40, 80], w: { coins: 4, magnet: 1.5, shield: 1.2, turbo: 0.8, double: 1.3, life: 1 } as Record<string, number> },
  ring: { coins: [5, 10, 15], w: { coins: 6, magnet: 1.2, shield: 0.8, turbo: 0.4, double: 1.2, life: 0.4 } as Record<string, number> },
  /** mystery boxes: chance per obstacle row to hang a box at the trick spot (over / under / beside it) */
  boxChance: 0.15,
  /** min metres between two boxes */
  boxGap: 600,
};

/**
 * v2.2 Bonus roads: specials are a rare drop. Each special reserves an empty stretch right after its
 * pickup; only when the player picks it up is that stretch filled with its "set piece" (car wall,
 * convoy, laser zone…), and the special fires by itself into it. Missed → the stretch stays empty.
 */
export const BONUS_SET = {
  /** chance that a power-up slot is a special instead of a normal item */
  chance: 0.065,
  /** chance that a tunnel gets a Tunnel Rider pickup in front of it */
  tunnelChance: 0.5,
  /** metres from the pickup to the start of the set piece */
  lead: 70,
  /** set-piece lengths (m) */
  len: { super: 26, hyper: 48, escape: 26, wall: 42, rail: 70, ghost: 54 } as Record<string, number>,
  /** seconds before the set piece when the special fires by itself */
  fire: { super: 0.55, hyper: 0.6, escape: 0.45, wall: 0.35, rail: 0.35, ghost: 0.35, tunnel: 0.3 } as Record<string, number>,
  /** tunnel sections on every Bonus road: centres as a fraction of the road + length (m) */
  tunnels: [0.24, 0.55, 0.83],
  tunnelLen: 150,
};

export const COIN_LINES = {
  // v2.2.4: main road back to v1's generous coin lines (the fun of collecting); Bonus ~10 % above it
  endless: { skip: 0.18, max: 8 },
  bonus: { skip: 0.1, max: 8 },
  /** old courses (v1) */
  course: { skip: 0.18, max: 8 },
};

/**
 * v2 EXP (docs/GAME-DESIGN.md §1). Run EXP = metres × rate[level]; the player's EXP = best run (never summed).
 * Rates are calibrated (tests/exp.test.ts) so a non-stop run reaches C / B / A / AA / AAA at
 * 3 / 7 / 12 / 20 / 30 min on HARD, ×2 that time on NORMAL and ×3 on EASY.
 */
export const EXP = {
  rate: { easy: 0.184, normal: 0.19, hard: 0.318 } as Record<SpeedLevel, number>,
  /** EXP needed for each rank */
  rank: { D: 0, C: 3000, B: 8000, A: 15000, AA: 26000, AAA: 40000, S: 65000, SS: 85000, SSS: 110000 },
  /** design targets (minutes of non-stop HARD; S tiers on Track 2) — shown in the rank guide, checked by the test */
  hardMinutes: { D: 0, C: 3, B: 7, A: 12, AA: 20, AAA: 30, S: 35, SS: 45, SSS: 58 },
  /** Track 2 (unlocks at AAA): starts two difficulty phases ahead, pays more EXP and is the only road to S / SS / SSS */
  track2: { rateMul: 1.25, phaseShift: 2, sSpeedStep: 0.03 },
  timeMul: { easy: 3, normal: 2, hard: 1 } as Record<SpeedLevel, number>,
};
/**
 * Speed levels. Harder = faster AND better paid (tiered rewards):
 *  `reward` multiplies the coin bonus, the track reward and the rank X-Points of a run.
 */
export const LEVELS: Record<SpeedLevel, { label: string; speed: number; gap: number; score: number; reward: number; desc: string }> = {
  easy: { label: 'EASY', speed: 0.82, gap: 1.2, score: 0.8, reward: 1, desc: 'Slower road · EXP ×1 (ranks take 3× longer)' },
  normal: { label: 'NORMAL', speed: 1.21, gap: 1, score: 1, reward: 1.25, desc: 'Regular speed · EXP ×1.05 · coins ×1.25' },
  hard: { label: 'HARD', speed: 1.5, gap: 0.92, score: 1.3, reward: 1.6, desc: 'Fast & tight · EXP ×1.7 · coins ×1.6' },
};

/** big-reward tracks also pay items when finished with enough stars (all matching rules apply) */
export const TRACK_ITEM_BONUS: { minReward: number; stars: number; items: Partial<Record<'super' | 'hyper' | 'escape' | 'shield', number>> }[] = [
  { minReward: 500, stars: 2, items: { super: 1 } },
  { minReward: 800, stars: 2, items: { escape: 1 } },
  { minReward: 900, stars: 3, items: { hyper: 1 } },
  { minReward: 1200, stars: 3, items: { shield: 1 } },
];

/** points per unused boost charge still held when a track is finished (× the run's score multiplier) */
export const LEFTOVER_POINTS = { super: 1500, hyper: 3000, escape: 1000 };

/**
 * Rolling tyres (rear render) + tyre spray. The tread may advance at most `maxStep` of a block per
 * frame (< 0.5 or it strobes backwards); higher speed reads through blur, streaks and spray instead.
 */
export const TYRE = {
  blocksPerMetre: 0.55,
  streaksPerMetre: 0.14,
  maxStep: 0.36,
  /** speed (m/s) where the extra blur starts / is full */
  blurFrom: 18,
  blurFull: 50,
  /** rear tyre contact point on the sprite plane (plane units, centre = 0) */
  spriteX: 0.43,
  spriteY: -0.48,
  /** grit kicked up by the rear tyres while driving fast */
  sprayFrom: 22,
  sprayRate: 0, // tyre grit off: no smoke / dust on the tyres (owner's brief)
  spraySize: 0.07,
  sprayLife: 0.3,
  sprayColor: 0xb9c6e6,
  /** wheel radius (m) — drives how fast the light trails circle the tyres */
  radius: 0.36,
  /** rear tyres on the X1 rear render (uv): x < maskX (and > 1 − maskX), y < maskY */
  maskX: 0.17,
  maskY: 0.5,
  /** rear tread layer: tread rect on the render (uv x), image height px, tile height px / metres */
  treadX0: 14 / 1024,
  treadX1: 136 / 1024,
  treadImgH: 588,
  treadTilePx: 120,
  treadTileM: 0.33,
  /** max tread scroll per frame (fraction of a tile) — more would strobe */
  treadMaxStep: 0.4,
  treadGain: 1.0,
  /** blur length (fraction of a tile) per speed tier, km/h: idle → run → fast → very fast */
  treadTiers: [
    { kmh: 0, blur: 0 },
    { kmh: 60, blur: 0.06 },
    { kmh: 150, blur: 0.22 },
    { kmh: 250, blur: 0.45 },
    { kmh: 400, blur: 0.7 },
  ],
  /** extra blur while Turbo runs */
  treadTurboBlur: 0.3,
  /** body suspension spring (metres; ~0.009 m ≈ 1 px on a phone) */
  susp: { k: 260, damp: 16, max: 0.03, bumpEvery: 0.35, bumpKick: 0.16, laneKick: 0.22, landKick: 0.55, pitchK: 0.0016, pitchMax: 0.012 },
  /** tyre effects (tread motion, hot streaks, orbit trails, sparks). Off = tyres look exactly like the render */
  effects: false,
  /** speed (m/s) where the hot-tyre glow starts / is full */
  hotFrom: 14,
  hotFull: 40,
  /** orbit trail speed relative to the wheel's real spin */
  orbitSpeed: 0.35,
  /** orbit glow placement on the sprite plane, diameter (m), horizontal squash */
  glowX: 0.43,
  glowY: -0.26,
  glowD: 0.66,
  glowSquash: 0.5,
  /** boost render height relative to the normal rear render (same width, same top edge) */
  boostImgH: 954 / 740,
  /** boost look envelope rates (1/s): attack when it starts, release when it ends */
  boostAttack: 9,
  boostRelease: 3,
  /** at speed the tyre spray turns into orange sparks */
  sparkColor: 0xff8a2a,
};

export const SPEED = {
  start: 21,
  max: 46,
  /** distance (m) at which ~63% of the extra speed has been added */
  rampDistance: 3200,
  turboMul: 1.55,
};

/**
 * Fairness model. A "row" is a set of obstacles the car reaches at the same moment.
 * The spawner only accepts a row if, from at least one lane the player could be in at
 * the previous row, a lane of the new row is reachable in the available time.
 */
export const FAIRNESS = {
  /** time budget per lane step (slightly more than TIMING.laneChange for human reaction) */
  laneStepTime: 0.27,
  /** time needed to reach HIGH / LOW from NORMAL including anticipation */
  verticalTime: 0.3,
  /** minimum reaction time to any row (seconds) */
  minRowTime: 0.5,
};

export const SCORE = {
  perMeter: 1,
  coin: 10,
  nearMiss: 50,
  ringPass: 100,
  dodge: 5,
  comboStep: 10, // every N dodges the multiplier grows by 0.5
  comboMax: 4,
};

export const POWERUP_DURATION = {
  shield: 0, // shield lasts until hit (upgrades add a timed safety bubble after break)
  magnet: 8,
  turbo: 4,
  double: 10,
  /** v2.2 ring pass: every coin counts twice for this long (a new ring refreshes it) */
  coin2: 8,
};

export const WORLD_LENGTH = 1000; // metres per themed world

export const DEBUG = typeof location !== 'undefined' && /[?&]debug/.test(location.search);
/** v4.2.1 `?perf=1`: frame-time recorder + small on-screen readout, `window.__perf()` / `window.__game` for scripted profiling */
export const PERF = typeof location !== 'undefined' && /[?&]perf/.test(location.search);
export const AUTOPILOT = typeof location !== 'undefined' && /[?&]autopilot/.test(location.search);

/**
 * v2.3 cloud save (server/index.mjs). `api` = the game server's address, e.g. 'https://api.skyroadster.com'.
 * Empty = cloud off (progress stays on the device). `?api=…` in the page URL overrides it for testing.
 */
export const CLOUD = {
  api: '',
  /** ms after the last change before the save is pushed */
  syncDelay: 4000,
};

/**
 * v4 render-only settings (no gameplay effect: hitboxes, lanes and timings above are unchanged).
 * `car`: 'mesh' = the 3D XWAVE X1 (src/assets/models/xwave-x1.glb), 'sprite' = the v2 studio image.
 * `?car=sprite` / `?car=mesh` in the page URL override it for comparison.
 */
export const RENDER = {
  car: (typeof location !== 'undefined' && /[?&]car=sprite/.test(location.search) ? 'sprite' : 'mesh') as 'mesh' | 'sprite',
  /**
   * player look (visual only): 'ninja' = the chibi ninja character (src/assets/models/ninja.glb, built by
   * assets-src/ninja/build_ninja.py, driven by render/car/NinjaRig.ts); 'car' = the XWAVE X1 exactly as
   * before. Revert to the car: set this to 'car' (or `?player=car` in the page URL).
   */
  player: (typeof location !== 'undefined' && /[?&]player=car/.test(location.search) ? 'car' : 'ninja') as 'ninja' | 'car',
  /** ninja: model (≈1.02 m) → game size; optional accessory (never both); clip timing */
  ninja: {
    scale: 1.75,
    accessory: ((typeof location !== 'undefined' && /[?&]ninjaacc=(dagger|handprop)/.exec(location.search)?.[1]) || 'none') as 'none' | 'dagger' | 'handprop',
    /** Run plays at speed / runRate (clamped 0.85…1.9 ×) */
    runRate: 30,
    /** crossfade between clips (s) and how long the landing clip plays (s) */
    fade: 0.12,
    landTime: 0.36,
    /** turn toward a lane change (rad per lane-speed) */
    laneYaw: 0.28,
    /** nitro thrust size on the ninja's back (× the X1's) */
    thrust: 0.6,
  },
  /** model (real-size metres) → game size. 0.76 ≈ 1.66 m wide: close to the 1.4 m hitbox, and the rear
   *  reads about the same size on screen as the old rear image did from the unchanged chase camera */
  carScale: 0.76,
  /** v4.6 (owner): with Settings → Camera motion OFF (fixed view, the default) the car is drawn a little
   *  bigger (visual only, hitbox unchanged; the moving chase camera keeps carScale for its readability) */
  carScaleFixed: 0.82,
  /**
   * v4.6 (owner): the 3D car is drawn 15 % taller (height only, at runtime — the approved GLB file is
   * unchanged) so the DOWN dive (height × (1 − duck.squash)) reads more clearly. Visual only: hitboxes,
   * pass heights and timings are unchanged; at NORMAL the roof stays below the hitbox top.
   */
  carHeightScale: 1.15,
  /** v4.3 (Step 06 PBR): paint metallic-flake normal map strength and tiles per metre (MeshCar) */
  paintFlake: 0.12,
  paintFlakeRepeat: 7,
  /** wheels: max visible spin per frame (rad) — more would strobe (10 spokes); speed above it reads via the blur disc */
  wheelMaxStep: 0.3,
  /** speed (m/s) where the wheel blur disc starts / is full */
  wheelBlurFrom: 8,
  wheelBlurFull: 30,
  /** front wheel steer (rad) per unit of lateral speed */
  steer: 0.2,
  /** sprung body: roll per unit of lateral speed, landing dip (m), landing pitch kick (rad) */
  bodyRoll: 0.045,
  landDip: 0.05,
  landPitch: 0.05,
  /** emissive strength of the rear LED / markers / badge in game (bloom picks up values above 1) */
  ledGlow: 3.6,
  markerGlow: 2.6,
  badgeGlow: 1.4,
  /** headlight LED emissive strength (slim signature, no blooming blob) */
  headGlow: 1.4,
  /** nitro flame length (m) at full boost */
  nitroLen: 2.0,
  /** sprung body yaw per unit of lateral speed (subtle nose-in on lane changes) */
  bodyYaw: 0.02,
  /** active rear spoiler (v4.1.3 pop-up): max angle (rad, trailing edge up, 0.38 ≈ 22°), how far the
   *  flap rises off the deck at full deployment (model metres), raise / retract rates (1/s) */
  spoilerAngle: 0.38,
  spoilerRise: 0.06,
  spoilerUp: 7,
  spoilerDown: 2.0,
  /** seconds the spoiler stays up after jump + nitro end (no flicker on landing) */
  spoilerHold: 0, // Step 06.5: closing starts at ground contact
  /** Bonus "Phase Ghost": opacity of the 3D car at full effect, cyan edge strength */
  ghostOpacity: 0.35,
  ghostRim: 1.6,
  /**
   * v4.1.3 DOWN (dive under a beam): the 3D car presses down toward the road — height × (1 − squash),
   * width × (1 + widen), length × (1 + stretch) at full dive, with a small spring overshoot — plus a
   * light pool under it and a few sparks. Visual only: the LOW hitbox and timings are unchanged.
   */
  duck: { squash: 0.28, widen: 0.06, stretch: 0.03 },
  /**
   * v4.1.3 airborne alignment: once the car leaves the road its visual underside is lifted to at least
   * the hitbox underside within `ramp` metres of height (jumped obstacles no longer cut through the
   * body while the hitbox already clears them). On the road nothing changes (wheels on the asphalt).
   */
  airAlignRamp: 0.45,
  /** shield aura: colour, rim strength, pulse (Hz), fade in / out rates (1/s) */
  shield: { color: 0x7fe6ff, rim: 1.25, pulse: 0.6, fadeIn: 9, fadeOut: 4 },
  /** Turbo smashes obstacles like the shield blocks them → the same shell, in Turbo's lime, a little
   *  larger (sits outside the shield when both run) and pulsing faster */
  turboAura: { color: 0x8fd61f, rim: 1.0, pulse: 1.4, fadeIn: 12, fadeOut: 5, size: 1.07, name: 'TurboAura' },
  /** pickup light sweep (turbo / rockets / power-ups): seconds front → back */
  sweepTime: 0.5,
  /** crash: debris fragments (pooled), their life (s), impact flash life (s) */
  crash: { fragments: 12, life: 1.4, flash: 0.2 },
  /**
   * Step 06.5 (owner): the car never hangs in the air after a crash — it drops to the road (gravity m/s²,
   * bounce = kept fraction of the landing speed, nose-down tilt in rad while falling). On the run-ending
   * crash a few real parts of the approved car (no geometry change: the same meshes, moved) break off,
   * tumble and lie on the road until the next run.
   */
  crashFall: { gravity: 24, bounce: 0.25, tilt: 0.12, parts: ['Front_Splitter', 'Spoiler_Pivot', 'Wheel_FL'] },
};

/** one chase-camera setup (metres relative to the car; damping rates 1/s) */
export type ChaseName = 'low' | 'balanced' | 'high';

export interface ChasePreset {
  /** camera height and distance behind the car; speedBack = extra pull-in at top speed */
  height: number;
  back: number;
  speedBack: number;
  /** look-at point: height and distance ahead */
  lookY: number;
  lookZ: number;
  /** how much of the car's lane offset the camera / look point follow */
  followX: number;
  lookX: number;
  /** how much the camera / look point rise with a normal hop */
  lift: number;
  lookLift: number;
  /** damping: horizontal position, vertical position, look point */
  hDamp: number;
  vDamp: number;
  lookDamp: number;
  /** added to the base FOV (degrees) */
  fov: number;
  /** FOV widening (degrees) at top speed / during Turbo (default 7 / 9) */
  fovSpeed?: number;
  fovTurbo?: number;
}

/**
 * v4 chase cameras (render-only). HIGH = the v1–v4.1.0 camera, kept for the old rear image.
 * The 3D car uses `CAMERA.chase` (URL `?cam=low|balanced|high` to compare).
 */
export const CAMERA = {
  presets: {
    low: { height: 1.6, back: 5.3, speedBack: 0.4, lookY: 1.05, lookZ: -16, followX: 0.8, lookX: 0.6, lift: 1.7, lookLift: 0.1, hDamp: 6, vDamp: 8, lookDamp: 6.5, fov: -3 },
    balanced: { height: 2.25, back: 5.9, speedBack: 0.5, lookY: 1.0, lookZ: -13, followX: 0.76, lookX: 0.58, lift: 1.7, lookLift: 0.1, hDamp: 6.5, vDamp: 8, lookDamp: 7, fov: -1 },
    high: { height: 3.25, back: 6.6, speedBack: 0.6, lookY: 1.15, lookZ: -9, followX: 0.72, lookX: 0.55, lift: 0.22, lookLift: 0.3, hDamp: 6.5, vDamp: 6, lookDamp: 7, fov: 0 },
  } as Record<ChaseName, ChasePreset>,
  chase: ((typeof location !== 'undefined' && /[?&]cam=(low|balanced|high)/.exec(location.search)?.[1]) || 'balanced') as ChaseName,
  /**
   * Home screen with the 3D car: a slow three-quarter orbit behind the car at a constant distance
   * (constant size), framed in the free band between the side buttons and the difficulty panel.
   * yaw in radians (0 = straight behind), height / distance in metres, lookY / lookZ = aim point,
   * fovScale × the base FOV.
   */
  // v4.5.1 (owner): the orbit stays INSIDE the road (camera x ≤ dist·sin(yaw+swing) ≈ 3.1 m, the guard rails
  // are at ±4.3 m) — it used to swing out past the right rail, so the barrier crossed the whole view
  /**
   * v4.6 Settings "Camera motion" OFF (default): fixed view down the centre of the road. It never follows
   * the lane, so it sits further back / higher than the chase preset (back / height added, metres) to
   * keep the car fully on screen in both outer lanes on narrow portrait phones; `hopTop` = gameplay
   * height above which (Roadster / HYPER / SOS flights only) it still climbs so the car stays framed.
   */
  // margin = gap kept between the car (outer lane) and the screen edge, fraction of the width;
  // carHalfW / carRear = the 3D car's half width / rear end in game metres (2.09 × 4.22 m model × carScale)
  fixed: { margin: 0.012, carHalfW: 1.045 * 0.82, carRear: 2.242 * 0.82, height: 0.5, lookY: 1.1, hopTop: 3.4 },
  home: { yaw: 0.24, yawSwing: 0.14, speed: 0.22, height: 2.45, dist: 8.3, lookY: 0.98, lookZ: 0.2, fovScale: 0.82 },
};

/**
 * v4.2 (3D upgrade Step 04) graphics presets. Render-only: the game logic, speeds and hitboxes are
 * identical on every preset. MEDIUM is the starting preset until device benchmarks exist; a device
 * that cannot hold ~42 fps steps down on its own (resolution → bloom → LOW, session only).
 */
export type GraphicsQuality = 'low' | 'medium' | 'high';
export interface GraphicsPreset {
  /** max device pixel ratio */
  dprCap: number;
  /** bloom (half-resolution) on lights / LEDs */
  bloom: boolean;
  /** edge speed blur post pass */
  speedBlur: boolean;
  /** share of the city buildings drawn (instance count) */
  cityDensity: number;
  /** far skyline lights, rooftop neon, roadside signs */
  cityExtras: boolean;
  /** road: light pools under the lamps, joints, polished tyre tracks (shader detail) */
  roadDetail: boolean;
  /** max anisotropic filtering on the road (sharp markings at grazing angles) */
  anisotropy: number;
  /** v4.2.1: share of burst particles (sparks, glints, dust) */
  particles: number;
  /** v4.2.1: road texture size (width; height = 2 ×) */
  roadTex: number;
}
export const GRAPHICS: Record<GraphicsQuality, GraphicsPreset> = {
  low: { dprCap: 1.25, bloom: false, speedBlur: false, cityDensity: 0.55, cityExtras: false, roadDetail: false, anisotropy: 2, particles: 0.5, roadTex: 256 },
  medium: { dprCap: 1.5, bloom: true, speedBlur: false, cityDensity: 0.8, cityExtras: true, roadDetail: true, anisotropy: 4, particles: 0.8, roadTex: 512 },
  high: { dprCap: 2, bloom: true, speedBlur: true, cityDensity: 1, cityExtras: true, roadDetail: true, anisotropy: 8, particles: 1, roadTex: 512 },
};
export const GRAPHICS_ORDER: GraphicsQuality[] = ['low', 'medium', 'high'];
/** the next preset when the player taps the Graphics setting */
export const nextGraphics = (q: GraphicsQuality): GraphicsQuality => GRAPHICS_ORDER[(GRAPHICS_ORDER.indexOf(q) + 1) % GRAPHICS_ORDER.length];

/**
 * v4.2 road surface (metres, road-local x: 0 = road centre). Marking positions are derived from the
 * gameplay LANES so the paint always sits between / beside the real lanes.
 */
export const ROAD = {
  /** half width of the road deck (the drivable plane) */
  half: 4.3,
  /** length covered by one road texture tile; every painted period below divides it */
  tile: 12,
  /** lane divider: width, dash length (of the tile) */
  dividerW: 0.12,
  dash: 3,
  /** edge line: centre distance from the road centre, width */
  edgeX: LANES[2] + LANE_WIDTH / 2 + 0.05,
  edgeW: 0.14,
  /** reflective studs: spacing along the lines, size */
  studEvery: 6,
  stud: 0.1,
  /** expansion joints (shader): spacing, width */
  jointEvery: 48,
  jointW: 0.035,
  /** polished tyre tracks: offset from each lane centre */
  trackX: 0.78,
  trackW: 0.42,
};
