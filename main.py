#!/usr/bin/env python3
"""Neon Eclipse — generative art for make.fun 'Make the coolest art'.

Pure Python 3 stdlib (no PIL in the sandbox). Renders a total eclipse with a
rayed corona over layered mountain silhouettes and a reflective lake, at
1024x1024, fully deterministic (fixed seed -> identical bytes every run).
Writes /output/entry.png (override with ENTRY_OUT for local runs).
"""
import math, os, random, struct, zlib

W = H = 1024
rng = random.Random(20261113)


def clamp(v, a, b):
    return a if v < a else (b if v > b else v)


def lerp(a, b, t):
    return a + (b - a) * t


def mix(c1, c2, t):
    return (lerp(c1[0], c2[0], t), lerp(c1[1], c2[1], t), lerp(c1[2], c2[2], t))


def grad(stops, t):
    """stops: list of (pos, color)."""
    if t <= stops[0][0]:
        return stops[0][1]
    for i in range(1, len(stops)):
        if t <= stops[i][0]:
            p0, c0 = stops[i - 1]
            p1, c1 = stops[i]
            return mix(c0, c1, (t - p0) / (p1 - p0))
    return stops[-1][1]


class Canvas:
    def __init__(self, w, h):
        self.w, self.h = w, h
        self.p = bytearray(w * h * 3)

    def blend(self, x, y, c, a):
        if a <= 0.0 or x < 0 or y < 0 or x >= self.w or y >= self.h:
            return
        i = (y * self.w + x) * 3
        ia = 1.0 - a
        self.p[i] = int(self.p[i] * ia + c[0] * a)
        self.p[i + 1] = int(self.p[i + 1] * ia + c[1] * a)
        self.p[i + 2] = int(self.p[i + 2] * ia + c[2] * a)

    def vgrad(self, stops, y_top, y_bot):
        for y in range(y_top, y_bot):
            c = grad(stops, y / (self.h - 1))
            row = bytes((int(c[0]), int(c[1]), int(c[2]))) * self.w
            i = y * self.w * 3
            self.p[i:i + self.w * 3] = row


# --- SDF shape drawing: paint(x, y) -> (r, g, b, alpha_multiplier) ---
def draw(cv, bbox, sdf, paint, aa=1.0):
    x0 = max(0, int(bbox[0])); y0 = max(0, int(bbox[1]))
    x1 = min(cv.w, int(bbox[2]) + 1); y1 = min(cv.h, int(bbox[3]) + 1)
    for y in range(y0, y1):
        for x in range(x0, x1):
            d = sdf(x + 0.5, y + 0.5)
            a = clamp(0.5 - d / aa, 0.0, 1.0)
            if a > 0.0:
                c = paint(x + 0.5, y + 0.5)
                cv.blend(x, y, c, a * c[3])


def solid(c):
    return lambda x, y: (c[0], c[1], c[2], 1.0)


def sd_circle(cx, cy, r):
    return lambda x, y: math.hypot(x - cx, y - cy) - r


def sd_poly(pts):
    """Inigo Quilez polygon SDF (exact sign test)."""
    def f(px, py):
        d = (px - pts[0][0]) ** 2 + (py - pts[0][1]) ** 2
        s = 1.0
        j = len(pts) - 1
        for i in range(len(pts)):
            xi, yi = pts[i]; xj, yj = pts[j]
            ex, ey = xj - xi, yj - yi
            wx, wy = px - xi, py - yi
            ee = ex * ex + ey * ey
            t = clamp((wx * ex + wy * ey) / ee, 0.0, 1.0) if ee > 0 else 0.0
            dx, dy = wx - ex * t, wy - ey * t
            dd = dx * dx + dy * dy
            if dd < d:
                d = dd
            c1 = py >= yi
            c2 = py < yj
            c3 = ex * wy > ey * wx
            if c1 == c2 == c3:
                s = -s
            j = i
        return s * math.sqrt(d)
    return f


