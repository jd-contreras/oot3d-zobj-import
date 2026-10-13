"""Put the Extra Buttons patch under an OoT3D Randomizer seed.

A seed's code.ips is the randomizer's base patch followed by that seed's own records (item
placements, settings, custom text, ...). The base patch is replaced by ours (the randomizer's
code plus the extra item buttons, web/extra-buttons-<build>-<region>.ips); the seed's records are
kept, moved to where the same data sits in our build (addresses in the .json next to it, written
by tools/gen_extra_buttons.py). Records at game addresses are copied as they are.
A seed only fits the randomizer build that made it, so there is one patch per supported build
and game region; the same code.ips serves Citra and a console.
"""
import os, json, struct

ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'web')
BUILDS = ('nightly-6bd4b80', 'v4.0.2')  # randomizer builds the Extra Buttons patch exists for
REGIONS = ('usa', 'eur')  # index = the randomizer's region setting
BASE_IPS, BASE_INFO = 'extra-buttons-%s-%s.ips', 'extra-buttons-%s-%s.json'
TUNIC_FLAGS = 5  # customTunicColors and the four rainbow tunic settings that follow it
REGION_NAMES = {'usa': 'USA', 'eur': 'Europe', 'jpn': 'Japan'}

# The randomizer's data symbols a seed can write, in the order source/patch.cpp writes them.
ORDER = ['rItemOverrides', 'rEntranceOverrides', 'gSettingsContext', 'gSpoilerData', 'gSpoilerDataLocs',
         'rScrubRandomItemPrices', 'rShopsanityPrices', 'rDungeonRewardOverrides', 'rCustomMessages',
         'ptrCustomMessageEntries', 'numCustomMessageEntries', 'rBGMOverrides', 'rSfxData',
         'rDungeonInfoData', 'rDungeonImportance', 'rGsLocOverrides', 'rEnemyOverrides']  # InfoData: v4.0.2's name
# Symbols whose record always has the symbol's full size.
WHOLE = {'gSettingsContext', 'gSpoilerData', 'rScrubRandomItemPrices', 'rShopsanityPrices',
         'rDungeonRewardOverrides', 'ptrCustomMessageEntries', 'numCustomMessageEntries', 'rSfxData'}
# Symbols every seed writes.
ALWAYS = {'rItemOverrides', 'gSettingsContext', 'gSpoilerData', 'rCustomMessages', 'ptrCustomMessageEntries',
          'numCustomMessageEntries', 'rSfxData'}


def assign(recs, sym, start):
    """Which symbol each seed record belongs to: [(name or None, offset into the symbol)], or None.
    The official builds come from another compiler, so the seed's addresses say nothing about ours;
    the records are matched by the order the randomizer writes them, their sizes, and the symbols
    every seed has. A record just above the previous one, inside that symbol, continues it."""
    def walk(i, cursor, last, seen):
        if i == len(recs):
            return [] if ALWAYS & set(sym) <= seen else None
        off, data = recs[i]
        if off < start:  # a game address, kept as it is
            rest = walk(i + 1, cursor, last, seen)
            return None if rest is None else [(None, 0)] + rest
        if last and off > last[1] and (not sym[last[0]][1] or off - last[1] < sym[last[0]][1]):
            rest = walk(i + 1, cursor, last, seen)
            return None if rest is None else [(last[0], off - last[1])] + rest
        for c in range(cursor, len(ORDER)):
            name = ORDER[c]
            if name not in sym:  # data this randomizer build doesn't have
                continue
            size = sym[name][1]
            if name in WHOLE and len(data) != size or size and len(data) > size:
                continue
            rest = walk(i + 1, c + 1, (name, off), seen | {name})
            if rest is not None:
                return [(name, 0)] + rest
        return None
    return walk(0, 0, None, frozenset())


def records(ips):
    """[(file offset, bytes)] of an IPS patch."""
    if ips[:5] != b'PATCH' or ips[-3:] != b'EOF':
        raise ValueError('the randomizer file is not an IPS patch (expected the seed\'s code.ips)')
    pos, out, end = 5, [], len(ips) - 3
    while pos < end:
        off = int.from_bytes(ips[pos:pos + 3], 'big')
        size = int.from_bytes(ips[pos + 3:pos + 5], 'big')
        pos += 5
        if size == 0:
            out.append((off, ips[pos + 2:pos + 3] * int.from_bytes(ips[pos:pos + 2], 'big')))
            pos += 3
        else:
            out.append((off, ips[pos:pos + size]))
            pos += size
    if pos != end:
        raise ValueError('the randomizer code.ips is cut short or damaged')
    return out


