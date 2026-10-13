#include "ui.h"

#include <stdarg.h>
#include <stdio.h>

static C3D_RenderTarget *sTop, *sBottom;
static C2D_TextBuf sBuf;

void ui_init(void) {
    gfxInitDefault();
    C3D_Init(C3D_DEFAULT_CMDBUF_SIZE);
    C2D_Init(C2D_DEFAULT_MAX_OBJECTS);
    C2D_Prepare();
    sTop = C2D_CreateScreenTarget(GFX_TOP, GFX_LEFT);
    sBottom = C2D_CreateScreenTarget(GFX_BOTTOM, GFX_LEFT);
    sBuf = C2D_TextBufNew(4096);
}

void ui_exit(void) {
    C2D_TextBufDelete(sBuf);
    C2D_Fini();
    C3D_Fini();
    gfxExit();
}

void ui_begin(void) {
    C2D_TextBufClear(sBuf);
    C3D_FrameBegin(C3D_FRAME_SYNCDRAW);
}

void ui_top(void) {
    C2D_TargetClear(sTop, CLR_BG);
    C2D_SceneBegin(sTop);
}

void ui_bottom(void) {
    C2D_TargetClear(sBottom, CLR_BG);
    C2D_SceneBegin(sBottom);
}

void ui_end(void) {
    C3D_FrameEnd(0);
}

void ui_rect(float x, float y, float w, float h, u32 color) {
    C2D_DrawRectSolid(x, y, 0.0f, w, h, color);
}

static void DrawString(float x, float y, float scale, u32 color, u32 flags, float wrap, float fit, const char* s) {
    C2D_Text t;
    C2D_TextParse(&t, sBuf, s);
    C2D_TextOptimize(&t);
    float sx = scale;
    if (fit > 0) {
        float w, h;
        C2D_TextGetDimensions(&t, scale, scale, &w, &h);
        if (w > fit) sx = scale * fit / w;
    }
    if (flags & C2D_WordWrap) C2D_DrawText(&t, C2D_WithColor | flags, x, y, 0.5f, sx, scale, color, wrap);
    else C2D_DrawText(&t, C2D_WithColor | flags, x, y, 0.5f, sx, scale, color);
}

#define FORMAT(buf)                            \
    char buf[256];                             \
    va_list ap;                                \
    va_start(ap, fmt);                         \
    vsnprintf(buf, sizeof(buf), fmt, ap);      \
    va_end(ap)

void ui_text(float x, float y, float scale, u32 color, const char* fmt, ...) {
    FORMAT(buf);
    DrawString(x, y, scale, color, 0, 0, 0, buf);
}

void ui_text_right(float right_x, float y, float scale, u32 color, const char* fmt, ...) {
    FORMAT(buf);
    DrawString(right_x, y, scale, color, C2D_AlignRight, 0, 0, buf);
}

void ui_text_center(float center_x, float y, float scale, u32 color, const char* fmt, ...) {
    FORMAT(buf);
    DrawString(center_x, y, scale, color, C2D_AlignCenter, 0, 0, buf);
}

void ui_text_wrap(float x, float y, float scale, u32 color, float width, const char* text) {
    DrawString(x, y, scale, color, C2D_WordWrap, width, 0, text);
}

void ui_text_fit(float x, float y, float scale, u32 color, float width, const char* text) {
    DrawString(x, y, scale, color, 0, 0, width, text);
}

bool ui_hit(const ui_box* b, const touchPosition* t) {
    return t->px >= b->x && t->px < b->x + b->w && t->py >= b->y && t->py < b->y + b->h;
}

void ui_progress(const char* title, const char* what, float fraction) {
    const float x = 24, y = 118, w = TOP_W - 48, h = 18;
    ui_begin();
    ui_top();
    ui_rect(0, 0, TOP_W, 34, CLR_HEADER);
    ui_text(12, 7, 0.65f, CLR_TEXT, "%s", title);
    ui_text(x, 84, 0.55f, CLR_TEXT, "%s...", what);
    ui_rect(x, y, w, h, CLR_PANEL);
    ui_rect(x, y, w * fraction, h, CLR_SEL);
    ui_text_right(x + w, y + h + 6, 0.5f, CLR_DIM, "%d%%", (int)(fraction * 100));
    ui_bottom();
    ui_text(16, 16, 0.55f, CLR_DIM, "Please wait. Do not power off.");
    ui_end();
}

void ui_busy(const char* title, const char* msg) {
    ui_begin();
    ui_top();
    ui_rect(0, 0, TOP_W, 34, CLR_HEADER);
    ui_text(12, 7, 0.65f, CLR_TEXT, "%s", title);
    ui_text_wrap(16, 60, 0.55f, CLR_TEXT, TOP_W - 32, msg);
    ui_bottom();
    ui_text(16, 16, 0.55f, CLR_DIM, "Please wait. Do not power off.");
    ui_end();
}
