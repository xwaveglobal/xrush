import * as THREE from 'three';
import { RENDER } from '../../config.ts';
import { Spring, clamp, clamp01 } from '../../core/math.ts';
import { glowTexture } from '../textures.ts';
import { assetBytes, parseGlb } from './glbParse.ts';
import { ease, spoilerUpdate, wheelStep, type SpoilerState } from './carMotion.ts';
import { ShieldAura, installCarFx, makeCarFxUniforms } from './CarFx.ts';
import { CAR_HALF } from '../../config.ts';
import { x1BadgeCanvas, x1CarbonCanvas, x1FlakeCanvas, x1TreadCanvas } from './x1Textures.ts';
import x1Url from '../../assets/models/xwave-x1.glb';
import { NinjaRig } from './NinjaRig.ts';

/** what the 3D car needs from a colourway (subset of VehicleSkin) */
export interface MeshSkin {
  body: number;
  glow: number;
  accent: number;
  tintAmt?: number;
}

interface WheelRig {
  hub: THREE.Object3D;
  spin: THREE.Object3D;
  front: boolean;
  /** tyre radius in model metres (r = r0 × the current scale) */
  r0: number;
  /** wheel radius in game metres */
  r: number;
  blur: THREE.Mesh;
}

/**
 * The XWAVE X1 as a real 3D model (v4). Lives inside the Vehicle's pose groups, so it inherits the
 * car's position, bank, pitch, barrel rolls and squash exactly like the old rear image did; on top of
 * that it animates what an image could not: spinning wheel assemblies, front-wheel steer, a sprung
 * body (roll on lane changes, dip + pitch on landing) and nitro flames from the two rear sockets.
 *
 * Node names come from scripts/car/x1-builder.ts: Body, Wheel_FL/FR/RL/RR → Spin_xx, NitroSocket_L/R.
 */
export class MeshCar {
  /** placed by Vehicle (its y = ground offset under the car's pose origin) */
  root = new THREE.Group();
  ready = false;
  /** sprung part: pivot above the axles so roll / pitch turn around the car's centre, not the road */
  private bodyPivot = new THREE.Group();
  private wheels: WheelRig[] = [];
  private sockets: THREE.Object3D[] = [];
  private flames: THREE.Mesh[] = [];
  private flameMats: THREE.ShaderMaterial[] = [];
  private nozzles: THREE.Sprite[] = [];
  private nozzleMat: THREE.SpriteMaterial;
  /** the X1 node (its origin is on the road, so scaling it squashes the car toward the asphalt) */
  private model: THREE.Object3D | null = null;
  /** RENDER.player = 'ninja': the character replaces the X1 visual (same root, effects and API) */
  private ninja: NinjaRig | null = null;
  private baseScale = 1;
  /** v4.6 size multiplier (fixed camera view: RENDER.carScaleFixed / carScale) */
  private scaleK = 1;
  private get sc() {
    return this.baseScale * this.scaleK;
  }
  /** draw the car k × its normal size (visual only) — e.g. bigger for the fixed camera view */
  setScaleK(k: number) {
    this.scaleK = k;
    if (this.ninja) return this.ninja.setScaleK(k);
    if (this.model) this.model.scale.set(this.sc, this.sc * RENDER.carHeightScale, this.sc);
    for (const w of this.wheels) w.r = w.r0 * this.sc;
  }
  /** DOWN: 0 = normal … 1 = pressed down (spring: a little overshoot in and out) */
  private duckS = new Spring(0, 320, 20);
  private hover: THREE.Mesh;
  private padMat: THREE.MeshBasicMaterial;
  /** edge light uniforms shared by all car materials (ghost rim, pickup sweep) */
  fx = makeCarFxUniforms();
  /** shield aura (follows the car pose) */
  aura = new ShieldAura();
  /** Turbo aura: Turbo smashes obstacles, so it gets the same kind of shell, in its own colour */
  turboAura = new ShieldAura(RENDER.turboAura);
  /** Turbo level 0..1 — set by Vehicle from the gameplay Turbo state */
  turbo = 0;
  /** shield level 0..1 — set by Vehicle from the gameplay shield state (fades over a timed shield's end) */
  shield = 0;
  private sweepT = 99;
  private mats = new Map<string, THREE.MeshStandardMaterial>();
  private orig = new Map<THREE.MeshStandardMaterial, { color: number; emissive: number; ei: number }>();
  private roll = new Spring(0, 140, 16);
  private pitch = new Spring(0, 160, 14);
  private dip = new Spring(0, 220, 16);
  private yaw = new Spring(0, 140, 16);
  /** active spoiler: pivot (hinge at the front edge) and 0..1 deployment */
  private spoiler: THREE.Object3D | null = null;
  private spoilerState: SpoilerState = { k: 0, hold: 0 };
  private spoilerBaseY = 0;
  get spoilerK() {
    return this.spoilerState.k;
  }
  /** how far the 3D nose reaches ahead of the gameplay hitbox (m, in game) */
  noseOverhang = 0;
  /** previews / tests: force the spoiler target (null = follow nitro) */
  spoilerForce: number | null = null;
  /** Phase Ghost: materials' own transparency, restored when the effect ends */
  private fadeState: { m: THREE.Material; transparent: boolean; opacity: number; depthWrite: boolean }[] = [];
  private fade = 1;
  private fadeSolid = true;
  private wheelV = 0;
  private prevAir = 0;
  private t = 0;
  /** 0..1 nitro look (set by Vehicle from the boost envelope) */
  nitro = 0;
  onReady: (() => void) | null = null;

