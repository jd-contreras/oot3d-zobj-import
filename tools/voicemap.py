"""Work out which WARC waves each OoT3D voice sound can play.

Runs the sound's CSEQ script with a small interpreter many times (different random outcomes and
toggle states) and resolves every (program, key) it plays through the CBNK to a wave id.
"""
import struct, random
import csar

N64_ADULT = [  # N64 sound id 0x6800 + i  ->  OoT3D sound name (same order as the decomp)
    'SWORD_N', 'SWORD_L', 'LASH', 'HANG', 'CLIMB_END', 'DAMAGE_S', 'FREEZE', 'FALL_S', 'FALL_L',
    'BREATH_REST', 'BREATH_DRINK', 'DOWN', 'TAKEN_AWAY', 'HELD', 'SNEEZE', 'SWEAT', 'DRINK', 'RELAX',
    'SWORD_PUTAWAY', 'GROAN', 'AUTO_JUMP', 'MAGIC_NALE', 'SURPRISE', 'MAGIC_FROL', 'PUSH',
    'HOOKSHOT_HANG', 'LAND_DAMAGE_S', 'NULL_0x1b', 'MAGIC_ATTACK', 'BL_DOWN', 'DEMO_DAMAGE',
    'ELECTRIC_SHOCK_LV']


def sound_name(n64_id):
    """0x6800-0x681F adult, 0x6820-0x683F child ('_KID' names; child SWORD_L is ROLLING_CUT)."""
    i = n64_id - 0x6800
    if 0 <= i < 32:
        return 'NA_SE_VO_LI_' + N64_ADULT[i]
    if 32 <= i < 64:
        base = N64_ADULT[i - 32]
        if base == 'SWORD_L':
            base = 'ROLLING_CUT'
        if base == 'BL_DOWN':
            return 'NA_SE_VO_BL_DOWN_KID'
        return 'NA_SE_VO_LI_' + base + '_KID'
    return None


class Bank:
    def __init__(self, b, wave_ids):
        self.b, self.wave_ids = b, wave_ids
        self.body = 0x28
        _, it = self._ref(self.body + 8)
        tab = self.body + it
        n = struct.unpack_from('<I', b, tab)[0]
        self.insts = [tab + self._ref(tab + 4 + 8 * k)[1] for k in range(n)]

    def _ref(self, o):
        return struct.unpack_from('<Hxxi', self.b, o)

    def _region(self, table_ref_at, key):
        t, off = self._ref(table_ref_at)
        tab = table_ref_at + off
        b = self.b
        if t == 0x6000:  # direct: a single reference
            rt, ro = self._ref(tab)
            return tab + ro
        if t == 0x6001:  # range: count, key bounds, refs
            n = struct.unpack_from('<I', b, tab)[0]
            keys = b[tab + 4:tab + 4 + n]
            refs = tab + 4 + ((n + 3) & ~3)
            for i, hi in enumerate(keys):
                if key <= hi:
                    rt, ro = self._ref(refs + 8 * i)
                    return tab + ro
            return None
        if t == 0x6002:  # index: min, max, refs
            lo, hi = b[tab], b[tab + 1]
            if not lo <= key <= hi:
                return None
            rt, ro = self._ref(tab + 4 + 8 * (key - lo))
            return tab + ro
        raise ValueError(hex(t))

    def wave(self, prg, key, vel=100):
        inst = self.insts[prg]
        kr = self._region(inst, key)
        if kr is None:
            return None
        vr = self._region(kr, vel)
        idx = struct.unpack_from('<I', self.b, vr)[0]
        return self.wave_ids[idx]


def _varlen(d, p):
    v = 0
    while True:
        c = d[p]; p += 1
        v = (v << 7) | (c & 0x7F)
        if not c & 0x80:
            return v, p


