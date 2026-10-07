# Development notes

Format findings and version history from building the converter (kept for contributors).


Convert N64 OoT player models (ML64 / zzplayas `.zobj`) into OoT3D adult/child Link models.

## End goal (revised 2026-10-07)

One command turns an ML64 / zzplayas player mod into a ready-to-copy OoT3D LayeredFS folder:

1. **Body** (done, confirmed in Citra): body, head, hands, gauntlets, boots, tunic swap, blinking.
2. **Equipment**: the zobj's own swords, shields, bow, hookshot, hammer, bottle, ocarina,
   sheath and back-items replace OoT3D's item meshes in the same mesh groups.
3. **First-person arms**: identify groups 26-28/30/34 and map the FPS display lists.
4. **Voice**: an ML64 voice pack (`.pak`, folders named by N64 sound ID with one or more
   `.ogg` each, one picked at random) replaces Link's voice in `sound/QueenSound.bcsar`.
   N64 IDs map to OoT3D's `NA_SE_VO_LI_*` sounds (adult) / `*_KID` (child).
5. **Child Link** (`zelda_link_child_new.zar`) and the `*_ultra.zar` variants.

## Progress on the end goal (2026-10-07)

- Equipment (v7): groups 0-3, 31, 42 (back items), 16, 37, 38, 32 (left hand items), 23, 39, 29,
  33, 40, 41 (right hand items), 25 (bottle) rebuilt from the zobj LUT display lists; back items use
  the zobj's MATRIX_SWORD_BACK (0x5010) / MATRIX_SHIELD_BACK (0x5050). Groups 7-12 keep OoT3D's
  Biggoron scabbard with the zobj's shields. Known gap: the N64 Mirror Shield's environment-mapped
  front has no equivalent yet (renders flat).
- v9: first-person groups 26 (FPS_LFOREARM), 27 (FPS_LHAND, far speck dropped), 28 (R shoulder limb +
  FPS_RFOREARM), 30 (FPS_RHAND + BOW), 34 (FPS_RHAND + FPS_HOOKSHOT). Bottle: ENV part -> Link's mat 3
  (contents; the game sets its constant colour 3), rest -> mat 2 (glass), both translucent.
  Gauntlets: ENV baked to N64 silver (OoT3D has one gauntlet mesh set).
- v10: N64 colour combiner evaluated per texel (`zobj.combine_rgb`, 1/2-cycle aware) and baked into
  textures, so PRIM/ENV colours set by the model (e.g. red Mirror Shield rim, PRIM 208 grey) survive.
  TEXGEN (geometry mode 0x40000) materials get texture coordinator 0 mapping = 3 (camera sphere env
  map), the 3DS equivalent; used by Mirror Shield, broken Giant's Knife, bottle, hook, belt buckle.
- v15 (current bow): zobj bow fitted onto Link's bow tips + grip (so the game's string meets it);
  the hand pivots about the wrist (~12 deg) to follow the grip, keeping the wrist joined.
- v14 (rejected in-game): bow left at the N64 placement. OoT3D's bow string is
  Link mesh 107 (group 43, bone 23), placed by game code to meet Link's 3D bow tips; its frame is
  inferred from Link's bow (tips, bulge, string length) and the string's tip vertices are moved onto
  the zobj bow tips. Gauntlets: ENV-tinted part -> Link's mat 14 (constant colour 4 set by the game
  per strength upgrade, silver / gold).
- v16 OoT3D Randomizer compatibility (gamestabled/OoT3D_Randomizer): with Custom Tunic Colors it
  patches link_v2.cmb at fixed vanilla offsets (mat 1 combiner list, combiners 2/3/11, tex entry 1,
  plus 0x4C52 for adult deku stick) and swaps in its own link_body.cmab (greyscale Link tunic
  ETC1A4 + ConstColor anim on mat 1 constant 0 carrying the chosen colours). The build applies the
  same combiner edits itself (mat 1 constant 0 = white without the rando), pads the material array so
  every other rando write lands in unused dummy materials (36, 37, 47, 52), and puts the tunic atlas
  in the bottom half of the texture, where the rando's tunic texture alpha mask is solid.