  constructor() {
    this.root.visible = false;
    // nitro thrust (v4.1.3): three nested additive cones per socket — white-blue core, cyan body,
    // violet-tinted outer veil — each fading along its length and toward its edges (tapered, soft,
    // no hard cone outline, nothing opaque over the rear LED)
    const layer = (inner: number, outer: number, len: number, edge: number) =>
      new THREE.ShaderMaterial({
        uniforms: { k: { value: 0 }, inner: { value: new THREE.Color(inner) }, outer: { value: new THREE.Color(outer) }, len: { value: len }, edge: { value: edge }, t: { value: 0 } },
        vertexShader: `varying float vA; varying vec3 vN; varying vec3 vV;
          void main(){ vA = position.z; vec4 mv = modelViewMatrix * vec4(position, 1.0); vN = normalize(normalMatrix * normal); vV = normalize(-mv.xyz); gl_Position = projectionMatrix * mv; }`,
        fragmentShader: `uniform float k; uniform vec3 inner; uniform vec3 outer; uniform float len; uniform float edge; uniform float t; varying float vA; varying vec3 vN; varying vec3 vV;
          void main(){
            float a = clamp(vA, 0.0, 1.0);
            float along = pow(1.0 - a, 1.6) * smoothstep(0.0, 0.06, a);
            float face = pow(abs(dot(normalize(vN), normalize(vV))), edge);
            float flick = 0.9 + 0.1 * sin(t * 47.0 + a * 20.0);
            gl_FragColor = vec4(mix(inner, outer, a) * along * face * k * flick, 1.0);
          }`,
        transparent: true,
        depthWrite: false,
        blending: THREE.AdditiveBlending,
        side: THREE.DoubleSide,
        toneMapped: false,
      });
    this.flameMats = [layer(0x9fe8ff, 0x8a5cff, 1, 1.2), layer(0x6fd6ff, 0x2f7dff, 0.8, 1.0), layer(0xffffff, 0x9fe8ff, 0.5, 0.6)];
    this.nozzleMat = new THREE.SpriteMaterial({ map: glowTexture(), color: 0x7fdcff, transparent: true, opacity: 0, depthWrite: false, blending: THREE.AdditiveBlending, toneMapped: false });
    // DOWN: soft light pool on the road under the car
    this.padMat = new THREE.MeshBasicMaterial({ map: glowTexture(), color: 0x39b6ff, transparent: true, opacity: 0, depthWrite: false, blending: THREE.AdditiveBlending, toneMapped: false });
    this.hover = new THREE.Mesh(new THREE.PlaneGeometry(1, 1), this.padMat);
    this.hover.rotation.x = -Math.PI / 2;
    this.hover.scale.set(2.4, 4.4, 1);
    this.hover.position.set(0, 0.02, 0.05);
    this.hover.visible = false;
    this.hover.renderOrder = 2;
    this.root.add(this.hover);
    this.root.add(this.aura.mesh, this.turboAura.mesh);
    void this.load();
  }