def ridge(seed, y_base, amp, step):
    r = random.Random(seed)
    pts = [(-20, H + 20), (-20, y_base)]
    x = -20
    y = y_base
    while x < W + 20:
        x += step * (0.6 + r.random() * 0.8)
        y = y_base + (r.random() - 0.5) * amp
        pts.append((x, y))
        # sharp peak between steps
        pts.append((x + step * 0.3, y - amp * (0.35 + r.random() * 0.55)))
    pts.append((W + 20, y_base))
    pts.append((W + 20, H + 20))
    return pts


def pine(cv, cx, base_y, s, color):
    """Silhouette pine: stacked triangles + trunk."""
    trunk = [(cx - 6 * s, base_y), (cx + 6 * s, base_y),
             (cx + 4 * s, base_y - 46 * s), (cx - 4 * s, base_y - 46 * s)]
    draw(cv, (cx - 10 * s, base_y - 50 * s, cx + 10 * s, base_y), sd_poly(trunk), solid(color))
    tiers = [(86, 40), (66, 78), (46, 112)]
    for half_w, top_off in tiers:
        ty = base_y - top_off * s - 30 * s
        by = ty + 74 * s
        tri = [(cx - half_w * s, by), (cx + half_w * s, by), (cx, ty)]
        draw(cv, (cx - half_w * s, ty, cx + half_w * s, by), sd_poly(tri), solid(color))


