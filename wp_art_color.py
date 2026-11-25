import colorsys
import math

import pygame


# a dark version of a cover's most vivid colour, for tinting the band over it. the cover is shrunk to a few
# hundred pixels, which are sorted into hue slices, each counting by its saturation cubed (so the vivid pixels
# far outweigh the dull ones) times its brightness. in the heaviest slice the most saturated quarter of the
# pixels are averaged and pushed to full saturation (scaled by `saturation`).
# that colour is then set to `lightness` (0-100) in OKLCH, where equal lightness looks equally bright whatever
# the hue, keeping its hue and as much of its colourfulness as fits at that lightness.
# a cover with no real colour gives black
def bandColor(surface, lightness=25, saturation=1.0, size=24):
    small = pygame.Surface((size, size), 0, 32)
    small.blit(pygame.transform.smoothscale(surface, (size, size)), (0, 0))
    slices = 12
    weights = [0.0] * slices
    members = [[] for _ in range(slices)]
    for y in range(size):
        for x in range(size):
            r, g, b = small.get_at((x, y))[:3]
            h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
            if s < 0.25 or v < 0.2:
                continue
            i = int(h * slices) % slices
            weights[i] += s ** 3 * v
            members[i].append((s, r, g, b))
    best = max(range(slices), key=lambda i: weights[i])
    # a few stray coloured pixels on a grey cover aren't enough to tint it
    if len(members[best]) < size * size * 0.03:
        return (0, 0, 0)
    vivid = sorted(members[best], reverse=True)[:max(1, len(members[best]) // 4)]
    r, g, b = (sum(m[c] for m in vivid) / len(vivid) for c in (1, 2, 3))
    h, _, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
    r, g, b = colorsys.hsv_to_rgb(h, min(1.0, saturation), v)
    return atLightness((r * 255, g * 255, b * 255), lightness / 100)


# the colour at OKLCH lightness L (0-1): same hue, its chroma cut down only as far as the screen can show
def atLightness(rgb, L):
    _, a, b = toOklab(*rgb)
    chroma, hue = math.hypot(a, b), math.atan2(b, a)
    low, high = 0.0, chroma
    best = fromOklab(L, 0.0, 0.0)
    for _ in range(20):
        c = (low + high) / 2
        color = fromOklab(L, c * math.cos(hue), c * math.sin(hue))
        if color is None:
            high = c
        else:
            best, low = color, c
    color = fromOklab(L, chroma * math.cos(hue), chroma * math.sin(hue))
    return color or best


def toLinear(c):
    c /= 255
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def fromLinear(c):
    return 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055


# OKLab, Björn Ottosson's
def toOklab(r, g, b):
    r, g, b = toLinear(r), toLinear(g), toLinear(b)
    l = (0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b) ** (1 / 3)
    m = (0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b) ** (1 / 3)
    s = (0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b) ** (1 / 3)
    return (0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s,
            1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s,
            0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s)


# None when the colour is outside what the screen can show
def fromOklab(L, a, b):
    l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3
    m = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3
    s = (L - 0.0894841775 * a - 1.2914855480 * b) ** 3
    rgb = (4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
           -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
           -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s)
    if any(c < -0.0001 or c > 1.0001 for c in rgb):
        return None
    return tuple(int(round(max(0.0, min(1.0, fromLinear(max(0.0, c)))) * 255)) for c in rgb)
