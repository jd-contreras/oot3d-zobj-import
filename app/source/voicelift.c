#include "voicelift.h"

#include <stdlib.h>
#include <string.h>

// A voice pack differs from the game's sound archive in one internal file only: the
// sound-effect wave archive WARC_SE, and in it only Link's voice waves. Those waves are copied
// from the pack into the target's WARC_SE, and the target is written out again with that one
// file replaced. Everything else in the target (the music the randomizer shuffled, every other
// sound) is kept byte for byte.

// Link's voice in WARC_SE: waves 250-329 (adult and child), plus the two surprise yells.
#define LINK_FIRST 250
#define LINK_LAST 329
static const uint32_t sLinkExtra[] = { 374, 375 };

#define BLOCK_STRINGS 0x2000
#define BLOCK_INFO 0x2001
#define BLOCK_FILES 0x2002
#define INFO_WAVE_ARCHIVES 0x2103
#define INFO_FILES 0x2106
#define FILE_INTERNAL 0x220C
#define ALIGNMENT 0x20
#define MAX_FILES 1024
#define MAX_WAVES 4096

typedef struct {
    const uint8_t* d;
    size_t len;
    int ok; // cleared by any read outside the data
} Reader;

static uint32_t U32(Reader* r, size_t off) {
    if (off > r->len || r->len - off < 4) {
        r->ok = 0;
        return 0;
    }
    const uint8_t* p = r->d + off;
    return (uint32_t)p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}

static uint32_t U16(Reader* r, size_t off) {
    if (off > r->len || r->len - off < 2) {
        r->ok = 0;
        return 0;
    }
    return (uint32_t)r->d[off] | ((uint32_t)r->d[off + 1] << 8);
}

static void Put32(uint8_t* p, uint32_t v) {
    p[0] = (uint8_t)v;
    p[1] = (uint8_t)(v >> 8);
    p[2] = (uint8_t)(v >> 16);
    p[3] = (uint8_t)(v >> 24);
}

static int InRange(const Reader* r, size_t off, size_t size) {
    return off <= r->len && size <= r->len - off;
}

// One internal file of a sound archive.
typedef struct {
    size_t off;  // absolute offset of its data
    size_t size;
    size_t info; // absolute offset of its sized reference in the INFO block
} ArchiveFile;

typedef struct {
    Reader r;
    size_t fileBlock; // offset of the FILE block
    ArchiveFile* files;
    int fileCount;
    int warcSe;       // index of WARC_SE in files
} Archive;

static void FreeArchive(Archive* a) {
    free(a->files);
    a->files = NULL;
}

// Reads the parts of a sound archive needed here. Returns 1 on success.
static int ReadArchive(Archive* a, const uint8_t* d, size_t len) {
    memset(a, 0, sizeof(*a));
    a->r.d = d;
    a->r.len = len;
    a->r.ok = 1;
    a->warcSe = -1;
    Reader* r = &a->r;
    if (!VoiceLift_IsArchive(d, len)) return 0;

    size_t strings = 0, info = 0;
    const uint32_t blocks = U32(r, 0x10);
    for (uint32_t i = 0; i < blocks && i < 8; i++) {
        const uint32_t type = U16(r, 0x14 + 12 * i);
        const uint32_t off = U32(r, 0x14 + 12 * i + 4);
        if (type == BLOCK_STRINGS) strings = off;
        else if (type == BLOCK_INFO) info = off;
        else if (type == BLOCK_FILES) a->fileBlock = off;
    }
    if (!r->ok || !strings || !info || !a->fileBlock) return 0;

    const size_t stringTable = strings + 8 + U32(r, strings + 8 + 4);
    const uint32_t stringCount = U32(r, stringTable);
    const size_t body = info + 8;
    size_t warcTable = 0, fileTable = 0;
    for (int k = 0; k < 8; k++) {
        const uint32_t type = U16(r, body + 8 * k);
        const size_t at = body + U32(r, body + 8 * k + 4);
        if (type == INFO_WAVE_ARCHIVES) warcTable = at;
        else if (type == INFO_FILES) fileTable = at;
    }
    if (!r->ok || !warcTable || !fileTable) return 0;

    // The wave archive named WARC_SE, and the file it lives in.
    uint32_t warcFileId = 0xFFFFFFFF;
    const uint32_t warcCount = U32(r, warcTable);
    for (uint32_t i = 0; i < warcCount && i < MAX_FILES; i++) {
        const size_t o = warcTable + U32(r, warcTable + 4 + 8 * i + 4);
        if (!(U32(r, o + 8) & 1)) continue; // no name
        const uint32_t nameIndex = U32(r, o + 12);
        if (nameIndex >= stringCount) continue;
        const size_t name = stringTable + U32(r, stringTable + 4 + 12 * nameIndex + 4);
        if (r->ok && InRange(r, name, 8) && memcmp(d + name, "WARC_SE", 8) == 0) warcFileId = U32(r, o);
    }

    const uint32_t fileCount = U32(r, fileTable);
    if (!r->ok || fileCount == 0 || fileCount > MAX_FILES || warcFileId >= fileCount) return 0;
    a->files = calloc(fileCount, sizeof(ArchiveFile));
    if (!a->files) return 0;
    a->fileCount = (int)fileCount;
    for (uint32_t i = 0; i < fileCount; i++) {
        const size_t o = fileTable + U32(r, fileTable + 4 + 8 * i + 4);
        if (U16(r, o) != FILE_INTERNAL) continue; // an external file: nothing stored here
        const size_t p = o + U32(r, o + 4);
        const int32_t rel = (int32_t)U32(r, p + 4);
        if (rel < 0) continue;
        a->files[i].info = p;
        a->files[i].off = a->fileBlock + 8 + (uint32_t)rel;
        a->files[i].size = U32(r, p + 8);
        if (!InRange(r, a->files[i].off, a->files[i].size)) r->ok = 0;
    }
    a->warcSe = (int)warcFileId;
    if (!r->ok || a->files[warcFileId].size == 0) {
        FreeArchive(a);
        return 0;
    }
    return 1;
}

