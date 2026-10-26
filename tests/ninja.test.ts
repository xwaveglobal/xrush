/**
 * v7 ninja asset checks (src/assets/models/ninja.glb, built by assets-src/ninja/build_ninja_v3.py): the cape is its
 * own skinned mesh with a double-sided alpha-cutout material, the optional accessories are tagged so NinjaRig can hide
 * them (both hidden unless ?ninjaacc= asks for one), the six clips are there and the triangle budget holds.
 */
declare const process: { exit(code: number): never };
// @ts-expect-error node built-in (no @types/node in this project)
import { readFileSync } from 'node:fs';
import { RENDER } from '../src/config.ts';

let fails = 0;
const check = (ok: boolean, msg: string) => {
  if (!ok) {
    fails++;
    console.error('  ✗ ' + msg);
  } else console.log('  ✓ ' + msg);
};
const buf: Uint8Array = readFileSync(new URL('../src/assets/models/ninja.glb', import.meta.url));
const jsonLen = new DataView(buf.buffer, buf.byteOffset, buf.byteLength).getUint32(12, true);
const g = JSON.parse(new TextDecoder().decode(buf.subarray(20, 20 + jsonLen)));
const nodes: { name?: string; mesh?: number; skin?: number; extras?: Record<string, unknown> }[] = g.nodes;
const mats: { name?: string; alphaMode?: string; doubleSided?: boolean }[] = g.materials;
const tris = (mi: number) =>
  g.meshes[mi].primitives.reduce((s: number, p: { indices: number }) => s + g.accessors[p.indices].count / 3, 0);
const byName = (n: string) => nodes.find((x) => x.name === n);

const cape = byName('Ninja_Cape');
const body = byName('Ninja_Body');
check(!!body && body.skin !== undefined, 'Ninja_Body is a skinned mesh');
check(!!cape && cape.skin !== undefined, 'Ninja_Cape is its own skinned mesh');
const capeMat = mats.find((m) => m.name === 'Ninja_Cape');
check(!!capeMat && capeMat.alphaMode === 'MASK' && capeMat.doubleSided === true, 'cape material: alpha cutout (MASK) + double sided');
const bodyTris = tris(body!.mesh!) + tris(cape!.mesh!);
check(bodyTris <= 33000, `body + cape ≤ 33k tris (${bodyTris})`);
const accs = nodes.filter((n) => n.extras?.optional_accessory);
const tags = accs.map((n) => n.extras!.optional_accessory).sort();
check(JSON.stringify(tags) === JSON.stringify(['dagger', 'handprop']), `accessories tagged: ${tags.join(', ')}`);
check(RENDER.ninja.accessory === 'none', 'no accessory by default (hand prop / dagger only via ?ninjaacc=)');
const clips = (g.animations ?? []).map((a: { name: string }) => a.name).sort();
check(['Fall', 'Idle', 'Jump', 'Land', 'Run', 'Slide'].every((c) => clips.includes(c)), `clips: ${clips.join(', ')}`);
const capeJoints: string[] = g.skins[cape!.skin!].joints.map((j: number) => nodes[j].name);
check(['cape_C1', 'cape_L2', 'cape_R3'].every((n) => capeJoints.includes(n)), 'cape skinned to the cape chains');

if (fails) {
  console.error(`${fails} FAILED`);
  process.exit(1);
}
console.log('ALL PASSED');