  private async load() {
    if (RENDER.player === 'ninja') {
      try {
        this.buildNinja(await NinjaRig.load());
        return;
      } catch (e) {
        console.warn('[ninja] character unavailable, using the X1 car', e);
      }
    }
    try {
      this.build(parseGlb(await assetBytes(x1Url)));
    } catch (e) {
      console.warn('[car] 3D model unavailable, keeping the rear image', e);
    }
  }

  private build(scene: THREE.Group) {
    const s = RENDER.carScale;
    const model = scene.getObjectByName('X1') ?? scene;
    model.scale.set(s * this.scaleK, s * RENDER.carHeightScale * this.scaleK, s * this.scaleK);
    this.model = model;
    this.baseScale = s;
    // materials by name: procedural textures + in-game glow levels (the GLB's images are not decoded)
    model.traverse((o) => {
      const m = (o as THREE.Mesh).material as THREE.MeshStandardMaterial | undefined;
      if (!m || this.mats.has(m.name)) return;
      this.mats.set(m.name, m);
      (o as THREE.Mesh).castShadow = false;
    });
    const tex = (c: HTMLCanvasElement, srgb = true) => {
      const t = new THREE.CanvasTexture(c);
      t.colorSpace = srgb ? THREE.SRGBColorSpace : THREE.NoColorSpace;
      t.wrapS = t.wrapT = THREE.RepeatWrapping;
      t.anisotropy = 4;
      return t;
    };
    const badge = this.mats.get('X1_Badge');
    if (badge) {
      const bt = tex(x1BadgeCanvas());
      bt.wrapS = bt.wrapT = THREE.ClampToEdgeWrapping;
      badge.map = bt;
      badge.emissiveMap = bt;
      badge.transparent = true;
      badge.alphaTest = 0.05;
      badge.emissiveIntensity = RENDER.badgeGlow;
    }
    const carbon = this.mats.get('X1_Carbon');
    if (carbon) carbon.map = tex(x1CarbonCanvas());
    const tyre = this.mats.get('X1_Tyre');
    if (tyre) tyre.map = tex(x1TreadCanvas());
    // v4.3 (Step 06 PBR): metallic flake in the base coat under the smooth clearcoat (UVs in metres)
    const paint = this.mats.get('X1_Paint');
    if (paint) {
      const ft = tex(x1FlakeCanvas(), false);
      ft.repeat.set(RENDER.paintFlakeRepeat, RENDER.paintFlakeRepeat);
      paint.normalMap = ft;
      paint.normalScale.set(RENDER.paintFlake, RENDER.paintFlake);
    }
    // lights: exact colours (no tone-map hue shift to orange) and strong enough to bloom
    for (const [name, k] of [['X1_RearLED', RENDER.ledGlow], ['X1_RearLEDCore', RENDER.ledGlow], ['X1_RedMarker', RENDER.markerGlow], ['X1_Headlight', 0], ['X1_SeatTrim', 0], ['X1_Badge', 0]] as const) {
      const m = this.mats.get(name);
      if (!m) continue;
      m.toneMapped = false;
      if (k) m.emissiveIntensity = k;
    }
    const glass = this.mats.get('X1_Glass');
    if (glass) glass.envMapIntensity = 0.18; // dark tint, soft highlight (no glare blob from the sun)
    for (const [name, k] of [['X1_Headlight', RENDER.headGlow], ['X1_HeadlightCore', RENDER.headGlow]] as const) {
      const m = this.mats.get(name);
      if (m) {
        m.toneMapped = false;
        m.emissiveIntensity = k;
      }
    }
    // edge light (Phase Ghost rim, pickup sweep) compiled into every car material up front
    for (const m of this.mats.values()) installCarFx(m, this.fx);
    this.spoiler = model.getObjectByName('Spoiler_Pivot') ?? null;
    if (this.spoiler) this.spoilerBaseY = this.spoiler.position.y;
    for (const m of this.mats.values()) {
      this.orig.set(m, { color: m.color.getHex(), emissive: m.emissive.getHex(), ei: m.emissiveIntensity });
      this.fadeState.push({ m, transparent: m.transparent, opacity: m.opacity, depthWrite: m.depthWrite });
    }

    // sprung body: re-parent under a pivot at axle height
    const body = model.getObjectByName('Body');
    if (body) {
      const py = 0.5;
      this.bodyPivot.position.set(0, py, 0);
      body.position.y -= py;
      model.add(this.bodyPivot);
      this.bodyPivot.add(body);
    }
    // wheels (radius from the tyre's bounds) + a speed blur disc on each rim face
    const blurTex = glowTexture();
    for (const id of ['FL', 'FR', 'RL', 'RR']) {
      const hub = model.getObjectByName(`Wheel_${id}`);
      const spin = model.getObjectByName(`Spin_${id}`);
      const tyreM = model.getObjectByName(`Tyre_${id}`) as THREE.Mesh | undefined;
      if (!hub || !spin || !tyreM) continue;
      // v4.6 taller body: the wheels keep their real shape and stay on the road (undo the height scale
      // on the wheel; its hub stays at the same height above the road)
      hub.scale.y = 1 / RENDER.carHeightScale;
      hub.position.y /= RENDER.carHeightScale;
      tyreM.geometry.computeBoundingBox();
      const bb = tyreM.geometry.boundingBox!;
      const r = (bb.max.y - bb.min.y) / 2;
      const w = bb.max.x - bb.min.x;
      const side = hub.position.x < 0 ? -1 : 1;
      const blur = new THREE.Mesh(
        new THREE.CircleGeometry(r * 0.72, 24),
        new THREE.MeshBasicMaterial({ map: blurTex, color: 0x15171b, transparent: true, opacity: 0, depthWrite: false }),
      );
      blur.rotation.y = (side * Math.PI) / 2;
      blur.position.x = side * (w * 0.5 + 0.004);
      hub.add(blur);
      this.wheels.push({ hub, spin, front: id[0] === 'F', r: r * s * this.scaleK, r0: r, blur });
    }
    // nitro sockets → flames
    for (const id of ['NitroSocket_L', 'NitroSocket_R']) {
      const so = model.getObjectByName(id);
      if (so) this.addThrust(so);
    }
    this.root.add(model);
    model.updateMatrixWorld(true);
    const box = new THREE.Box3().setFromObject(model);
    this.noseOverhang = Math.max(0, -box.min.z - CAR_HALF.z);
    this.zFront = box.min.z;
    this.zBack = box.max.z;
    this.ready = true;
    this.onReady?.();
  }