def run(data, start, rng, toggle):
    """Interpret from `start`; return list of (program, key) notes played."""
    pc, prg, transpose = start, 0, 0
    # variables the game may set before playing (e.g. low-HP breathing reads var1): try small values
    var = {v: rng.randint(0, 3) for v in range(16)}
    var[31] = toggle
    stack, cmp_flag, notes = [], True, []
    for _ in range(400):
        op = data[pc]; pc += 1
        use_var = use_if = False
        rand_range = None
        while op in (0xA0, 0xA1, 0xA2):
            if op == 0xA1:
                use_var = True
            elif op == 0xA2:
                use_if = True
            else:
                rand_range = True
            op = data[pc]; pc += 1

        def arg_u8():
            nonlocal pc
            v = data[pc]; pc += 1
            return var.get(v, 0) if use_var else v

        def arg_s16():
            nonlocal pc
            if use_var:
                v = var.get(data[pc], 0); pc += 1
                return v
            if rand_range:
                lo, hi = struct.unpack_from('>hh', data, pc); pc += 4
                return rng.randint(lo, hi)
            v = struct.unpack_from('>h', data, pc)[0]; pc += 2
            return v

        skip = use_if and not cmp_flag
        if op < 0x80:  # note: key, velocity, length
            key = op
            pc += 1
            _, pc = _varlen(data, pc)
            if not skip:
                notes.append((prg, key + transpose))
        elif op == 0x80:  # wait
            if use_var:
                pc += 1
            else:
                _, pc = _varlen(data, pc)
        elif op == 0x81:  # program
            v, pc = _varlen(data, pc)
            if not skip:
                prg = v
        elif op == 0x88:  # open track: track u8, offset u24 (ignored)
            pc += 4
        elif op in (0x89, 0x8A):  # jump / call
            tgt = int.from_bytes(data[pc:pc + 3], 'big'); pc += 3
            if not skip:
                if op == 0x8A:
                    stack.append(pc)
                pc = tgt
        elif op == 0xFD:
            if not stack:
                break
            pc = stack.pop()
        elif op in (0xFF,):
            break
        elif op == 0xFE:
            pc += 2
        elif op == 0xC3:  # transpose s8
            v = arg_u8()
            if not skip:
                transpose = v - 256 if (not use_var and v > 127) else v
        elif 0xB0 <= op <= 0xDF:
            arg_u8()
        elif 0xE0 <= op <= 0xE3:
            arg_s16() if not use_var else arg_u8()
        elif op == 0xF0:  # extended var ops: sub u8, var u8, value s16 (or var with a1)
            sub = data[pc]; pc += 1
            vi = data[pc]; pc += 1
            val = arg_s16()
            cur = var.get(vi, 0)
            if skip:
                continue
            if sub == 0x80: var[vi] = val
            elif sub == 0x81: var[vi] = cur + val
            elif sub == 0x82: var[vi] = cur - val
            elif sub == 0x83: var[vi] = cur * val
            elif sub == 0x86: var[vi] = rng.randint(0, val) if val > 0 else 0  # randvar: 0..val inclusive
            elif sub == 0x87: var[vi] = cur & val
            elif sub == 0x88: var[vi] = cur | val
            elif sub == 0x89: var[vi] = cur ^ val
            elif sub == 0x8B: var[vi] = cur % val if val else 0
            elif sub == 0x90: cmp_flag = cur == val
            elif sub == 0x91: cmp_flag = cur >= val
            elif sub == 0x92: cmp_flag = cur > val
            elif sub == 0x93: cmp_flag = cur <= val
            elif sub == 0x94: cmp_flag = cur < val
            elif sub == 0x95: cmp_flag = cur != val
        else:
            raise ValueError('unknown seq command %02x at %x' % (op, pc - 1))
    return notes


def voice_waves(c, sound, with_kind=False):
    """Ordered list of distinct (warc_id, wave_index) the sound can play.
    with_kind: also return True when one playback plays several notes in sequence (sneeze, yawn)."""
    seq = c.file(sound.file_id)
    data = seq[seq.index(b'DATA') + 8:]
    bank_index = sound.banks[0] & 0xFFFFFF
    name, bank_file, _ = c.banks[bank_index]
    b = c.file(bank_file)
    wt = 0x28 + struct.unpack_from('<Hxxi', b, 0x28)[1]
    n = struct.unpack_from('<I', b, wt)[0]
    wave_ids = [struct.unpack_from('<II', b, wt + 4 + 8 * i) for i in range(n)]
    bank = Bank(b, wave_ids)
    seen, sequential = [], False
    rng = random.Random(1)
    for trial in range(400):
        # var31 persists between plays (last variant / alternation toggle): try every prior value
        notes = run(data, sound.start_offset, rng, trial % 16)
        sequential |= len(notes) > 1
        for prg, key in notes:
            w = bank.wave(prg, key)
            if w and w not in seen:
                seen.append(w)
    return (seen, sequential) if with_kind else seen
