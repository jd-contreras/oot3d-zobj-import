"""Regenerate web/extra-buttons-<build>-<region>.ips and .json from a build of the Extra Buttons patch.

    python tools/gen_extra_buttons.py <build> usa|eur <our basecode.ips> <our .elf> <stock basecode.ips>

<build> is one of seedmerge.BUILDS: the randomizer version the patch was built on.

The stock base patch (same randomizer commit, without the extra buttons) is only used to count
the game bytes our patch changes on top of the randomizer's; tools/seedmerge.py uses that count
to recognise seeds from the matching randomizer build. Needs devkitARM (nm, gdb).
"""
import sys, os, json, subprocess

sys.path.insert(0, os.path.dirname(__file__))
import seedmerge

SOURCES = {'nightly-6bd4b80': 'OoT3D Randomizer nightly 6bd4b80', 'v4.0.2': 'OoT3D Randomizer v4.0.2'}
RANDO_START = 0x5C7000  # first address after the game's own code and data
BIN = os.path.join(os.environ.get('DEVKITARM', ''), 'bin')
if not os.path.isdir(BIN):  # e.g. an msys-style path in the environment
    BIN = 'C:/devkitPro/devkitARM/bin'
FIELDS = ['region', 'customTunicColors']


def main(build, region, base_ips, elf, stock_ips):
    assert build in seedmerge.BUILDS and region in seedmerge.REGIONS, (build, region)
    base = open(base_ips, 'rb').read()
    sym = {}
    for line in subprocess.run([os.path.join(BIN, 'arm-none-eabi-nm'), '-S', elf],
                               capture_output=True, text=True, check=True).stdout.splitlines():
        p = line.split()
        if p[-1] in seedmerge.ORDER:
            sym[p[-1]] = [int(p[0], 16), int(p[1], 16) if len(p) == 4 else 0]
    print('not in this build:', [n for n in seedmerge.ORDER if n not in sym])
    cmds = ['print sizeof(SettingsContext)'] + ['print (int)&((SettingsContext*)0)->' + f for f in FIELDS]
    gdb = subprocess.run([os.path.join(BIN, 'arm-none-eabi-gdb'), '-batch'] + [a for c in cmds for a in ('-ex', c)] + [elf],
                         capture_output=True, text=True, check=True).stdout
    vals = [int(line.split('=')[1]) for line in gdb.splitlines() if line.startswith('$')]
    assert vals[0] == sym['gSettingsContext'][1], vals
    limit = RANDO_START - 0x100000
    ours = seedmerge.game_bytes(seedmerge.records(base), limit)
    stock = seedmerge.game_bytes(seedmerge.records(open(stock_ips, 'rb').read()), limit)
    assert stock <= ours
    info = {'source': SOURCES[build], 'randoStart': RANDO_START, 'addedBytes': len(ours - stock), 'symbols': sym,
            'settings': dict(zip(FIELDS, vals[1:]))}
    open(os.path.join(seedmerge.ASSETS, seedmerge.BASE_IPS % (build, region)), 'wb').write(base)
    with open(os.path.join(seedmerge.ASSETS, seedmerge.BASE_INFO % (build, region)), 'w', encoding='utf-8', newline='\n') as f:
        json.dump(info, f, indent=1)
        f.write('\n')
    print('wrote', seedmerge.BASE_IPS % (build, region), len(base), 'bytes;', info['addedBytes'], 'game bytes added;', info['settings'])


if __name__ == '__main__':
    main(*sys.argv[1:6])