  /** the ninja character: its materials get the same edge light / ghost fade as the X1's */
  private buildNinja(n: NinjaRig) {
    this.ninja = n;
    this.model = n.root;
    n.setScaleK(this.scaleK);
    for (const m of n.materials) this.mats.set(m.name, m);
    for (const m of this.mats.values()) {
      installCarFx(m, this.fx);
      this.orig.set(m, { color: m.color.getHex(), emissive: m.emissive.getHex(), ei: m.emissiveIntensity });
      this.fadeState.push({ m, transparent: m.transparent, opacity: m.opacity, depthWrite: m.depthWrite });
    }
    for (const so of n.sockets) this.sockets.push(so); // trail anchors only: no nitro flames on the character (car-only look)
    this.root.add(n.root);
    n.root.updateMatrixWorld(true);
    const box = new THREE.Box3().setFromObject(n.root);
    this.zFront = box.min.z;
    this.zBack = box.max.z;
    this.ready = true;
    this.onReady?.();
  }

  /** nitro thrust flames + nozzle glow on one socket */
  private addThrust(so: THREE.Object3D) {
    {
      this.sockets.push(so);
      for (const [i, rad] of [0.16, 0.1, 0.05].entries()) {
        // cone from the socket (z 0, wide end) to the tip (z 1)
        const geo = new THREE.CylinderGeometry(rad * 0.25, rad, 1, 16, 4, true);
        geo.translate(0, 0.5, 0);
        geo.rotateX(Math.PI / 2);
        const f = new THREE.Mesh(geo, this.flameMats[i]);
        f.visible = false;
        f.renderOrder = 5 + i;
        f.frustumCulled = false;
        so.add(f);
        this.flames.push(f);
      }
      const nz = new THREE.Sprite(this.nozzleMat);
      nz.scale.setScalar(0.42);
      nz.position.z = 0.02;
      nz.visible = false;
      nz.renderOrder = 8;
      so.add(nz);
      this.nozzles.push(nz);
    }
  }

