#include "merge.h"

#include <stdlib.h>
#include <string.h>

// A seed's code.ips is the randomizer's base patch followed by that seed's own records. The
// base patch is replaced by ours and the seed's records are kept, moved to where the same data
// sits in our build. The official randomizer builds come from another compiler, so the seed's
// addresses say nothing about ours: its records are matched by the order the randomizer writes
// them, their sizes, and the symbols every seed has.

#define IPS_HEADER 5
#define IPS_EOF 3
#define IPS_MAX_CHUNK 0xFFFF
#define CODE_BASE 0x100000 // file offset 0 of code.bin is this address
#define TUNIC_SETTINGS 5   // Custom Tunic Colors and the four rainbow tunic settings after it

typedef struct {
    uint32_t off;        // file offset
    uint32_t len;
    const uint8_t* data; // NULL for a run of `fill`
    uint8_t fill;
} Record;

typedef struct {
    Record* recs;
    int count;
} RecordList;

// Symbols whose record always has the symbol's full size, and symbols every seed writes.
static const uint8_t sWhole[SYM_COUNT] = {
    [SYM_SETTINGS] = 1,      [SYM_SPOILER_DATA] = 1,        [SYM_SCRUB_PRICES] = 1,          [SYM_SHOP_PRICES] = 1,
    [SYM_DUNGEON_REWARDS] = 1, [SYM_MESSAGE_ENTRIES_PTR] = 1, [SYM_MESSAGE_ENTRIES_COUNT] = 1, [SYM_SFX_DATA] = 1,
};
static const uint8_t sAlways[SYM_COUNT] = {
    [SYM_ITEM_OVERRIDES] = 1,      [SYM_SETTINGS] = 1,              [SYM_SPOILER_DATA] = 1, [SYM_CUSTOM_MESSAGES] = 1,
    [SYM_MESSAGE_ENTRIES_PTR] = 1, [SYM_MESSAGE_ENTRIES_COUNT] = 1, [SYM_SFX_DATA] = 1,
};

static uint32_t Be(const uint8_t* p, int n) {
    uint32_t v = 0;
    while (n--) v = (v << 8) | *p++;
    return v;
}

static MergeResult ParseRecords(const uint8_t* ips, size_t len, RecordList* list) {
    list->recs = NULL;
    list->count = 0;
    if (len < IPS_HEADER + IPS_EOF || memcmp(ips, "PATCH", IPS_HEADER) != 0 || memcmp(ips + len - IPS_EOF, "EOF", IPS_EOF) != 0) {
        return MERGE_NOT_IPS;
    }
    const size_t end = len - IPS_EOF;
    for (int pass = 0; pass < 2; pass++) {
        size_t pos = IPS_HEADER;
        int n = 0;
        while (pos < end) {
            if (pos + 5 > end) return MERGE_NOT_IPS;
            Record r = { Be(ips + pos, 3), Be(ips + pos + 3, 2), NULL, 0 };
            pos += 5;
            if (r.len == 0) {
                if (pos + 3 > end) return MERGE_NOT_IPS;
                r.len = Be(ips + pos, 2);
                r.fill = ips[pos + 2];
                pos += 3;
            } else {
                if (pos + r.len > end) return MERGE_NOT_IPS;
                r.data = ips + pos;
                pos += r.len;
            }
            if (pass) list->recs[n] = r;
            n++;
        }
        if (!pass) {
            list->recs = malloc((n ? n : 1) * sizeof(Record));
            if (!list->recs) return MERGE_NO_MEMORY;
            list->count = n;
        }
    }
    return MERGE_OK;
}

// The base patch is written in ascending order; the seed's own records start where that breaks.
static int SplitIndex(const RecordList* list) {
    for (int i = 1; i < list->count; i++) {
        if (list->recs[i].off < list->recs[i - 1].off) return i;
    }
    return list->count;
}

// Marks the game bytes (below the randomizer's own code) that records [0, count) change.
static void MarkGameBytes(uint8_t* bits, const Record* recs, int count, uint32_t limit) {
    for (int i = 0; i < count; i++) {
        uint32_t end = recs[i].off + recs[i].len;
        if (end > limit) end = limit;
        for (uint32_t b = recs[i].off; b < end; b++) bits[b >> 3] |= (uint8_t)(1 << (b & 7));
    }
}

