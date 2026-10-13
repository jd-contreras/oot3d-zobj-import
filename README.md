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
OoT3D Biggoron scabbard** to use OoT3D's big scabbard instead (your Biggoron hilt still shows in it).

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
   Use the original files, not ones from a mods folder (those are already converted).
3. Choose Citra or 3DS (Luma) and your game region, then **Convert** and download the zip.
   - **Citra:** extract into Citra's `load/mods` folder.
   - **3DS:** extract into your Luma `luma/titles` folder on the SD card, and enable game patching in the Luma3DS config.
     Or keep the zip as it is and use the [OoT Model Manager](#oot-model-manager-3ds-app) app on the console.

Tunic colours can be picked per model in step 1 (Kokiri / Goron / Zora for an adult model, one
colour for a child model).

If you use the OoT3D Randomizer, turn off **Custom Tunic Colors**; it isn't compatible with
imported models. Everything else in the randomizer works.

### Extra Buttons for the randomizer

Add your seed's `code.ips` in step 1 or 2, with or without a model, to add Extra Buttons to it:
ZL and ZR use items I and II, and the D-pad holds four more items (hover an item on the Items
page and press the button). The zip then contains the patched `code.ips`; the seed's
`exheader.bin` does not change. It works with USA and Europe seeds (Citra or console) made by randomizer `v4.0.2` or nightly `6bd4b80`,
and turns the seed's Custom Tunic Colors off when a model is imported with it.

The Extra Buttons code is open for anyone to use and modify, for example to add it to official
randomizer builds or to other projects: [Extra Button Functionality for OoT3D](https://github.com/jd-contreras/Extra-Button-Functionality-for-OoT3D).

## OoT Model Manager (3DS app)

For console players: a homebrew app that switches between your converted characters and patches
new randomizer seeds on the 3DS itself, so the SD card doesn't have to go back to a PC every time.

**Download: [OoTModelManager.3dsx](https://github.com/jd-contreras/oot3d-zobj-import/releases/latest/download/OoTModelManager.3dsx)**

It only loads models and voice packs that are **already converted** with the importer above: the
conversion itself is not done on the console. What it does on its own is add Extra Buttons to a
randomizer seed, on the fly, each time you make a new one.

### Setting it up

1. Copy `OoTModelManager.3dsx` into the `3ds` folder on your SD card.
2. Run it once from the Homebrew Launcher. It makes an `OoTModelManager` folder at the top of the
   SD card (next to the `3ds` folder, not inside it), with a `Voice` folder and a short how-to note.
3. Put your converted characters in `OoTModelManager`, one per character:
   - the **zip** the importer gives you, as it is, or
   - a **folder** holding the converted files: an adult model, a child model and/or a voice pack.

   File names don't matter. The folder or zip name is what the app shows, and the app works out
   from each file whether it is an adult model, a child model or a voice pack.
4. Voice packs that belong to no character go in `OoTModelManager/Voice`.

### Using it

Nothing on the card changes until you choose **Apply patch**. Everything else only records what
you want, and the top screen shows what is selected and what is not applied yet.

| Menu | What it does |
| --- | --- |
| Choose models and voice | Pick a whole character (Sets), or mix an adult model, a child model and a voice from the Adult, Child and Voice tabs |
| Press A to randomize | Picks for you, as set under Randomize settings. You see the pick before applying it |
| Randomize settings | What the randomize button picks: Set (one whole character), Adult, Child, Voice, or All; and Secret random, which hides the picks |
| Apply extra buttons | On: Apply patch adds ZL / ZR and D-pad item buttons to your randomizer seed. Off: it removes them. Shows APPLIED once the seed has them |
| Game region | Which game's folder the files go to. Auto uses the OoT3D folders found in `luma/titles` |
| Apply patch | Writes your selection to the game. Use it after every new seed |

Good to know:

- **After every new seed, run the app and choose Apply patch.** The randomizer replaces
  `code.ips` and clears the game's sound folder each time it makes a seed, so the buttons and
  your voice pack have to be put back. Your models stay.
- A voice pack is put *into* the sound file that is already there, so the randomizer's shuffled
  music is kept.
- Apply a voice to a character that has none and the app remembers it (a `uses.txt` file in that
  character's folder), so the character keeps that voice from then on, also when picked at
  random. Applying a different voice replaces it.
- A seed made with the randomizer's Custom Tunic Colors on has that setting switched off while a
  custom model is in use; with it on, every tunic would show the model's default colour.
- Extra Buttons works with USA and Europe seeds made by randomizer `v4.0.2` or nightly `6bd4b80`.
  A seed from another version is left alone and the app says so; models and voices still work.
- The library is only read. Your zips and folders are never changed, apart from that `uses.txt`.

The source is in [`app/`](app); `python gen_builds.py` then `make` builds it (devkitARM with
libctru and citro2d).

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
`--hide-back shield`, `--hide-back sword` or `--hide-back shield,sword`,
`--tunics kokiri=RRGGBB,goron=RRGGBB,zora=RRGGBB,child=RRGGBB`, `--seed code.ips` (adds Extra
Buttons to a randomizer seed; `python tools/seedmerge.py code.ips out.ips` does only that).

## Credits

- ModLoader64 / Z64Online player model format and manifests:
  [hylian-modding/Z64-CustomPlayerModels](https://github.com/hylian-modding/Z64-CustomPlayerModels)
- OoT3D model, animation and archive format references: [noclip.website](https://github.com/magcius/noclip.website)
- OoT3D behaviour and randomizer compatibility: [gamestabled/OoT3D_Randomizer](https://github.com/gamestabled/OoT3D_Randomizer)
- N64 animation layout (link_animetion): [zeldaret/oot](https://github.com/zeldaret/oot)
- Extra Buttons: [Extra Button Functionality for OoT3D](https://github.com/jd-contreras/Extra-Button-Functionality-for-OoT3D), built on the OoT3D Randomizer, with
  item-assignment hooks adapted from [Ocarina Reframed](https://github.com/OTPR26/OOT3DHud) by OTPR26
- Python in the browser: [Pyodide](https://pyodide.org)
- 3DS app: built with [devkitPro](https://devkitpro.org) (libctru, citro2d)

Format notes and the history of how each piece was worked out are in [NOTES.md](NOTES.md).

Not affiliated with Nintendo. Ocarina of Time is a trademark of Nintendo.
