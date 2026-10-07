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
import build, voice, ml64pak, equippak, zobj, animconv

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


def model_name(path):
    """Display name of a player model: its .zobj file name (packs often hold several models)."""
    last = path.replace('\\', '/').split('/')[-1]
    return os.path.splitext(last)[0].replace('_', ' ')


def as_equipment(path, data, age):
    """A second player model used as an equipment source: its display lists, shaped like a pack."""
    info = {'name': model_name(path) + ' (model)', 'category': 'model', 'unused': [],
            'dls': {age: build.drawn_lut(zobj.read(data))}}
    return path, info, data


def plan(files, main=None):
    """What a file set contains: ({'adult'|'child': (path, zobj bytes)} main models,
    {sound id: clips}, notes, equipment sources [(path, parsed, zobj bytes)],
    {age: [candidate model paths]}). Several models of one age: `main` = {age: path} picks the one
    converted (default the first); the others become equipment sources, like equipment packs."""
    cands, notes, paks = {}, [], []
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
        else:
            cands.setdefault(age, []).append((path, data))
    models = {}
    for age, lst in cands.items():
        want = (main or {}).get(age)
        pick = next((c for c in lst if c[0] == want), lst[0])
        models[age] = pick
        for path, data in lst:
            if path != pick[0]:
                paks.append(as_equipment(path, data, age))
                notes.append(f'{age} equipment source: {model_name(path)} (model)')
    return models, voice.find_clips(files), notes, paks, {age: [p for p, _ in lst] for age, lst in cands.items()}


def equipment_options(models, paks=()):
    """{age: [(key, label, [source ids], default source)]} for the planned models; source ids are
    'model' or an equipment pack path ('oot3d' is always possible)."""
    return {age: build.equipment_options(data, paks) for age, (_, data) in models.items()}


def pak_names(paks):
    """{pack path: display name}."""
    return {path: info['name'] or os.path.basename(path) for path, info, _ in paks}


def anim_bank(files):
    """(path, bytes, [changed N64 animation names]) of the first ML64 animation bank (.zdata), or None."""
    for path, data in sorted(files.items()):
        if path.lower().endswith('.zdata') and animconv.is_anim_bank(data):
            return path, data, animconv.changed(data)
    return None


def biggoron_source(models, paks, choice=None):
    """(bytes, {part: address}, name) of the adult Biggoron Sword for the child option: the adult
    choice's source if it is a pack / another model, else the adult model, else any adult source."""
    parts = build.BIGGORON_PARTS

    def from_pak(pid):
        for path, info, data in paks:
            dls = info['dls'].get('adult', {})
            if path == pid and all(p in dls for p in parts):
                return data, {p: dls[p] for p in parts}, info['name'] or model_name(path)

    src = choice.get('biggoron') if isinstance(choice, dict) else None
    if src and src not in ('model', 'oot3d'):
        hit = from_pak(src)
        if hit:
            return hit
    if src is None:  # same default as the adult's own Biggoron: equipment packs first
        for path, info, _ in paks:
            if info.get('category') != 'model':
                hit = from_pak(path)
                if hit:
                    return hit
    if 'adult' in models:
        path, data = models['adult']
        lut = build.drawn_lut(zobj.read(data))
        if all(p in lut for p in parts):
            return data, {p: lut[p] for p in parts}, model_name(path)
    for path, _, _ in paks:
        hit = from_pak(path)
        if hit:
            return hit
    return None