MergeResult Merge_Identify(const uint8_t* seed, size_t seedLen, const uint8_t* base, size_t baseLen,
                           const MergeBuild* build) {
    // A file that starts with our whole base patch is one we already patched.
    if (baseLen > IPS_HEADER + IPS_EOF && seedLen >= baseLen && memcmp(seed, base, baseLen - IPS_EOF) == 0) {
        return MERGE_ALREADY_PATCHED;
    }
    RecordList s, b;
    MergeResult res = ParseRecords(seed, seedLen, &s);
    if (res != MERGE_OK) return res;
    res = ParseRecords(base, baseLen, &b);
    if (res != MERGE_OK) {
        free(s.recs);
        return res;
    }
    const uint32_t limit = build->randoStart - CODE_BASE;
    const size_t bytes = (limit + 7) / 8;
    uint8_t* theirs = calloc(bytes, 1);
    uint8_t* ours = calloc(bytes, 1);
    res = MERGE_NO_MEMORY;
    if (theirs && ours) {
        MarkGameBytes(theirs, s.recs, SplitIndex(&s), limit);
        MarkGameBytes(ours, b.recs, b.count, limit);
        // The seed's base patch must change a subset of what ours changes, and ours exactly
        // `addedBytes` more (the Extra Buttons hooks).
        uint32_t extraTheirs = 0, extraOurs = 0;
        for (size_t i = 0; i < bytes; i++) {
            extraTheirs += (uint32_t)__builtin_popcount(theirs[i] & ~ours[i] & 0xFF);
            extraOurs += (uint32_t)__builtin_popcount(ours[i] & ~theirs[i] & 0xFF);
        }
        if (extraTheirs == 0 && extraOurs == build->addedBytes) res = MERGE_OK;
        else res = MERGE_OTHER_BUILD;
    }
    free(theirs);
    free(ours);
    free(s.recs);
    free(b.recs);
    return res;
}

// Which symbol each seed record belongs to. names[i] is a SYM_ index or -1 for a record at a
// game address; into[i] is the offset into the symbol (a record just above the previous one,
// inside that symbol, continues it). Returns 1 when every record is placed.
typedef struct {
    const Record* recs;
    int count;
    const MergeBuild* build;
    uint32_t limit;
    int* names;
    uint32_t* into;
} Assign;

static int Walk(Assign* a, int i, int cursor, int last, uint32_t lastOff, uint32_t seen) {
    if (i == a->count) {
        for (int s = 0; s < SYM_COUNT; s++) {
            if (sAlways[s] && a->build->symbols[s].addr && !(seen & (1u << s))) return 0;
        }
        return 1;
    }
    const Record* r = &a->recs[i];
    a->into[i] = 0;
    if (r->off < a->limit) { // a game address, kept as it is
        a->names[i] = -1;
        return Walk(a, i + 1, cursor, last, lastOff, seen);
    }
    if (last >= 0 && r->off > lastOff) {
        const uint32_t size = a->build->symbols[last].size;
        if (!size || r->off - lastOff < size) {
            a->names[i] = last;
            a->into[i] = r->off - lastOff;
            return Walk(a, i + 1, cursor, last, lastOff, seen);
        }
    }
    for (int c = cursor; c < SYM_COUNT; c++) {
        const MergeSymbol* sym = &a->build->symbols[c];
        if (!sym->addr) continue;
        if (sWhole[c] ? r->len != sym->size : (sym->size && r->len > sym->size)) continue;
        a->names[i] = c;
        a->into[i] = 0;
        if (Walk(a, i + 1, c + 1, c, r->off, seen | (1u << c))) return 1;
    }
    return 0;
}

static void PutRecord(uint8_t** p, uint32_t off, const uint8_t* data, uint32_t len) {
    for (uint32_t i = 0; i < len; i += IPS_MAX_CHUNK) {
        const uint32_t n = len - i < IPS_MAX_CHUNK ? len - i : IPS_MAX_CHUNK;
        const uint32_t o = off + i;
        uint8_t* q = *p;
        q[0] = (uint8_t)(o >> 16);
        q[1] = (uint8_t)(o >> 8);
        q[2] = (uint8_t)o;
        q[3] = (uint8_t)(n >> 8);
        q[4] = (uint8_t)n;
        memcpy(q + 5, data + i, n);
        *p = q + 5 + n;
    }
}

