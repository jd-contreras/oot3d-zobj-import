"""One-step OoT3D mod from ML64 player / voice mods.

    python tools/pack.py <inputs...> --romfs <ExtractedRomFS> -o <out.zip | out_dir>
                         [--layout citra|luma|romfs] [--region usa|eur|jpn] [--equipment all|none|key,key...]

Inputs: any mix of .pak, .zip, .zobj files and folders. The OoT adult / child zobjs, equipment
pack zobjs and the voice clips (sounds/<hex id>/...) are found inside them; MM zobjs are skipped.
--romfs is the user's own extracted OoT3D romfs (only the files the mod replaces are read from it).
--equipment picks the items to convert (default: from equipment packs first, else the model); the
rest stay OoT3D's: all | none | key,key... | key=source,... (source: model, oot3d or a pack file
name). Keys and sources: python tools/pack.py --list-equipment <inputs...>
"""
import sys, os, io, zipfile, argparse
import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
import build, voice, ml64pak, equippak

TITLE_IDS = {'usa': '0004000000033500', 'eur': '0004000000033600', 'jpn': '0004000000033400'}
GAME_FILES = {  # file name -> path inside the romfs
    'zelda_link_boy_new.zar': 'actor/zelda_link_boy_new.zar',
    'zelda_link_child_new.zar': 'actor/zelda_link_child_new.zar',
    'QueenSound.bcsar': 'sound/QueenSound.bcsar',
}


def expand(name, data):
    """{path: bytes} of one input file (archives are opened)."""
    low = name.lower()
    if low.endswith('.pak'):
        return {name + '/' + k: v for k, v in ml64pak.read(data).items()}
    if low.endswith('.zip'):
        out = {}
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            for info in z.infolist():
                if not info.is_dir():
                    out.update(expand(name + '/' + info.filename, z.read(info)))
        return out
    return {name: data}


def plan(files):
    """What a file set contains: ({'adult'|'child': (path, zobj bytes)}, {sound id: clips}, notes,
    equipment packs [(path, parsed, zobj bytes)])."""
    models, notes, paks = {}, [], []
    for path, data in sorted(files.items()):
        if not path.lower().endswith('.zobj'):
            continue
        if equippak.is_equipment(data):
            info = equippak.parse(data)
            if info['dls']:
                paks.append((path, info, data))
                ages = '/'.join(a for a in ('adult', 'child') if a in info['dls'])
                notes.append(f'equipment: {info["name"] or path} ({info["category"]}, {ages})')
            else:
                notes.append(f'skipped {path} (equipment for another game)')
            for u in info['unused']:
                notes.append(f'{info["name"] or path}: slot {u} not supported yet')
            continue
        age = build.model_age(data)
        if age is None:
            notes.append(f'skipped {path} (not an OoT ML64 player zobj, e.g. an MM model)')
        elif age in models:
            notes.append(f'skipped {path} (already using {models[age][0]} for {age})')
        else:
            models[age] = (path, data)
    return models, voice.find_clips(files), notes, paks


def equipment_options(models, paks=()):
    """{age: [(key, label, [source ids], default source)]} for the planned models; source ids are
    'model' or an equipment pack path ('oot3d' is always possible)."""
    return {age: build.equipment_options(data, paks) for age, (_, data) in models.items()}


def pak_names(paks):
    """{pack path: display name}."""
    return {path: info['name'] or os.path.basename(path) for path, info, _ in paks}