def make_mod(files, game, rate=22050, layout='citra', region='usa', decode=None, log=print, equipment=None,
             hide_back=None, main=None, child_biggoron=False, animations=True, oot3d_scabbard=None):
    """files: {path: bytes} (inputs, already expanded). game: {GAME_FILES name: bytes} (only those
    needed). decode(bytes) -> mono int16 PCM at `rate` (default ffmpeg); audio files may also be
    given already decoded as numpy arrays. equipment: {age: choice} with choice as in
    build.convert (None, [keys] or {key: source}); missing ages use the defaults.
    hide_back: {age: {'shield', 'sword'}} back items to leave off (still shown in hand).
    main: {age: model path} when several models of an age are given (others lend equipment).
    animations: use an included ML64 animation bank's changed animations (link_animetion .zdata).
    oot3d_scabbard: ages (adult) keeping OoT3D's Biggoron scabbard instead of the model's sheath.
    child_biggoron: the child model holds the adult Biggoron Sword (from the adult model or an
    adult equipment source) in place of the pedestal Master Sword, as ModLoader64's option does.
    Returns ({output path: bytes}, report lines)."""
    models, clips, report, paks, _ = plan(files, main)
    if not models and not clips:
        raise ValueError('no OoT player zobj or voice clips found in the inputs')
    tid = TITLE_IDS[region]
    base = {'citra': f'{tid}/romfs/', 'luma': f'luma/titles/{tid}/romfs/', 'romfs': 'romfs/'}[layout]
    out = {}
    build.log = log
    bank = anim_bank(files) if animations else None
    if bank:
        report.append(f'animations: {len(bank[2])} custom from {bank[0]}: ' + ', '.join(bank[2]))
    for age in ('adult', 'child'):
        if age not in models:
            continue
        path, data = models[age]
        need = build.target_zar(age)
        if need not in game:
            raise ValueError(f'{need} from your OoT3D romfs (actor/{need}) is needed for the {age} model')
        log(f'converting {age} model {path}')
        bgs = None
        if age == 'child' and child_biggoron:
            bgs = biggoron_source(models, paks, (equipment or {}).get('adult'))
            if bgs is None:
                log('child Biggoron Sword: no adult model or adult Biggoron Sword in the inputs, skipped')
                report.append('child Biggoron Sword skipped (needs an adult model or adult Biggoron Sword)')
        res = build.convert(data, game[need], (equipment or {}).get(age), paks, (hide_back or {}).get(age, ()), bgs,
                            bank[1] if bank and bank[2] else None, age in (oot3d_scabbard or ()))
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
    ap.add_argument('--main', action='append', default=[], metavar='NAME',
                    help='with several models of one age: the one to convert (file or model name); '
                         'the others lend their equipment')
    ap.add_argument('--oot3d-biggoron-scabbard', action='store_true',
                    help="keep OoT3D's Biggoron scabbard on the back (default: the model's sheath and Biggoron hilt)")
    ap.add_argument('--no-animations', action='store_true',
                    help="ignore an included animation bank (link_animetion .zdata)")
    ap.add_argument('--child-biggoron', action='store_true',
                    help="the child model holds the adult model's Biggoron Sword (replaces the pedestal Master Sword)")
    ap.add_argument('--hide-back', default='', metavar='shield,sword',
                    help='leave these off the back (still shown in hand), e.g. for long hair or a cape')
    a = ap.parse_args()

    files = {}
    for inp in a.inputs:
        if os.path.isdir(inp):
            for k, v in voice.read_files(inp).items():
                files.update(expand(os.path.basename(inp.rstrip('/\\')) + '/' + k, v))
        else:
            files.update(expand(os.path.basename(inp), open(inp, 'rb').read()))
    _, _, _, _, cands = plan(files)
    main = {}
    for want in a.main:
        for age, paths in cands.items():
            for p in paths:
                if want.lower() in (p.lower(), model_name(p).lower(), os.path.basename(p).lower()):
                    main[age] = p
    models, clips, _, paks, _ = plan(files, main)
    for age in models:
        print(f'{age} model: {model_name(models[age][0])} ({models[age][0]})')
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
        byname = {n.lower(): p for p, n in pak_names(paks).items()}
        byname.update({os.path.basename(p).lower(): p for p, _, _ in paks})
        byname.update({model_name(p).lower(): p for p, info, _ in paks if info['category'] == 'model'})
        eq = {}
        for item in a.equipment.split(','):
            k, src = item.split('=', 1)
            eq[k.strip()] = byname.get(src.strip().lower(), src.strip())
    else:
        eq = a.equipment.split(',')
    equipment = {age: eq for age in models}
    if not a.romfs or not a.out:
        ap.error('--romfs and -o are required to convert')
    need = [build.target_zar(age) for age in models] + (['QueenSound.bcsar'] if clips else [])
    game = {n: open(os.path.join(a.romfs, GAME_FILES[n]), 'rb').read() for n in need}

    out, report = make_mod(files, game, a.rate, a.layout, a.region, equipment=equipment,
                           hide_back={age: {x for x in a.hide_back.split(',') if x} for age in models},
                           main=main, child_biggoron=a.child_biggoron, animations=not a.no_animations,
                           oot3d_scabbard={'adult'} if a.oot3d_biggoron_scabbard else ())
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