// A wave archive (CWAR): its wave table and FILE block.
typedef struct {
    Reader r;
    size_t info;  // offset of the INFO block
    size_t files; // offset of the FILE block
    uint32_t count;
} WaveArchive;

static int ReadWaveArchive(WaveArchive* w, const uint8_t* d, size_t len) {
    memset(w, 0, sizeof(*w));
    w->r.d = d;
    w->r.len = len;
    w->r.ok = 1;
    if (len < 0x40 || memcmp(d, "CWAR", 4) != 0) return 0;
    w->info = U32(&w->r, 0x18);
    w->files = U32(&w->r, 0x24);
    if (!InRange(&w->r, w->info, 12) || !InRange(&w->r, w->files, 8)) return 0;
    if (memcmp(d + w->info, "INFO", 4) != 0 || memcmp(d + w->files, "FILE", 4) != 0) return 0;
    w->count = U32(&w->r, w->info + 8);
    if (w->count == 0 || w->count > MAX_WAVES || !InRange(&w->r, w->info + 12, 12 * (size_t)w->count)) return 0;
    for (uint32_t k = 0; k < w->count; k++) {
        const size_t off = w->files + 8 + U32(&w->r, w->info + 12 + 12 * k + 4);
        if (!InRange(&w->r, off, U32(&w->r, w->info + 12 + 12 * k + 8))) return 0;
    }
    return w->r.ok;
}

static const uint8_t* Wave(WaveArchive* w, uint32_t k, size_t* size) {
    *size = U32(&w->r, w->info + 12 + 12 * k + 8);
    return w->r.d + w->files + 8 + U32(&w->r, w->info + 12 + 12 * k + 4);
}

static int IsLinkWave(uint32_t k) {
    if (k >= LINK_FIRST && k <= LINK_LAST) return 1;
    for (size_t i = 0; i < sizeof(sLinkExtra) / sizeof(sLinkExtra[0]); i++) {
        if (k == sLinkExtra[i]) return 1;
    }
    return 0;
}

static size_t Align(size_t n) {
    return (n + ALIGNMENT - 1) & ~(size_t)(ALIGNMENT - 1);
}

// The target's WARC_SE with Link's waves taken from the pack's. Waves stay 0x20-aligned.
static uint8_t* MergeWaveArchive(WaveArchive* tw, WaveArchive* pw, size_t* outLen) {
    size_t total = tw->r.len + ALIGNMENT * (size_t)tw->count;
    for (uint32_t k = 0; k < tw->count; k++) {
        size_t size;
        if (IsLinkWave(k)) {
            Wave(pw, k, &size);
            total += size;
        }
    }
    uint8_t* out = calloc(total, 1);
    if (!out) return NULL;
    const size_t fb = tw->files;
    memcpy(out, tw->r.d, fb + 8);
    size_t pos = fb + 8;
    for (uint32_t k = 0; k < tw->count; k++) {
        size_t size;
        const uint8_t* data = IsLinkWave(k) ? Wave(pw, k, &size) : Wave(tw, k, &size);
        pos = Align(pos);
        Put32(out + tw->info + 12 + 12 * k + 4, (uint32_t)(pos - (fb + 8)));
        Put32(out + tw->info + 12 + 12 * k + 8, (uint32_t)size);
        memcpy(out + pos, data, size);
        pos += size;
    }
    // Keep the padding the archive had after its last wave.
    size_t lastSize;
    const uint8_t* last = Wave(tw, tw->count - 1, &lastSize);
    const size_t origEnd = fb + U32(&tw->r, fb + 4);
    const size_t lastEnd = (size_t)(last - tw->r.d) + lastSize;
    if (origEnd > lastEnd && origEnd <= tw->r.len) pos += origEnd - lastEnd;
    Put32(out + fb + 4, (uint32_t)(pos - fb));
    Put32(out + 0x28, (uint32_t)(pos - fb));
    Put32(out + 0x0C, (uint32_t)pos);
    *outLen = pos;
    return out;
}