def make_mod(files, game, rate=22050, layout='citra', region='usa', decode=None, log=print, equipment=None,
             hide_back_shield=()):
    """files: {path: bytes} (inputs, already expanded). game: {GAME_FILES name: bytes} (only those
    needed). decode(bytes) -> mono int16 PCM at `rate` (default ffmpeg); audio files may also be
    given already decoded as numpy arrays. equipment: {age: choice} with choice as in
    build.convert (None, [keys] or {key: source}); missing ages use the defaults.
    hide_back_shield: ages whose shield is hidden on the back (still shown in hand).
    Returns ({output path: bytes}, report lines)."""
    models, clips, report, paks = plan(files)
    if not models and not clips:
        raise ValueError('no OoT player zobj or voice clips found in the inputs')
    tid = TITLE_IDS[region]
    base = {'citra': f'{tid}/romfs/', 'luma': f'luma/titles/{tid}/romfs/', 'romfs': 'romfs/'}[layout]
    out = {}
    build.log = log
    for age in ('adult', 'child'):
        if age not in models:
            continue
        path, data = models[age]
        need = build.target_zar(age)
        if need not in game:
            raise ValueError(f'{need} from your OoT3D romfs (actor/{need}) is needed for the {age} model')
        log(f'converting {age} model {path}')
        res = build.convert(data, game[need], (equipment or {}).get(age), paks, age in hide_back_shield)
        out[base + 'actor/' + res['name']] = res['zar']
        report.append(f'{age}: {path} -> romfs/actor/{res["name"]}')
    if clips:
        if 'QueenSound.bcsar' not in game:
            raise ValueError('QueenSound.bcsar from your OoT3D romfs (sound/QueenSound.bcsar) is needed for the voice')
        dec = decode or (lambda d: voice.decode_clip(d, rate))
        log(f'decoding {sum(len(v) for v in clips.values())} voice clips')
        pcm = {sid: [(n, d if isinstance(d, np.ndarray) else dec(d)) for n, d in cl] for sid, cl in clips.items()}
        bcsar, vrep = voice.build(pcm, game['QueenSound.bcsar'], rate, log=log)
        out[base + 'sound/QueenSound.bcsar'] = bcsar
        report += ['voice: ' + r for r in vrep]
    out[base.split('romfs/')[0] + 'zobj-import-report.txt'] = ('\n'.join(report) + '\n').encode()
    return out, report


def zip_bytes(out):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
        for path, data in sorted(out.items()):
            z.writestr(path, data)
    return buf.getvalue()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('inputs', nargs='+')
    ap.add_argument('--romfs', help='your extracted OoT3D romfs folder (required to convert)')
    ap.add_argument('-o', '--out', help='output .zip or folder (required to convert)')
    ap.add_argument('--layout', choices=['citra', 'luma', 'romfs'], default='citra')
    ap.add_argument('--region', choices=list(TITLE_IDS), default='usa')
    ap.add_argument('--rate', type=int, default=22050)
    ap.add_argument('--equipment', default='all', help='all, none, or comma-separated keys')
    ap.add_argument('--list-equipment', action='store_true', help='list the equipment keys and exit')
    ap.add_argument('--hide-back-shield', action='store_true',
                    help='no shield on the back (still shown in hand), e.g. for long hair or a cape')
    a = ap.parse_args()

    files = {}
    for inp in a.inputs:
        if os.path.isdir(inp):
            for k, v in voice.read_files(inp).items():
                files.update(expand(os.path.basename(inp.rstrip('/\\')) + '/' + k, v))
        else:
            files.update(expand(os.path.basename(inp), open(inp, 'rb').read()))
    models, clips, _, paks = plan(files)
    if a.list_equipment:
        names = pak_names(paks)
        for age, opts in equipment_options(models, paks).items():
            print(age + ':')
            for key, label, srcs, default in opts:
                alt = ', '.join(('*' if s == default else '') + names.get(s, s) for s in srcs) or 'OoT3D only'
                print(f'  {key:16} {label:38} {alt}')
        print('(* = default; every item can also be "oot3d")')
        return
    if a.equipment == 'all':
        eq = None
    elif a.equipment == 'none':
        eq = []
    elif '=' in a.equipment:  # key=source pairs; a source may be a pack's file or display name
        byname = {n: p for p, n in pak_names(paks).items()}
        byname.update({os.path.basename(p): p for p, _, _ in paks})
        eq = {}
        for item in a.equipment.split(','):
            k, src = item.split('=', 1)
            eq[k.strip()] = byname.get(src.strip(), src.strip())
    else:
        eq = a.equipment.split(',')
    equipment = {age: eq for age in models}
    if not a.romfs or not a.out:
        ap.error('--romfs and -o are required to convert')
    need = [build.target_zar(age) for age in models] + (['QueenSound.bcsar'] if clips else [])
    game = {n: open(os.path.join(a.romfs, GAME_FILES[n]), 'rb').read() for n in need}

    out, report = make_mod(files, game, a.rate, a.layout, a.region, equipment=equipment,
                           hide_back_shield=set(models) if a.hide_back_shield else ())
    if a.out.lower().endswith('.zip'):
        open(a.out, 'wb').write(zip_bytes(out))
    else:
        for path, data in out.items():
            p = os.path.join(a.out, path)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            open(p, 'wb').write(data)
    print('\n'.join(report))
    print('wrote', a.out)


if __name__ == '__main__':
    main()