- v17: tunic atlas regions are placed by scoring the randomizer's tunic texture (fully masked,
  smooth, mid-grey) when its asset zar is found (`RANDO_ASSETS` in build.py), so custom tunic
  colours get clean shading; falls back to bottom-half packing otherwise.
- v18 (current): **OoT3D Randomizer "Custom Tunic Colors" is not supported** (its tunic texture is
  painted for Link's UVs; v16/v17 attempts reverted, `RANDO_CUSTOM_TUNIC = False`). Kept: dummy
  materials absorbing the randomizer's fixed-offset writes, so other rando options (custom gauntlet
  colours, adult deku stick) are safe. Turn Custom Tunic Colors off when using a converted model.
- v19 (2026-10-07, adult Saria test): the tunic atlas could not hold Saria's 11 tunic textures
  (24576 texels vs 128x128). Tunic textures now get **their own materials** (baked with ENV = white,
  own wrap modes, no atlas) plus one extra TEV stage after stage 0: `previous * constant 0`
  (`TINT_STAGE`, appended combiner, mats size field +0x28 per added combiner). link_body.cmab keeps
  Link's texture-palette track on mat 1 (unused now) and adds a ConstColor (type 4) track on
  constant 0 of every tunic material, frames 0/1/2 = Kokiri/Goron/Zora (same mmad layout the
  randomizer's custom-tunic cmab uses). Every tested tunic combiner is exactly texture x ENV, so
  this matches the N64 result.
- v20: in Citra v19 loaded with correct textures but every tunic stayed green: the constant was on
  TEV stage 1. Now `TINT_STAGES` replace Link's stage 0: stage 0 = texture x constant 0 (the stage
  and slot the randomizer's working custom tunic animates), stage 1 = previous x vertex colour
  (scale 2). Ocarina (groups 40/41) is seated onto Link's 3D ocarina (mat 33, bone 20) by rigid ICP
  with a UV tie-break (`tools/fit.py`); Link's g41 ocarina is g40 turned 179 deg.
- v21 child Link (`zelda_link_child_new.zar`, `child/model/childlink_v2.cmb`): build.py picks an
  ADULT / CHILD profile from zobj header byte 0x500B. Child LUT from 0x50D0 (`zobj.CHILD_LUT_NAMES`,
  from hylian-modding/Z64-CustomPlayerModels child_map.ts); back matrices 0x5010 (hilt) and 0x5050
  (Deku shield). Child groups: 24 body, 26 head, 25 emptied, hands 0/1/3/4/7, bracelet 15, back
  9-14/21, held 2/5/6/8/16, seated 17-20 (ocarinas, slingshot, first-person arm); 22 slingshot
  string and 23 Deku stick stay Link's (placed by game code). Eye mat 14 / tex 16, mouth 15 / 17,
  bottle glass 3 / contents 4, templates 2 (opaque) / 13 (cutout). Child Link has no tunic swap in
  the game (no link_body.cmab; the randomizer only gives child one custom colour), so the child
  tunic is baked Kokiri green. Items are only re-seated onto Link's when the fit clearly beats the
  authored placement (`SEAT_*` in build.py).
- v22: in Citra the first-person slingshot string missed the lower fork tip and its other half
  floated in the sky (the game pins the string to Link's own tips). Slingshots are now fitted by
  handle + fork tips (`fit.fit_fork`: similarity with scale, tips weighted 4x): tip error 10-16
  units, was ~100-130.
- v23: **the game deforms the bow / slingshot string by writing straight into its vertex data at
  Link's original offsets.** The relayout had shifted those vertices (child string 25692 -> 17100,
  adult bow strings 58080 -> 54744), so the string never pulled and the game's writes landed in
  another mesh (a sliver floating in first person). `cmbwrite.write(pin_sepds=...)` now pads the
  preceding sepd with unreferenced vertices so pinned sepds keep their exact original starts
  (`PINNED_GROUPS`: adult 43/44, child 22/23).
  Known issue (user accepted, "mileage may vary"): with pinning the child first-person sliver
  shrinks when the string is pulled but is still there, and the string still does not fully follow
  the pull, so the game likely also writes other data the relayout moves (indices or another sepd).
- Voice (`tools/voice.py`): ML64 pack -> `romfs/sound/QueenSound.bcsar`. Voice sounds are CSEQ
  scripts (file 6) on BANK_VOICE (file 125) playing waves 250-375 of WARC_SE (file 161, DSP-ADPCM).
  `voicemap.py` interprets each script to find its waves; `dspadpcm.py` encodes; CWAR/CSAR
  rebuilders are byte-identical on no-op. Waves shared by several N64 ids go to the lowest id;
  sequential sounds (sneeze, sweat, yawn) get the clip in their first note only.

## Status

| Step | State |
|---|---|
| ZAR archive reader (`tools/zar.py`) | done |
| CMB skeleton reader + bind pose (`tools/cmbskel.py`) | done |
| zobj reader: skeleton, F3DEX2 display lists, 0x0D seam matrices, textures (`tools/zobj.py`) | done (textures decode; combiner not interpreted) |
| Place limbs on OoT3D bones + preview (`tools/pose.py`) | done, first test fits cleanly |
| CMB writer (`tools/cmbwrite.py`), reparsed + posed with real animations | done |
| Full build `tools/build.py` -> zar + LayeredFS folder | done, **not yet tested in-game** |
| Eyes / mouth / 3 tunics via rewritten `.cmab` texture palettes | done |
| Hands, fists, gauntlets, boots, first-person arms from the zobj | done |
| Swords, shields, bow, hookshot, etc. | v1 keeps OoT3D's own models |
| Child Link (`zelda_link_child_new.zar`), `*_ultra.zar` variants | todo |

## Key findings

- Adult Link: `romfs/actor/zelda_link_boy_new.zar` → `boy/model/link_v2.cmb` (25 bones),
  582 `.csab` animations, 582 `.faceb`, eye/mouth/body `.cmab` texture animations.
- OoT3D bones use the **same local-axis convention as N64 limbs** (child offset along +X), so
  N64 limb-local vertices can be placed directly into the matching OoT3D bone's bind frame.
  No retargeting of animations needed. Mapping is `LIMB_TO_BONE` in `tools/pose.py`.
- **Left/right differ:** N64 limbs 3-5 are Link's right leg; OoT3D bones 3-5 are his left (+X).
- The N64 skeleton is narrower at the hips and has a shorter neck. `pose.fit` keeps OoT3D bone
  rotations but moves joints to the N64 positions, so seams (82 waist/thigh triangles on the first test model)
  stay closed. The CMB writer must write these refitted translations. **Open risk:** if `.csab`
  animations carry translation tracks for these bones they will override the refit.
- **Tunic materials** (ZZENV): combiner reads ENVIRONMENT colour that the model never sets
  (`Tri.tunic`). Bake 3 textures with the OoT3D-style colours in `tools/tunics.py` (Kokiri #1AB31A, Goron #C30819,
  Zora #1144BB). OoT3D's `boy/misc/link_body.cmab` is a 3-key material animation, probably the
  tunic texture swap: point it at the 3 baked textures (to confirm when writing materials).
- Transparency comes from the combiner alpha (`Tri.alpha_from_texture`), not texture alpha:
  I8 textures copy intensity into alpha and would otherwise punch holes.
- N64 textures are bilinear-filtered; CMB materials must use linear min/mag filtering (keep
  original texture sizes, no upscaling) to keep the soft N64 look.
- Lit triangles carry vertex normals in the colour bytes; carry them into the CMB for smooth shading.
- OoT3D adds a clavicle bone per arm (13, 17) and bones 22–24 under the root with no N64 match.
- CMB bone rotation order: R = Rz·Ry·Rx (gives a symmetric A-pose).
- ML64 zobj: flex skeleton header at `0x5380`, 21 limbs, 18 with display lists; matrix
  `0x0D000000 + n*0x40` = n-th limb that has a display list.

## In-game findings (v1 test on hardware, 2026-10-06)

- v1 loaded without crashing. Bugs: face missing, tunic did not swap, item textures broken,
  floating dark pieces.
- Likely cause of the first three: the game copies `.cmab` texture-palette textures into the
  CMB's own texture slots (tunic = slot 1, eyes = 15, mouth = 16) and expects Link's exact
  count / size / format. v1 used new slots, RGBA8 and 12 tunic textures.
  v2: tunic textures packed into one atlas in slot 1 (128x128 ETC1), eyes 128x64 RGB565 in
  slot 15, mouth 32x32 RGB565 in slot 16; the three `.cmab` files keep Link's exact layout.
- Floating pieces: probably group 27 (mapped to the N64 first-person left hand, which includes
  bow geometry). v2 leaves groups 26-28/30/34 as Link's until their role is confirmed.
- `tools/pica.py` decodes/encodes 3DS textures (ETC1 encoder included);
  `tools/cmbtexview.py` renders a CMB from its 3DS texture data.

- **Confirmed in Citra (v3):** a mesh whose bone table has one entry is treated as SingleBone
  (bone-local positions) whatever its skinning field says. the first test model's face pieces (head bone only)
  were written in world space and landed at her feet; other one-bone pieces floated.
  `cmbwrite` now writes one-bone meshes as SingleBone (flags 0x0B, local positions) like Link's,
  and pads one-entry tables in smooth meshes with a zero-weight second bone.

- **Confirmed in Citra (v4):** tunic swap works with the atlas-in-slot-1 approach. Textures were
  smeared because new meshes stored UVs as float; the game reads texcoords as int16 (Link uses
  dtype 0x1402 + scale). v5 writes int16 UVs with scale = max|uv| / 32767.
- Every mesh is smooth-skinned (SINGLE_BONE_MODE off); double-sided N64 tris get a back face.

- **Root cause of scrambled UVs / torn Link items (v1-v5):** Link's vertex arrays and index
  buffer are contiguous in sepd order with no gaps (each array padded to 4 bytes only at its
  end, `n_idx` counts the padding). The game evidently derives per-sepd vertex ranges from that
  layout. `cmbwrite` now keeps Link's sepd indices, rebuilds all vertex/index data in sepd order
  (`_relayout`), and keeps Link's odd `mats` size field; a no-change rebuild is byte-identical.
  `tools/probe.py` re-encodes some of Link's own meshes as an in-game check.

## Build

```
python tools/build.py <player.zobj> <romfs>/actor/zelda_link_boy_new.zar out/build
```
Copy `zelda_link_boy_new.zar` to `luma/titles/0004000000033500/romfs/actor/` (USA).

- Link mesh groups (game toggles visibility per group id): 45 body, 46 head, 13/14 L hand/fist,
  20/21 R hand/fist, 24 L bottle hand, 4-6 / 17-19 gauntlets, 15/22 hover boots, 35/36 iron boots,
  26-28/30/34 first-person arms, other groups = items on back / in hands. See `GROUPS` in build.py.
- CSAB translation tracks on bones 5, 18-21 (and 2, 9) are patched to the refit skeleton.
- Rotation keys in CSAB are int16 binary angles (pi / 0x8000).
- Texture data: row 0 = top, sampled at v = 1, so v = 1 - t/h.

## Usage

```
python tools/zar.py <archive.zar> -x <outdir>
python tools/pose.py <player.zobj> <link_v2.cmb> out/<name>   # writes .obj + .png preview
```

- Equipment selection: `build.ITEMS` maps each equipment group to parts tagged with an equipment key
  (None = the model's hand) and Link's materials for that part; an item not taken keeps Link's
  meshes of those materials. Sources per item: the model, an equipment pack, or OoT3D.
- Equipment packs (`tools/equippak.py`): 'MODLOADER64' + type 0x69 + u32 count + DL table, then
  'EQUIPMANIFEST' JSON {"OOT": {"adult"|"child": {index: slot}}}, 'EQUIPMENTNAME', 'EQUIPMENTCAT'.
  Slots (sword0/1/2 = Kokiri / Master / Biggoron, shield0/1/2 = Deku / Hylian / Mirror, ocarina_0/1,
  bow, hookshot, ...) map onto the player LUT names. Pack triangles carry their own file (tri.src)
  for texture decoding.
- Back matrices: a zero-scale matrix at 0x5010 / 0x5050 is how a model hides its back items (adult
  Saria hides hilt and shield so they don't clip her cape); those parts are left out. Equipment-pack
  items still show on the back, placed with Z64Online's default matrices (`BACK_MTX_DEFAULT`).
  `hide_back` ({'shield', 'sword'}) drops those back items, the model's, a pack's or Link's
  (including OoT3D's Biggoron scabbard); held items are unaffected.
- Pinned string sepds with large equipment: if new meshes overflow the space before a pinned sepd,
  the slots before it take only meshes that fit (smallest first, exact per-array budgets), the rest
  get one-triangle unreferenced placeholders, and the remaining meshes go after the pin
  (shp chunk offsets are 16-bit, so whole Link sepds can't be kept there).
- Several models of one age: `pack.plan(files, main)` converts the main one and turns the others
  into equipment sources shaped like packs (`pack.as_equipment`, category 'model', dls = their LUT).
  They are offered for every item but never the default (packs first, then the main model).
- Child Biggoron Sword option: child group 16 (pedestal Master Sword, also the child Biggoron) gets
  the adult LONGSWORD_HILT + LONGSWORD_BLADE in the left hand; the adult grip holds it right side up
  (child MASTER_SWORD blade centre x = -549 in the hand frame, adult Biggoron +3236).
- Stub display lists (setup commands, no triangles; e.g. Aria's adult BOW) count as missing
  (`build.drawn_lut`), so the item falls back to another source or OoT3D's instead of vanishing.

## Animations (ML64 link_animetion .zdata -> OoT3D .csab)

- link_animetion: 573 animations (zeldaret/oot link_animetion.xml), 134 bytes per frame: root
  translation (3 s16), 21 limb rotations (3 s16 binary angles, R = Rz Ry Rx like OoT3D), face u16.
  ML64 banks are the vanilla file edited in place (same size, 0x265C30).
- OoT3D keeps N64 frame counts (mostly) but Grezzo re-keyed most animations (hermite int16 keys,
  edited poses), so N64 and OoT3D frames rarely match exactly.
- Retargeting: N64 limb 0 = OoT3D bone 1 (root motion; bone 0 is a static model root). For each
  OoT3D bone driven by an N64 limb, world_3d = world_n64 @ C with C a constant fitted robustly over
  the ~360 animations both games share (two halves of the data agree within 0.1-2.4 deg; the hat
  needs 27 deg, matching the -30 deg LIMB_TILT found by hand). Clavicles (13, 17), bow string
  (22-24) and the model root keep OoT3D's motion. Root: x/z follow OoT3D's fitted mapping (OoT3D
  scales sideways root sway to ~0.14), height uses the standing-frame ratio (~1.0).
- `gen_anim_tables.py` (developer only, needs a ROM) writes `anim_tables.py`: animation list,
  vanilla fingerprints (to find the animations a bank changes) and the fitted tables. No game data.
- Converted csabs: linear int16 rotation keys per frame (rot16 anods), root translation as linear
  float keys, other bones' anods copied raw; they go through the usual translation patch.
- Not yet: the per-frame face index (OoT3D uses separate .faceb files).