def game_bytes(recs, limit):
    """Addresses of the game's own code and data (below the randomizer's) that a patch changes."""
    out = set()
    for off, data in recs:
        if off < limit:
            out.update(range(off, min(off + len(data), limit)))
    return out


def load_base(build, region):
    """(our base patch, its address table) for a randomizer build and region, from web/."""
    with open(os.path.join(ASSETS, BASE_IPS % (build, region)), 'rb') as f:
        base = f.read()
    with open(os.path.join(ASSETS, BASE_INFO % (build, region)), encoding='utf-8') as f:
        return base, json.load(f)


def merge(seed, drop_custom_tunics=False, bases=None):
    """seed: a randomizer seed's code.ips (bytes). Returns (merged code.ips, report lines, region).
    The seed's randomizer build and region are recognised from the game addresses its base
    patch changes.
    drop_custom_tunics: turn the seed's Custom Tunic Colors off (imported models can't use it).
    bases: {(build, region): (base patch, address table)} (default: everything in web/)."""
    bases = bases or {(b, r): load_base(b, r) for b in BUILDS for r in REGIONS}
    seed_recs = records(seed)
    # The base patch is written in ascending order; the seed's records start where that breaks.
    split = next((i for i in range(1, len(seed_recs)) if seed_recs[i][0] < seed_recs[i - 1][0]), len(seed_recs))
    for (build, region), (base, info) in bases.items():
        start = info['randoStart'] - 0x100000  # file offset where the randomizer's own code begins
        theirs, ours = game_bytes(seed_recs[:split], start), game_bytes(records(base), start)
        if theirs == ours:
            raise ValueError('this code.ips already has the Extra Buttons patch; add the code.ips the randomizer made')
        if theirs <= ours and len(ours - theirs) == info['addedBytes']:
            break
    else:
        raise ValueError('this code.ips is not from a supported randomizer build. Extra Buttons works with '
                         'USA and Europe seeds made by: '
                         + ', '.join(sorted({i['source'] for _, i in bases.values()})))

    sym = {k: tuple(v) for k, v in info['symbols'].items()}
    extras = seed_recs[split:]
    names = assign(extras, sym, start)
    if names is None:
        raise ValueError('this code.ips does not look like a seed made by ' + info['source'])
    out, report, messages = bytearray(base[:-3]), [], None
    for (off, data), (name, into) in zip(extras, names):
        old = off + 0x100000
        new = old if name is None else sym[name][0] + into
        if name == 'rCustomMessages' and not into:
            messages = (old, new)
        elif name == 'ptrCustomMessageEntries':
            data = struct.pack('<I', struct.unpack('<I', data)[0] - messages[0] + messages[1])
        elif name == 'gSettingsContext':
            fields = info['settings']
            if data[fields['region']] != REGIONS.index(region):
                raise ValueError('this seed\'s settings and its code are for different game regions')
            at = fields['customTunicColors']
            if drop_custom_tunics and any(data[at:at + TUNIC_FLAGS]):
                data = data[:at] + bytes(TUNIC_FLAGS) + data[at + TUNIC_FLAGS:]
                report.append('randomizer Custom Tunic Colors turned off (imported models use the tunic '
                              'colours picked here)')
        for i in range(0, len(data), 0xFFFF):
            chunk = data[i:i + 0xFFFF]
            out += (new - 0x100000 + i).to_bytes(3, 'big') + len(chunk).to_bytes(2, 'big') + chunk
    out += b'EOF'
    report.insert(0, f'randomizer seed ({info["source"]}, {REGION_NAMES[region]}): Extra Buttons added '
                     '(ZL / ZR = items I / II, D-pad = four more item slots)')
    return bytes(out), report, region


if __name__ == '__main__':
    import sys
    merged, lines, seed_region = merge(open(sys.argv[1], 'rb').read())
    open(sys.argv[2], 'wb').write(merged)
    print('\n'.join(lines))
