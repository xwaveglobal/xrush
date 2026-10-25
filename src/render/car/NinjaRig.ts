import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { RENDER } from '../../config.ts';
import { clamp } from '../../core/math.ts';
import { assetBytes } from './glbParse.ts';
import ninjaUrl from '../../assets/models/ninja.glb';

/** the six in-place clips baked by assets-src/ninja/build_ninja_v3.py (same clips as build_ninja.py) */
export type NinjaClip = 'Idle' | 'Run' | 'Jump' | 'Fall' | 'Land' | 'Slide';

/** what the game state asks for this frame (pure, so it can be checked without WebGL) */
export function pickNinjaClip(
  cur: NinjaClip,
  s: { speed: number; locked: boolean; airborne: boolean; rising: boolean; duck: number; landing: boolean },
): NinjaClip {
  if (s.locked || s.speed < 0.5) return 'Idle';
  if (s.duck > 0.05) return 'Slide';
  if (s.airborne) return s.rising && cur !== 'Fall' ? 'Jump' : 'Fall';
  if (s.landing) return 'Land';
  return 'Run';
}

/**
 * The chibi ninja player character (RENDER.player = 'ninja'): a skinned GLB with its own PBR
 * textures, driven by an AnimationMixer from the same values MeshCar gets for the X1. Visual only:
 * it sits in MeshCar.root (so it inherits the car's lane position, bank, jumps and squash) and never
 * touches hitboxes, camera or timings.
 *
 * Wrapper node: glTF faces +Z, the game drives toward −Z → turned 180°; scaled to RENDER.ninja.scale;
 * the model's origin is between the feet, so it stands on MeshCar.root (= the road).
 */
export class NinjaRig {
  /** wrapper (rotation / scale / offset) — the model's own root transform stays untouched */
  root = new THREE.Group();
  materials: THREE.MeshStandardMaterial[] = [];
  /** nitro sockets on the back (MeshCar hangs its thrust flames on them) */
  sockets: THREE.Object3D[] = [];
  private mixer: THREE.AnimationMixer;
  private actions = new Map<NinjaClip, THREE.AnimationAction>();
  private cur: NinjaClip = 'Idle';
  private prevY = NaN;
  private vy = 0;
  private wasAir = false;
  private landT = 0;
  private yaw = 0;
  private tmp = new THREE.Vector3();

  static async load(): Promise<NinjaRig> {
    const gltf = await new GLTFLoader().parseAsync(await assetBytes(ninjaUrl), '');
    return new NinjaRig(gltf.scene, gltf.animations);
  }

  constructor(scene: THREE.Group, clips: THREE.AnimationClip[]) {
    this.root.name = 'NinjaWrapper';
    this.root.rotation.y = Math.PI;
    this.root.add(scene);
    const acc = RENDER.ninja.accessory;
    const seen = new Set<THREE.Material>();
    scene.traverse((o) => {
      const tag = o.userData.optional_accessory as string | undefined;
      if (tag) o.visible = tag === acc; // dagger / hand prop: hidden by default, at most one shown
      const mesh = o as THREE.Mesh;
      if (!mesh.isMesh) return;
      mesh.frustumCulled = false; // skinned: the bind-pose bounds do not follow the animation
      mesh.castShadow = false;
      for (const m of Array.isArray(mesh.material) ? mesh.material : [mesh.material]) {
        if (seen.has(m) || !(m as THREE.MeshStandardMaterial).isMeshStandardMaterial) continue;
        seen.add(m);
        const sm = m as THREE.MeshStandardMaterial;
        sm.color.multiplyScalar(RENDER.ninja.bright);
        sm.envMapIntensity = RENDER.ninja.env;
        this.materials.push(sm);
      }
    });
    for (const x of [-1, 1]) {
      // lower back, behind the cape; flames point backward (+Z in game = −Z in the turned model)
      const so = new THREE.Object3D();
      so.position.set(x * 0.09, 0.34, -0.2);
      so.rotation.y = Math.PI;
      this.root.add(so);
      this.sockets.push(so);
    }
    this.mixer = new THREE.AnimationMixer(scene);
    for (const c of clips) {
      const a = this.mixer.clipAction(c);
      if (c.name === 'Jump' || c.name === 'Land') {
        a.setLoop(THREE.LoopOnce, 1);
        a.clampWhenFinished = true;
      }
      this.actions.set(c.name as NinjaClip, a);
    }
    this.actions.get('Idle')?.play();
    this.setScaleK(1);
  }

  setScaleK(k: number) {
    const s = RENDER.ninja.scale * k;
    this.root.scale.setScalar(s);
    // thrust flames are sized for the X1 (inside carScale): keep them that size on the ninja
    for (const so of this.sockets) so.scale.setScalar((RENDER.carScale * RENDER.ninja.thrust) / s);
  }

  private play(name: NinjaClip) {
    if (name === this.cur) return;
    const next = this.actions.get(name);
    const prev = this.actions.get(this.cur);
    if (!next) return;
    next.reset().setEffectiveWeight(1).fadeIn(RENDER.ninja.fade).play();
    prev?.fadeOut(RENDER.ninja.fade);
    this.cur = name;
  }

  get clip() {
    return this.cur;
  }

  /** same inputs as MeshCar.update (speed m/s, lat lane-speeds, air 0..1, jumping, duck 0..1) */
  update(dt: number, speed: number, lat: number, air: number, locked: boolean, jumping: boolean, duck: number) {
    // vertical speed of the character (world), for jump vs fall
    this.root.getWorldPosition(this.tmp);
    if (dt > 0 && Number.isFinite(this.prevY)) this.vy += ((this.tmp.y - this.prevY) / dt - this.vy) * (1 - Math.exp(-14 * dt));
    this.prevY = this.tmp.y;
    const airborne = !locked && (jumping || air > 0.05);
    if (this.wasAir && !airborne) this.landT = RENDER.ninja.landTime;
    this.wasAir = airborne;
    this.landT = Math.max(0, this.landT - dt);
    const name = pickNinjaClip(this.cur, { speed, locked, airborne, rising: this.vy > 0.4, duck: locked ? 0 : duck, landing: this.landT > 0 });
    this.play(name);
    const run = this.actions.get('Run');
    if (run) run.timeScale = clamp(speed / RENDER.ninja.runRate, 0.85, 1.9);
    const land = this.actions.get('Land');
    if (land) land.timeScale = land.getClip().duration / RENDER.ninja.landTime;
    // turn a little toward the lane change (the car's bank / pose groups still apply on top)
    this.yaw += (-lat * RENDER.ninja.laneYaw * (airborne ? 0.5 : 1) - this.yaw) * (1 - Math.exp(-10 * dt));
    this.root.rotation.y = Math.PI + this.yaw;
    this.mixer.update(dt);
  }

  /** respawn / menu: back to a calm idle */
  reset() {
    for (const a of this.actions.values()) a.stop();
    this.cur = 'Idle';
    this.actions.get('Idle')?.reset().play();
    this.prevY = NaN;
    this.vy = 0;
    this.wasAir = false;
    this.landT = 0;
    this.yaw = 0;
    this.root.rotation.y = Math.PI;
  }
}
