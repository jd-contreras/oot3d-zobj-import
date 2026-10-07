# OoT3D Model Importer

Convert ModLoader64 (zzplayas / Z64Online) **Ocarina of Time player models** and **voice packs**
into an **Ocarina of Time 3D** mod for Citra or a modded 3DS.

**Use it in your browser: https://jd-contreras.github.io/oot3d-zobj-import/**

Everything runs locally in your browser (Python via Pyodide). Your files are never uploaded, and
no game files are included: you supply them from your own copy of OoT3D.

## What it converts

| | Adult | Child |
|---|---|---|
| Body, face (blinking, talking) | yes | yes |
| Tunic colours | Kokiri / Goron / Zora | Kokiri green (the game has no child tunic swap) |
| Equipment (swords, shields, bow / slingshot, hookshot, ocarina, bottle, gauntlets, boots, ...) | from the model, equipment packs or OoT3D, per item | same |
| First-person arms | yes | yes |
| Voice packs (ML64 `sounds/<id>/` clips) | yes | yes |
| Custom animations (ML64 `link_animetion.zdata`) | yes (changed ones only) | yes |

**Equipment packs** (ModLoader64 / Z64Online equipment `.pak` files) work too: add them next to
a model and pick, per item, whether it comes from the model, a pack, or OoT3D. Anything you don't
take from the model or a pack stays OoT3D's own, which is handy for models that still carry
ModLoader64's default N64 items.

**Equipment from another model:** add two or more models of the same age (for example two
adult `.pak` files). Pick the main model, and the others can lend any of their items, just like
ModLoader64 lets you mix models and equipment.

**Biggoron Sword on the back:** player models have no Biggoron Sword for the back, so by default
the model's Master Sword sheath is used, with the Biggoron hilt in it when sheathed. Tick **Use
OoT3D Biggoron scabbard** to keep OoT3D's big scabbard instead.

**Import child Biggoron Sword:** like ModLoader64's option, the adult model's Biggoron Sword (held
right side up) replaces child Link's pedestal Master Sword, which the game also draws for a child
holding the Biggoron Sword.

**Custom animations:** if a pack includes a ModLoader64 animation bank (`link_animetion.zdata`),
the animations it changes from the original game are converted onto OoT3D's skeleton and replace
OoT3D's versions; every other animation stays OoT3D's own. No ROM is needed.

**Hide shield on back / Hide sword on back:** two options (tick either or both) for long hair or
a cape the items would clip into. They're left off the back but still show when held. Back items a
model hides itself (ModLoader64's zero-scale back matrix) stay hidden; equipment-pack items show on
the back unless you tick these.

**Mileage may vary:** every model is built a little differently. Held items may sit slightly
differently than on the N64, and the first-person slingshot can show a small stray sliver.

## How to use

1. Open the site and drop in your `.pak` / `.zip` / `.zobj` files (adult, child, equipment packs and/or a voice pack).
2. Pick the listed files from your own extracted OoT3D romfs (`actor/zelda_link_boy_new.zar`,
   `actor/zelda_link_child_new.zar`, `sound/QueenSound.bcsar`), or pick the whole romfs folder.
3. Choose Citra or 3DS (Luma) and your game region, then **Convert** and download the zip.
   - **Citra:** extract into Citra's `load/mods` folder.
   - **3DS:** extract to the root of the SD card and enable game patching in the Luma3DS config.

If you use the OoT3D Randomizer, turn off **Custom Tunic Colors**; it isn't compatible with
imported models. Everything else in the randomizer works.

## Command line

The same converter runs with Python 3, numpy and Pillow (ffmpeg for voice packs):

```bash
python tools/pack.py Adult_Model.pak Child_Model.pak Voice.pak --romfs path/to/ExtractedRomFS -o mod.zip
python tools/pack.py --list-equipment Adult_Model.pak
python tools/pack.py Adult_Model.pak --romfs path/to/ExtractedRomFS -o mod.zip --equipment none
python tools/pack.py Child_Model.pak Equipment.pak --romfs path/to/ExtractedRomFS -o mod.zip --equipment "kokiri_sword=MM3D Razor Sword"
python tools/pack.py Model_A.pak Model_B.pak --main "Model A" --equipment "master_sword=Model B" --romfs path/to/ExtractedRomFS -o mod.zip
```

Options: `--layout citra|luma|romfs`, `--region usa|eur|jpn`,
`--equipment all|none|key,key...|key=source,...` (source: `model`, `oot3d`, an equipment pack's name
or another model's name), `--main NAME` (with several models of one age), `--child-biggoron`, `--oot3d-biggoron-scabbard`, `--no-animations`,
`--hide-back shield`, `--hide-back sword` or `--hide-back shield,sword`.

## Credits

- ModLoader64 / Z64Online player model format and manifests:
  [hylian-modding/Z64-CustomPlayerModels](https://github.com/hylian-modding/Z64-CustomPlayerModels)
- OoT3D model, animation and archive format references: [noclip.website](https://github.com/magcius/noclip.website)
- OoT3D behaviour and randomizer compatibility: [gamestabled/OoT3D_Randomizer](https://github.com/gamestabled/OoT3D_Randomizer)
- N64 animation layout (link_animetion): [zeldaret/oot](https://github.com/zeldaret/oot)
- Python in the browser: [Pyodide](https://pyodide.org)

Format notes and the history of how each piece was worked out are in [NOTES.md](NOTES.md).

Not affiliated with Nintendo. Ocarina of Time is a trademark of Nintendo.