  /** colourway + locked (dark silhouette) preview */
  applySkin(skin: MeshSkin, locked: boolean) {
    if (!this.ready) return;
    for (const [m, o] of this.orig) {
      m.color.setHex(o.color);
      m.emissive.setHex(o.emissive);
      m.emissiveIntensity = o.ei;
    }
    const paint = this.mats.get('X1_Paint');
    if (paint && (skin.tintAmt ?? 0) > 0) paint.color.setHex(skin.body);
    for (const n of ['X1_Headlight']) {
      const m = this.mats.get(n);
      if (m) {
        m.color.setHex(skin.glow);
        m.emissive.setHex(skin.glow);
      }
    }
    if (locked) {
      for (const m of this.mats.values()) {
        m.color.multiplyScalar(0.06);
        m.emissiveIntensity = 0;
      }
    }
    this.padMat.color.setHex(skin.glow);
  }

  /**
   * @param speed road speed (m/s)
   * @param lat lateral speed in lane-speeds (−1.4 … 1.4, + = moving right)
   * @param air 0 on the road … 1 airborne
   * @param jumping gameplay jump state (Player.vmode === 'up': take-off → airborne → touch-down)
   * @param duck gameplay DOWN depth 0..1 (from Player.squash while vmode === 'down')
   */
  update(dt: number, speed: number, lat: number, air: number, locked: boolean, jumping = false, duck = 0) {
    if (!this.ready) return;
    this.t += dt;
    if (this.ninja) {
      this.ninja.update(dt, speed, lat, air, locked, jumping, duck);
      this.updateFx(dt, speed, locked);
      return;
    }
    // ---- DOWN (dive under a beam): the whole car presses down toward the road — squashes low and a
    // little wider/longer, with a small spring overshoot on entry and on release (arcade squash).
    // Wheels stay on the asphalt; a soft light pool under the car reads as "skimming the road".
    const D = RENDER.duck;
    this.duckS.target = locked ? 0 : clamp01(duck);
    this.duckS.update(dt);
    const e = Math.max(0, this.duckS.value);
    if (this.model) this.model.scale.set(this.sc * (1 + D.widen * e), this.sc * RENDER.carHeightScale * (1 - D.squash * e), this.sc * (1 + D.stretch * e));
    this.padMat.opacity = 0.8 * clamp01(e);
    this.hover.visible = e > 0.02;
    // ---- wheels: spin with the road (free-wheel and slow down in the air), capped against strobing
    const onRoad = air < 0.05;
    this.wheelV = onRoad ? speed : this.wheelV * Math.exp(-0.45 * dt);
    const blurK = clamp01((this.wheelV - RENDER.wheelBlurFrom) / (RENDER.wheelBlurFull - RENDER.wheelBlurFrom));
    for (const w of this.wheels) {
      const step = wheelStep(this.wheelV, w.r, dt, RENDER.wheelMaxStep);
      w.spin.rotation.x -= step; // top of the wheel moves forward (−z)
      if (w.front) w.hub.rotation.y = -lat * RENDER.steer * (1 - air);
      (w.blur.material as THREE.MeshBasicMaterial).opacity = 0.75 * blurK;
    }
    // ---- sprung body: roll against the lane change, dip + nose-down kick on landing
    if (this.prevAir > 0.3 && onRoad) {
      this.dip.velocity -= RENDER.landDip * 9 * clamp01(this.prevAir);
      this.pitch.velocity += RENDER.landPitch * 9 * clamp01(this.prevAir);
    }
    this.prevAir = air;
    this.roll.target = lat * RENDER.bodyRoll * (1 - air);
    this.yaw.target = -lat * RENDER.bodyYaw;
    this.yaw.update(dt);
    this.pitch.target = 0;
    this.dip.target = 0;
    this.roll.update(dt);
    this.pitch.update(dt);
    this.dip.update(dt);
    // light road buzz at speed (sub-centimetre) so the body feels planted, not glued
    const buzz = (Math.sin(this.t * 41) * 0.5 + Math.sin(this.t * 67) * 0.3) * 0.004 * clamp01(speed / 30) * (1 - air);
    this.bodyPivot.rotation.set(clamp(this.pitch.value, -0.08, 0.08), clamp(this.yaw.value, -0.04, 0.04), clamp(this.roll.value, -0.06, 0.06));
    this.bodyPivot.position.y = 0.5 + clamp(this.dip.value, -0.08, 0.04) + buzz;
    // ---- active spoiler (pop-up), Step 06.5: open ONLY while airborne (`jumping` = gameplay flight
    // state); rises off the deck and tilts on its hinge; closes flush from ground contact (Turbo never opens it)
    if (this.spoilerForce !== null) this.spoilerState.k = this.spoilerForce;
    else spoilerUpdate(this.spoilerState, !locked && jumping, dt, RENDER.spoilerUp, RENDER.spoilerDown, RENDER.spoilerHold);
    if (this.spoiler) {
      const sk = ease(this.spoilerState.k);
      this.spoiler.rotation.x = -RENDER.spoilerAngle * sk;
      this.spoiler.position.y = this.spoilerBaseY + RENDER.spoilerRise * sk;
    }
    this.updateFx(dt, speed, locked);
  }