MergeResult Merge_Apply(const uint8_t* seed, size_t seedLen, const uint8_t* base, size_t baseLen,
                        const MergeBuild* build, int dropTunics, int* tunicsWereOn, uint8_t** out, size_t* outLen) {
    *out = NULL;
    *outLen = 0;
    if (tunicsWereOn) *tunicsWereOn = 0;
    RecordList s;
    MergeResult res = ParseRecords(seed, seedLen, &s);
    if (res != MERGE_OK) return res;
    if (baseLen < IPS_HEADER + IPS_EOF) {
        free(s.recs);
        return MERGE_NOT_IPS;
    }
    const int split = SplitIndex(&s);
    const int count = s.count - split;
    const Record* extras = s.recs + split;

    int* names = malloc((count ? count : 1) * sizeof(int));
    uint32_t* into = malloc((count ? count : 1) * sizeof(uint32_t));
    uint8_t* result = NULL;
    uint8_t* scratch = NULL;
    res = MERGE_NO_MEMORY;
    if (!names || !into) goto done;

    Assign a = { extras, count, build, build->randoStart - CODE_BASE, names, into };
    if (!Walk(&a, 0, 0, -1, 0, 0)) {
        res = MERGE_NOT_A_SEED;
        goto done;
    }

    // Worst case: every record split into IPS_MAX_CHUNK pieces, each with a 5-byte header.
    size_t total = baseLen;
    uint32_t largest = 4;
    for (int i = 0; i < count; i++) {
        total += extras[i].len + 5 * (extras[i].len / IPS_MAX_CHUNK + 1);
        if (extras[i].len > largest) largest = extras[i].len;
    }
    result = malloc(total);
    scratch = malloc(largest);
    if (!result || !scratch) goto done;

    memcpy(result, base, baseLen - IPS_EOF);
    uint8_t* p = result + baseLen - IPS_EOF;
    uint32_t msgOld = 0, msgNew = 0;
    for (int i = 0; i < count; i++) {
        const Record* r = &extras[i];
        const uint8_t* data = r->data;
        if (!data) { // a run: write it out as plain bytes
            memset(scratch, r->fill, r->len);
            data = scratch;
        }
        uint32_t newOff = r->off;
        if (names[i] >= 0) newOff = build->symbols[names[i]].addr - CODE_BASE + into[i];

        if (names[i] == SYM_CUSTOM_MESSAGES && into[i] == 0) {
            msgOld = r->off;
            msgNew = newOff;
        } else if (names[i] == SYM_MESSAGE_ENTRIES_PTR) {
            // A pointer into the custom text: move it by as much as the text moved.
            uint32_t v = (uint32_t)data[0] | ((uint32_t)data[1] << 8) | ((uint32_t)data[2] << 16) | ((uint32_t)data[3] << 24);
            v = v - msgOld + msgNew;
            scratch[0] = (uint8_t)v;
            scratch[1] = (uint8_t)(v >> 8);
            scratch[2] = (uint8_t)(v >> 16);
            scratch[3] = (uint8_t)(v >> 24);
            data = scratch;
        } else if (names[i] == SYM_SETTINGS) {
            if (data[build->settingsRegion] != build->region) {
                res = MERGE_WRONG_REGION;
                goto done;
            }
            int on = 0;
            for (uint32_t t = 0; t < TUNIC_SETTINGS && build->settingsTunics + t < r->len; t++) {
                on |= data[build->settingsTunics + t];
            }
            if (tunicsWereOn) *tunicsWereOn = on != 0;
            if (dropTunics && on) {
                if (data != scratch) memcpy(scratch, data, r->len);
                for (uint32_t t = 0; t < TUNIC_SETTINGS && build->settingsTunics + t < r->len; t++) {
                    scratch[build->settingsTunics + t] = 0;
                }
                data = scratch;
            }
        }
        PutRecord(&p, newOff, data, r->len);
    }
    memcpy(p, "EOF", IPS_EOF);
    *out = result;
    *outLen = (size_t)(p + IPS_EOF - result);
    result = NULL;
    res = MERGE_OK;

done:
    free(result);
    free(scratch);
    free(names);
    free(into);
    free(s.recs);
    return res;
}
