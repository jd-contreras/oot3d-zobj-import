"""ModLoader64 / Z64Online equipment zobjs (the .zobj files inside an equipment .pak).

Layout: 'MODLOADER64' + type 0x69 + u32 count, then `count` 8-byte display-list entries
(DE010000 06xxxxxx), then 'EQUIPMANIFEST' + JSON {"OOT": {"adult": {index: slot}, "child": {...}},
"MM": {...}} + 0xFF, then 'EQUIPMENTNAME' and 'EQUIPMENTCAT' strings (16-byte tags).
Slot names map onto the player-model LUT names the converter uses (zobj.LUT_NAMES / CHILD_LUT_NAMES).
"""
import json, struct

HEADER = b'MODLOADER64'
TYPE_EQUIPMENT = 0x69

# Z64Online equipment slot -> player LUT name, per age
SLOTS = {
    'adult': {
        'sword1_blade': 'SWORD_BLADE', 'sword1_hilt': 'SWORD_HILT', 'sword1_sheath': 'SWORD_SHEATH',
        'sword2_blade': 'LONGSWORD_BLADE', 'sword2_hilt': 'LONGSWORD_HILT',
        'sword2_broken': 'LONGSWORD_BROKEN', 'sword2_blade_broken': 'LONGSWORD_BROKEN',
        'shield1_held': 'SHIELD_HYLIAN', 'shield2_held': 'SHIELD_MIRROR',
        'bow': 'BOW', 'hookshot': 'HOOKSHOT', 'hammer': 'HAMMER', 'bottle': 'BOTTLE',
        'ocarina_1': 'OCARINA_TIME', 'ocarina_1_a': 'OCARINA_TIME', 'ocarina_2': 'OCARINA_TIME',
    },
    'child': {
        'sword0_blade': 'SWORD_BLADE', 'sword0_hilt': 'SWORD_HILT', 'sword0_sheath': 'SWORD_SHEATH',
        'shield0_held': 'SHIELD_DEKU', 'shield0_back': 'SHIELD_DEKU',
        'shield1_held': 'SHIELD_HYLIAN_BACK', 'shield1_back': 'SHIELD_HYLIAN_BACK',
        'ocarina_0': 'OCARINA_FAIRY', 'ocarina_1': 'OCARINA_TIME', 'ocarina_1_c': 'OCARINA_TIME',
        'ocarina_1_a': 'OCARINA_TIME', 'ocarina_2': 'OCARINA_TIME',
        'slingshot': 'SLINGSHOT', 'boomerang': 'BOOMERANG', 'bottle': 'BOTTLE',
        'master_sword': 'MASTER_SWORD', 'deku_stick': 'DEKU_STICK',
    },
}
# A pak's third-person item also stands in for the first-person one when it has no separate one.
STANDS_IN = {'adult': {'FPS_HOOKSHOT': 'HOOKSHOT'}, 'child': {}}


def _tag_string(d, tag):
    i = d.find(tag)
    if i < 0:
        return ''
    return d[i + 16:].split(b'\0')[0].decode('utf-8', 'replace').strip()


def is_equipment(d):
    i = d.find(HEADER)
    return i >= 0 and i + 16 <= len(d) and d[i + 11] == TYPE_EQUIPMENT and b'EQUIPMANIFEST' in d


def parse(d):
    """{'name', 'category', 'dls': {age: {LUT name: segment address}}, 'unused': [slot names]}."""
    i = d.find(HEADER)
    count = struct.unpack_from('>I', d, i + 12)[0]
    table = [struct.unpack_from('>II', d, i + 16 + 8 * k) for k in range(count)]
    j = d.find(b'EQUIPMANIFEST')
    manifest = json.loads(d[j + 16:d.index(b'\xff', j)].decode('utf-8'))
    out = {'name': _tag_string(d, b'EQUIPMENTNAME'), 'category': _tag_string(d, b'EQUIPMENTCAT'),
           'dls': {}, 'unused': []}
    for age in ('adult', 'child'):
        for idx, slot in (manifest.get('OOT', {}).get(age) or {}).items():
            w0, w1 = table[int(idx)]
            lut = SLOTS[age].get(slot)
            if lut is None or w0 >> 24 != 0xDE or w1 >> 24 != 6:
                out['unused'].append(f'{age} {slot}')
                continue
            out['dls'].setdefault(age, {})[lut] = w1
    for age, sub in STANDS_IN.items():
        dls = out['dls'].get(age, {})
        for fps, item in sub.items():
            if item in dls and fps not in dls:
                dls[fps] = dls[item]
    return out