  /** nitro thrust, shield / Turbo aura, pickup sweep (X1 and ninja) */
  private updateFx(dt: number, speed: number, locked: boolean) {
    // ---- nitro thrust from the sockets: length follows the boost and (a little) the speed
    const k = locked ? 0 : clamp01(this.nitro);
    const show = k > 0.02;
    const fl = (0.35 + 0.65 * k) * (0.85 + 0.3 * clamp01(speed / 60)) * RENDER.nitroLen / RENDER.carScale;
    const lens = [1, 0.78, 0.48];
    const amps = [0.6, 0.9, 1.2];
    for (let i = 0; i < this.flames.length; i++) {
      const f = this.flames[i];
      f.visible = show;
      f.scale.set(1, 1, fl * lens[i % 3]);
    }
    for (let i = 0; i < 3; i++) {
      this.flameMats[i].uniforms.k.value = k * amps[i];
      this.flameMats[i].uniforms.t.value = this.t;
    }
    for (const n of this.nozzles) n.visible = show;
    this.nozzleMat.opacity = 0.6 * k;
    // ---- shield aura + pickup light sweep
    this.aura.update(dt, locked ? 0 : this.shield);
    this.turboAura.update(dt, locked ? 0 : this.turbo);
    if (this.sweepT < RENDER.sweepTime) {
      this.sweepT += dt;
      const u = Math.min(1, this.sweepT / RENDER.sweepTime);
      this.root.getWorldPosition(this.tmpV);
      this.fx.uFxSweepZ.value = this.tmpV.z + this.zFront - 0.2 + (this.zBack - this.zFront + 0.4) * u;
      this.fx.uFxSweep.value = Math.sin(Math.PI * u) * 1.1;
    } else this.fx.uFxSweep.value = 0;
  }
  private tmpV = new THREE.Vector3();
  /** front / back of the car (game metres, relative to the root) — for the light sweep */
  private zFront = -1.5;
  private zBack = 1.7;