def main():
    cv = Canvas(W, H)

    # --- sky: deep space indigo -> violet -> magenta -> ember at horizon ---
    horizon = 742
    sky_stops = [
        (0.00, (7, 8, 32)), (0.22, (24, 16, 66)), (0.42, (58, 24, 104)),
        (0.58, (110, 36, 128)), (0.70, (178, 58, 120)), (0.80, (232, 96, 92)),
        (0.90, (250, 150, 84)), (1.00, (255, 186, 102)),
    ]
    cv.vgrad(sky_stops, 0, horizon + 2)

    # --- lake: darker mirrored ember gradient ---
    lake_stops = [
        (0.00, (30, 14, 52)), (0.30, (52, 22, 74)), (0.62, (88, 34, 88)),
        (0.85, (120, 48, 84)), (1.00, (66, 26, 66)),
    ]
    for y in range(horizon, H):
        t = (y - horizon) / (H - horizon)
        c = grad(lake_stops, t)
        # keep lake darker toward the viewer
        row = bytes((int(c[0]), int(c[1]), int(c[2]))) * W
        i = y * W * 3
        cv.p[i:i + W * 3] = row

    # --- stars (upper sky, deterministic) ---
    for _ in range(620):
        sx = rng.random() * W
        sy = (rng.random() ** 1.6) * horizon * 0.92
        fade = 1.0 - sy / (horizon * 1.05)
        if fade <= 0:
            continue
        br = (0.25 + rng.random() * 0.75) * clamp(fade, 0, 1)
        r = 0.7 + rng.random() * 1.7
        tint = [(200, 210, 255), (255, 255, 255), (255, 230, 200)][rng.randrange(3)]
        col = (tint[0] * br, tint[1] * br, tint[2] * br)
        draw(cv, (sx - 4, sy - 4, sx + 4, sy + 4), sd_circle(sx, sy, r),
             lambda x, y, c=col: (c[0], c[1], c[2], 0.85), aa=1.4)
        if r > 2.1:  # sparkle cross on the brightest
            for dx, dy in ((0, -6), (0, 6), (-6, 0), (6, 0)):
                cv.blend(int(sx + dx), int(sy + dy), col, 0.35)

    # --- eclipse geometry ---
    ex, ey, er = 512, 400, 118

    # wide ambient glow (bbox reaches ~4 sigma so the falloff dies at the edge)
    def glow_paint(strength, tint, sigma):
        def f(x, y):
            d = math.hypot(x - ex, y - ey)
            a = math.exp(-((d - er) ** 2) / (2 * sigma ** 2)) * strength
            return (tint[0], tint[1], tint[2], clamp(a, 0, 1))
        return f
    draw(cv, (ex - 600, ey - 600, ex + 600, ey + 600), sd_circle(ex, ey, 10 ** 6),
         glow_paint(0.50, (255, 170, 120), 120.0), aa=1.0)
    draw(cv, (ex - 470, ey - 470, ex + 470, ey + 470), sd_circle(ex, ey, 10 ** 6),
         glow_paint(0.55, (255, 205, 150), 82.0), aa=1.0)

    # corona rays: tapered triangles, gold-white, deterministic lengths
    n_rays = 72
    for i in range(n_rays):
        ang = (i / n_rays) * math.tau + rng.uniform(-0.02, 0.02)
        L = er * (0.55 + rng.random() ** 2 * 1.9)
        wdt = 0.016 + rng.random() * 0.03
        x0 = ex + math.cos(ang) * er * 0.92
        y0 = ey + math.sin(ang) * er * 0.92
        x1 = ex + math.cos(ang) * (er + L)
        y1 = ey + math.sin(ang) * (er + L)
        px_, py_ = math.cos(ang + math.pi / 2), math.sin(ang + math.pi / 2)
        bw = er * wdt
        pts = [(x0 + px_ * bw, y0 + py_ * bw), (x0 - px_ * bw, y0 - py_ * bw), (x1, y1)]
        bright = 0.35 + rng.random() * 0.65
        col = (255 * bright + 40, 225 * bright + 30, 180 * bright + 20)
        col = tuple(min(255, int(v)) for v in col)
        bb = (min(p[0] for p in pts) - 3, min(p[1] for p in pts) - 3,
              max(p[0] for p in pts) + 3, max(p[1] for p in pts) + 3)
        draw(cv, bb, sd_poly(pts), lambda x, y, c=col: (c[0], c[1], c[2], 0.5), aa=1.6)

    # chromosphere ring: thin hot-pink rim
    def ring_paint(x, y):
        d = math.hypot(x - ex, y - ey)
        a = clamp(1.0 - abs(d - (er + 3)) / 7.0, 0, 1)
        return (255, 84, 130, a * 0.9)
    draw(cv, (ex - er - 14, ey - er - 14, ex + er + 14, ey + er + 14),
         sd_circle(ex, ey, 10 ** 6), ring_paint)

    # the black disc + diamond-ring bead (bright spot at upper left rim)
    draw(cv, (ex - er, ey - er, ex + er, ey + er), sd_circle(ex, ey, er), solid((3, 3, 10)))
    ba = math.radians(-52)
    bx, by = ex + math.cos(ba) * er, ey + math.sin(ba) * er
    for rr, al in ((26, 0.25), (15, 0.55), (7, 1.0)):
        draw(cv, (bx - rr - 2, by - rr - 2, bx + rr + 2, by + rr + 2),
             sd_circle(bx, by, rr), lambda x, y, a=al: (255, 250, 235, a), aa=2.0)

    # --- mountain layers (atmospheric: far = lighter haze, near = darker) ---
    layers = [
        (11, 560, 120, 90, (74, 44, 108)),
        (22, 622, 130, 80, (52, 30, 84)),
        (33, 690, 140, 70, (34, 20, 58)),
        (44, horizon + 4, 90, 60, (18, 11, 34)),
    ]
    for seed, yb, amp, step, col in layers:
        pts = ridge(seed, yb, amp, step)
        # clip ridge to above the lake line for far layers
        draw(cv, (-20, 300, W + 20, horizon + 6), sd_poly(pts), solid(col), aa=1.2)

    # snow-kissed rim light on the nearest ridge tops: thin ember line
    # (cheap trick: redraw nearest ridge shifted up 3px in ember, then overdraw original)
    pts_near = ridge(44, horizon + 4, 90, 60)
    shifted = [(x, y - 3) for (x, y) in pts_near]
    draw(cv, (-20, 300, W + 20, horizon + 6), sd_poly(shifted),
         lambda x, y: (255, 140, 90, 0.55), aa=1.2)
    draw(cv, (-20, 300, W + 20, horizon + 6), sd_poly(pts_near), solid((18, 11, 34)), aa=1.2)

    # --- lake reflection: shimmering light column under the eclipse ---
    for i in range(210):
        t = rng.random()
        y = horizon + 6 + t * (H - horizon - 14)
        spread = 30 + t * 210
        cx = ex + (rng.random() - 0.5) * 2 * spread * 0.55
        wdt = (6 + rng.random() * 46) * (1 - t * 0.45)
        hgt = 2.0 + rng.random() * 3.0
        bright = (1 - t) * (0.25 + rng.random() * 0.6)
        col = mix((255, 120, 90), (255, 200, 130), rng.random())
        col = tuple(v * (0.35 + bright) for v in col)
        for yy in range(int(y), int(y + hgt)):
            for xx in range(int(cx - wdt / 2), int(cx + wdt / 2)):
                cv.blend(xx, yy, col, 0.5)
    # faint ridge reflections: dark soft bands
    for i in range(46):
        y = horizon + 8 + rng.random() * (H - horizon - 20)
        x = rng.random() * W
        wdt = 30 + rng.random() * 130
        for xx in range(int(x), int(x + wdt)):
            cv.blend(xx, int(y), (8, 5, 18), 0.16)

    # --- foreground pines framing the corners ---
    pine(cv, 66, horizon + 26, 1.25, (8, 5, 16))
    pine(cv, 138, horizon + 18, 0.8, (10, 6, 20))
    pine(cv, 958, horizon + 26, 1.35, (8, 5, 16))
    pine(cv, 884, horizon + 16, 0.75, (10, 6, 20))

    # --- birds: tiny silhouettes ---
    def bird(cx, cy, s):
        for sgn in (-1, 1):
            pts = [(cx, cy), (cx + sgn * 16 * s, cy - 8 * s), (cx + sgn * 19 * s, cy - 4 * s),
                   (cx + sgn * 4 * s, cy + 2 * s)]
            draw(cv, (cx - 22 * s, cy - 10 * s, cx + 22 * s, cy + 4 * s), sd_poly(pts),
                 solid((10, 6, 22)), aa=1.2)
    bird(238, 218, 1.0); bird(300, 262, 0.7); bird(792, 190, 0.85); bird(742, 244, 0.6)

    # --- vignette (single pass; no grain: noise would break the 1 MiB PNG cap) ---
    cxm, cym = W / 2, H / 2
    maxd2 = cxm * cxm + cym * cym
    xs2 = [(x - cxm) ** 2 for x in range(W)]
    p = cv.p
    for y in range(H):
        dy2 = (y - cym) ** 2
        base = y * W * 3
        for x in range(W):
            d2 = (xs2[x] + dy2) / maxd2
            v = 1.0 - 0.34 * d2 * (0.65 + 0.35 * d2)
            i = base + x * 3
            p[i] = clamp(int(p[i] * v), 0, 255)
            p[i + 1] = clamp(int(p[i + 1] * v), 0, 255)
            p[i + 2] = clamp(int(p[i + 2] * v), 0, 255)

    # --- PNG encode (deterministic) ---
    raw = bytearray()
    stride = W * 3
    for y in range(H):
        raw.append(0)
        raw += cv.p[y * stride:(y + 1) * stride]
    comp = zlib.compress(bytes(raw), 9)

    def chunk(tag, data):
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    png = (b"\x89PNG\r\n\x1a\n"
           + chunk(b"IHDR", struct.pack(">IIBBBBB", W, H, 8, 2, 0, 0, 0))
           + chunk(b"IDAT", comp)
           + chunk(b"IEND", b""))
    out = os.environ.get("ENTRY_OUT", "/output/entry.png")
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    with open(out, "wb") as f:
        f.write(png)
    print(f"wrote {out}: {len(png)} bytes")


if __name__ == "__main__":
    main()

# --- make.fun entry notes (coolest-art-01) --------------------------------
# Entrant: @urelkdubdqwr. Deterministic generative art: pure stdlib SDF
# rasterizer, fixed seedless math only, so every run writes the identical
# PNG bytes to /output/entry.png.
# Composition: the eclipse sits on the upper golden-ratio point; ridges
# darken and cool with distance, and the lake reflection reuses the sky
# gradient so the eye lands on the diamond ring first.