int VoiceLift_IsArchive(const uint8_t* data, size_t len) {
    return len >= 0x40 && memcmp(data, "CSAR", 4) == 0;
}

int VoiceLift_Locate(const uint8_t* archive, size_t len, size_t* offset) {
    Archive a;
    if (!ReadArchive(&a, archive, len)) return 0;
    WaveArchive w;
    int ok = ReadWaveArchive(&w, archive + a.files[a.warcSe].off, a.files[a.warcSe].size) && w.count > LINK_FIRST;
    if (ok) {
        size_t size;
        *offset = (size_t)(Wave(&w, LINK_FIRST, &size) - archive);
    }
    FreeArchive(&a);
    return ok;
}

LiftResult VoiceLift(const uint8_t* pack, size_t packLen, const uint8_t* target, size_t targetLen, uint8_t** out,
                     size_t* outLen) {
    *out = NULL;
    *outLen = 0;
    Archive pa, ta;
    if (!ReadArchive(&pa, pack, packLen)) return LIFT_BAD_PACK;
    if (!ReadArchive(&ta, target, targetLen)) {
        FreeArchive(&pa);
        return LIFT_BAD_TARGET;
    }
    LiftResult res = LIFT_OK;
    uint8_t* warc = NULL;
    uint8_t* result = NULL;
    int* order = NULL;
    WaveArchive pw, tw;
    if (!ReadWaveArchive(&pw, pack + pa.files[pa.warcSe].off, pa.files[pa.warcSe].size)) res = LIFT_BAD_PACK;
    else if (!ReadWaveArchive(&tw, target + ta.files[ta.warcSe].off, ta.files[ta.warcSe].size)) res = LIFT_BAD_TARGET;
    else if (pw.count != tw.count || tw.count <= sLinkExtra[1]) res = LIFT_BAD_PACK;
    if (res != LIFT_OK) goto done;

    // Nothing to do if the target already has every one of the pack's Link waves.
    int same = 1;
    for (uint32_t k = 0; k < tw.count && same; k++) {
        if (!IsLinkWave(k)) continue;
        size_t ps, ts;
        const uint8_t* p = Wave(&pw, k, &ps);
        const uint8_t* t = Wave(&tw, k, &ts);
        same = ps == ts && memcmp(p, t, ps) == 0;
    }
    if (same) {
        res = LIFT_SAME;
        goto done;
    }

    res = LIFT_NO_MEMORY;
    size_t warcLen = 0;
    warc = MergeWaveArchive(&tw, &pw, &warcLen);
    if (!warc) goto done;

    // Write the target again, its files in the order they are stored, with WARC_SE replaced.
    order = malloc((size_t)ta.fileCount * sizeof(int));
    result = calloc(targetLen + warcLen + ALIGNMENT * (size_t)ta.fileCount, 1);
    if (!order || !result) goto done;
    int n = 0;
    for (int i = 0; i < ta.fileCount; i++) {
        if (!ta.files[i].info) continue;
        int j = n++;
        while (j > 0 && ta.files[order[j - 1]].off > ta.files[i].off) {
            order[j] = order[j - 1];
            j--;
        }
        order[j] = i;
    }
    const size_t fb = ta.fileBlock;
    memcpy(result, target, fb + 8);
    size_t pos = fb + 8, lastEnd = 0;
    for (int j = 0; j < n; j++) {
        const ArchiveFile* f = &ta.files[order[j]];
        const uint8_t* data = order[j] == ta.warcSe ? warc : target + f->off;
        const size_t size = order[j] == ta.warcSe ? warcLen : f->size;
        pos = Align(pos);
        Put32(result + f->info + 4, (uint32_t)(pos - (fb + 8)));
        Put32(result + f->info + 8, (uint32_t)size);
        memcpy(result + pos, data, size);
        pos += size;
        if (f->off + f->size > lastEnd) lastEnd = f->off + f->size;
    }
    const size_t origEnd = fb + U32(&ta.r, fb + 4);
    if (origEnd > lastEnd && origEnd <= targetLen) pos += origEnd - lastEnd;
    Put32(result + fb + 4, (uint32_t)(pos - fb));
    Put32(result + 0x14 + 12 * 2 + 8, (uint32_t)(pos - fb));
    Put32(result + 0x0C, (uint32_t)pos);
    *out = result;
    *outLen = pos;
    result = NULL;
    res = LIFT_OK;

done:
    free(order);
    free(result);
    free(warc);
    FreeArchive(&pa);
    FreeArchive(&ta);
    return res;
}