  /** a short light sweep over the body, front to back (booster / power-up pickup) */
  sweep(color: number) {
    this.fx.uFxSweepColor.value.setHex(color);
    this.sweepT = 0;
  }

  /** Phase Ghost: 0 = normal … 1 = translucent car with a cyan edge (materials restored exactly at 0) */
  setGhost(e: number) {
    this.fx.uFxGhost.value = RENDER.ghostRim * e;
    this.setFade(1 - (1 - RENDER.ghostOpacity) * e);
  }

  /** Phase Ghost: 1 = solid, lower = translucent (materials restored exactly at 1) */
  setFade(k: number) {
    if (Math.abs(k - this.fade) < 0.005 && !(k === 1 && this.fade !== 1)) return;
    this.fade = k;
    const solid = k >= 0.995;
    if (solid) this.fade = 1;
    const flip = solid !== this.fadeSolid;
    this.fadeSolid = solid;
    for (const f of this.fadeState) {
      f.m.transparent = solid ? f.transparent : true;
      f.m.opacity = solid ? f.opacity : f.opacity * k;
      f.m.depthWrite = solid ? f.depthWrite : false;
      if (flip) f.m.needsUpdate = true; // only when switching between solid and translucent
    }
  }

  /** materials are exactly as loaded (no ghost / fade state left) — tests */
  get materialsRestored() {
    return this.fadeState.every((f) => f.m.transparent === f.transparent && f.m.opacity === f.opacity && f.m.depthWrite === f.depthWrite) && this.fx.uFxGhost.value === 0;
  }

  /** crash: the body jolts on its springs (nose dips, a little roll), wheels stop */
  crashJolt() {
    this.pitch.velocity += 2.2;
    this.dip.velocity -= 0.8;
    this.roll.velocity += (Math.sin(this.t * 7.3) > 0 ? 1 : -1) * 0.9;
  }

  /**
   * after a crash (dying / game over): the springs settle, nitro and shield fade, the spoiler retracts
   * to its flush rest — a defined, stable final pose.
   */
  settle(dt: number) {
    this.nitro = 0;
    this.shield = 0;
    this.turbo = 0;
    this.update(dt, 0, 0, 0, false, false, 0);
  }

  /** compile every effect variant once (ghost transparency, aura, thrust) so none compiles mid-race */
  prewarm(renderer: THREE.WebGLRenderer, scene: THREE.Object3D, camera: THREE.Camera) {
    if (!this.ready) return;
    const was = this.root.visible;
    this.root.visible = true;
    const show = [...this.flames, ...this.nozzles, this.aura.mesh, this.turboAura.mesh, this.hover];
    for (const o of show) o.visible = true;
    this.setFade(0.5);
    renderer.compile(scene, camera);
    this.setFade(1);
    renderer.compile(scene, camera);
    for (const o of show) o.visible = false;
    this.root.visible = was;
  }

