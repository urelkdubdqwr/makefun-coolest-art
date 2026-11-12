#!/usr/bin/env python3
"""SYNTHWAVE SUNSET — generative art for make.fun 'Make the coolest art' (v2).

One bold focal subject: a giant striped gradient sun sinking behind a
silhouette ridge over a glowing perspective grid. Pure Python 3 stdlib,
fully deterministic (fixed constants and fixed-seed placement only), writes
/output/entry.png (override with ENTRY_OUT for local runs).
"""
import math, os, random, struct, zlib

W = H = 1024


def clamp(v, a, b):
    return a if v < a else (b if v > b else v)


def lerp(a, b, t):
    return a + (b - a) * t


def mix(c1, c2, t):
    return (lerp(c1[0], c2[0], t), lerp(c1[1], c2[1], t), lerp(c1[2], c2[2], t))


def grad(stops, t):
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

    def fill_rows(self, stops, y_top, y_bot):
        for y in range(y_top, y_bot):
            t = (y - y_top) / max(1, (y_bot - y_top - 1))
            c = grad(stops, t)
            row = bytes((int(c[0]), int(c[1]), int(c[2]))) * self.w
            i = y * self.w * 3
            self.p[i:i + self.w * 3] = row


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


def solid(c, a=1.0):
    return lambda x, y: (c[0], c[1], c[2], a)


def sd_circle(cx, cy, r):
    return lambda x, y: math.hypot(x - cx, y - cy) - r


def sd_capsule(x1, y1, x2, y2, r):
    def f(px, py):
        ex, ey = x2 - x1, y2 - y1
        wx, wy = px - x1, py - y1
        t = clamp((wx * ex + wy * ey) / (ex * ex + ey * ey), 0.0, 1.0)
        return math.hypot(wx - ex * t, wy - ey * t) - r
    return f


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
        pts.append((x + step * 0.3, y - amp * (0.35 + r.random() * 0.55)))
    pts.append((W + 20, y_base))
    pts.append((W + 20, H + 20))
    return pts


def main():
    cv = Canvas(W, H)
    horizon = 688
    SX, SY, SR = 512, 452, 302  # the sun

    # --- sky: near-black violet up top -> deep magenta at the horizon ---
    cv.vgrad([(0.00, (10, 4, 32)), (0.35, (32, 8, 62)), (0.55, (66, 16, 96)),
              (0.68, (110, 26, 116))], 0, horizon + 2)

    # --- sparse stars, upper sky only ---
    rng = random.Random(4242)
    for _ in range(170):
        sx = rng.random() * W
        sy = (rng.random() ** 1.5) * 400
        br = 0.35 + rng.random() * 0.65
        r = 0.8 + rng.random() * 1.5
        col = (210 * br + 30, 200 * br + 30, 255 * br)
        draw(cv, (sx - 4, sy - 4, sx + 4, sy + 4), sd_circle(sx, sy, r),
             solid(tuple(min(255, int(v)) for v in col), 0.9), aa=1.4)

    # --- sun glow: warm halo hugging the disc ---
    def glow(x, y):
        d = math.hypot(x - SX, y - SY) - SR
        a = math.exp(-(max(d, 0.0) ** 2) / (2 * 64.0 ** 2)) * 0.55
        return (255, 110, 130, clamp(a, 0.0, 1.0))
    draw(cv, (SX - 470, SY - 470, SX + 470, horizon), sd_circle(SX, SY, 10 ** 6),
         glow, aa=1.0)

    # --- THE SUN: one giant gradient disc, sliced in its lower half ---
    gaps = []  # (y_center_offset_from_sun_center, half_thickness) in px
    for off, half in ((34, 3.2), (78, 4.6), (126, 6.4), (178, 8.8), (234, 12.0)):
        gaps.append((SY + off, half))
    sun_stops = [(0.00, (255, 240, 170)), (0.38, (255, 186, 74)),
                 (0.66, (255, 110, 84)), (0.86, (255, 64, 128)),
                 (1.00, (244, 44, 158))]

    def sun_paint(x, y):
        t = (y - (SY - SR)) / (2 * SR)
        c = grad(sun_stops, clamp(t, 0.0, 1.0))
        a = 1.0
        for gy, half in gaps:
            dd = abs(y - gy) - half
            if dd < 2.0:
                a = min(a, clamp(0.5 + dd / 2.0, 0.0, 1.0))
        return (c[0], c[1], c[2], a)
    draw(cv, (SX - SR, SY - SR, SX + SR, SY + SR), sd_circle(SX, SY, SR),
         sun_paint, aa=1.6)

    # --- floor base: dark violet; painted over the sun's lower segment
    # so the disc sinks cleanly behind the horizon line ---
    cv.fill_rows([(0.0, (24, 6, 44)), (1.0, (8, 2, 18))], horizon, H)

    # --- silhouette ridges crossing in front of the sun ---
    far = ridge(7, horizon - 6, 74, 120)
    draw(cv, (-20, 380, W + 20, horizon + 4), sd_poly(far), solid((38, 12, 58)), aa=1.2)
    near = ridge(19, horizon + 2, 66, 90)
    draw(cv, (-20, 420, W + 20, horizon + 4), sd_poly(near), solid((13, 4, 26)), aa=1.2)

    # --- perspective grid on the floor (hot pink, glow + core) ---
    grid_col = (255, 45, 150)
    # verticals fanning from the vanishing point
    for k in range(-7, 8):
        xb = 512 + k * 168
        draw(cv, (min(512, xb) - 10, horizon, max(512, xb) + 10, H),
             sd_capsule(512, horizon, xb, H, 7.0), solid(grid_col, 0.16), aa=3.0)
        draw(cv, (min(512, xb) - 5, horizon, max(512, xb) + 5, H),
             sd_capsule(512, horizon, xb, H, 1.8), solid(grid_col, 0.85), aa=1.4)
    # horizontals rushing toward the viewer
    for i in range(1, 10):
        t = i / 9.0
        y = horizon + (H - horizon) * t ** 2.1
        thick = 1.6 + t * 4.5
        draw(cv, (0, y - thick * 3, W, y + thick * 3),
             sd_capsule(0, y, W, y, thick * 2.6), solid(grid_col, 0.14), aa=3.0)
        draw(cv, (0, y - thick, W, y + thick),
             sd_capsule(0, y, W, y, thick * 0.55), solid(grid_col, 0.9), aa=1.4)
    # horizon light line
    draw(cv, (0, horizon - 4, W, horizon + 4), sd_capsule(0, horizon, W, horizon, 2.6),
         solid((255, 120, 190), 0.55), aa=1.6)

    # --- gentle vignette ---
    cxm, cym = W / 2, H / 2
    maxd2 = cxm * cxm + cym * cym
    xs2 = [(x - cxm) ** 2 for x in range(W)]
    p = cv.p
    for y in range(H):
        dy2 = (y - cym) ** 2
        base = y * W * 3
        for x in range(W):
            d2 = (xs2[x] + dy2) / maxd2
            v = 1.0 - 0.30 * d2 * (0.65 + 0.35 * d2)
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

# --- make.fun entry notes (coolest-art-01, v2) ----------------------------
# Entrant: @urelkdubdqwr. Deterministic generative art: pure stdlib SDF
# rasterizer, fixed math only, identical PNG bytes on every run.
# Duel design: one focal shape (the striped sun), a single horizon line,
# and a grid that pulls the eye to the center — nothing else competes.