  // ---- Step 06.5: parts that break off on the run-ending crash (same meshes, re-parented and moved)
  private broken: { o: THREE.Object3D; parent: THREE.Object3D; pos: THREE.Vector3; quat: THREE.Quaternion; pivot: THREE.Object3D; v: THREE.Vector3; w: THREE.Vector3; half: number; rest: boolean }[] = [];
  /** detach a few named parts into `world` (their world pose kept) and throw them off the car */
  breakParts(world: THREE.Object3D, names: readonly string[]) {
    if (!this.model || this.broken.length) return;
    this.model.updateWorldMatrix(true, true);
    let k = 0;
    for (const name of names) {
      const o = this.model.getObjectByName(name);
      if (!o || !o.parent) continue;
      const box = new THREE.Box3().setFromObject(o);
      if (box.isEmpty()) continue;
      const c = box.getCenter(new THREE.Vector3());
      const pivot = new THREE.Group();
      pivot.position.copy(c);
      world.add(pivot);
      const rec = { o, parent: o.parent, pos: o.position.clone(), quat: o.quaternion.clone(), pivot, v: new THREE.Vector3(), w: new THREE.Vector3(), half: (box.max.y - box.min.y) / 2, rest: false };
      pivot.attach(o); // keeps the world pose: nothing jumps at the moment of the break
      const side = k % 2 ? 1 : -1;
      // the car stopped at the obstacle; loose parts carry on a little (ahead = −z) and off to the sides
      rec.v.set(side * (1.4 + k * 0.6), 3.0 + k * 0.8, -(0.8 + k * 0.7));
      rec.w.set(4 + k * 2, side * 3, side * (5 - k));
      this.broken.push(rec);
      k++;
    }
  }
  /** broken parts: fall, bounce, tumble, come to rest on the road (y = 0); resting parts move with the
   *  road (which is braking to a stop under the crashed car) */
  updateParts(dt: number, roadSpeed: number, gravity: number) {
    for (const b of this.broken) {
      const p = b.pivot;
      if (b.rest) {
        p.position.z += roadSpeed * dt;
        continue;
      }
      b.v.y -= gravity * dt;
      p.position.addScaledVector(b.v, dt);
      p.rotation.x += b.w.x * dt;
      p.rotation.y += b.w.y * dt;
      p.rotation.z += b.w.z * dt;
      if (p.position.y < b.half) {
        p.position.y = b.half;
        if (Math.abs(b.v.y) > 1.2) {
          b.v.y = -b.v.y * 0.3;
          b.v.x *= 0.5;
          b.v.z *= 0.5;
          b.w.multiplyScalar(0.45);
        } else b.rest = true;
      }
    }
  }
  /** put every broken part back on the car */
  restoreParts() {
    for (const b of this.broken) {
      b.parent.add(b.o);
      b.o.position.copy(b.pos);
      b.o.quaternion.copy(b.quat);
      b.pivot.removeFromParent();
    }
    this.broken.length = 0;
  }
  get partsBroken() {
    return this.broken.length;
  }

  /** settle the sprung body instantly (respawn / menu) */
  resetPose() {
    this.restoreParts();
    this.yaw.snap(0);
    this.spoilerState.k = 0;
    this.spoilerState.hold = 0;
    this.roll.snap(0);
    this.pitch.snap(0);
    this.dip.snap(0);
    this.prevAir = 0;
    this.duckS.snap(0);
    this.duckS.velocity = 0;
    if (this.model && !this.ninja) this.model.scale.set(this.sc, this.sc * RENDER.carHeightScale, this.sc);
    this.ninja?.reset();
    this.aura.reset();
    this.turboAura.reset();
    this.sweepT = 99;
    this.fx.uFxSweep.value = 0;
  }

  /** world position of nitro socket i (for trail particles) */
  socketWorld(i: number, out: THREE.Vector3) {
    const so = this.sockets[i % Math.max(1, this.sockets.length)];
    if (!so) return out.set(0, 0, 0);
    return so.getWorldPosition(out);
  }
}
