import logging
import math
import random
import re
import socket
import subprocess
import sys
import threading
import time

import pygame
from wp_app_state import WpAppState


# the idle screen: day, time and date, and a line saying what's wrong when not connected, over recently shown album art
class WpClockDisplay:
    def __init__(self, config, appStatus, parent, artCache=None):
        self.wpStatus = appStatus
        self.parent = parent
        self.screenSize = parent.screenSize
        self.timeFont = parent.getFontForElement('clock_time')
        self.dayFont = parent.getFontForElement('clock_day')
        self.dateFont = parent.getFontForElement('clock_date')
        self.problemFont = parent.getFontForElement('clock_problem')
        self.background = config.getSubkey('layout', 'clock_background_color', [0, 0, 0])
        self.timeColor = config.getSubkey('layout', 'clock_time_color', [235, 235, 235])
        self.textColor = config.getSubkey('layout', 'clock_text_color', [170, 170, 170])
        self.problemColor = config.getSubkey('layout', 'clock_problem_color', [240, 170, 60])
        self.centerY = config.getSubkey('layout', 'clock_time_y', 350)
        self.gap = config.getSubkey('layout', 'clock_gap', 6)
        self.problemY = config.getSubkey('layout', 'clock_problem_y', 590)
        self.surfaces = {}      # text -> rendered surface, since only the minute changes
        # the Wi-Fi network, frequency and address, small at the bottom, for seeing when a display has moved
        self.networkFont = parent.getFontForElement('clock_network')
        self.networkColor = config.getSubkey('layout', 'clock_network_color', [110, 110, 110])
        self.networkY = config.getSubkey('layout', 'clock_network_y', 640)
        self.networkRefresh = config.getSubkey('layout', 'clock_network_refresh', 30)
        self.network = ''
        self.networkCheckedAt = None
        self.networkChecking = False

        # the art behind it: a different recent cover every clock_art_interval seconds, crossfading over
        # clock_art_fade. the text gets a shadow there, and goes dark on a light cover
        self.artCache = artCache
        self.artInterval = config.getSubkey('layout', 'clock_art_interval', 60)
        self.artFade = config.getSubkey('layout', 'clock_art_fade', 2.0)
        self.artDim = config.getSubkey('layout', 'clock_art_dim', 50)      # 0-255 of black over the art
        self.artDeepen = config.getSubkey('layout', 'clock_art_deepen', 255)    # 0-255, see prepareArt
        self.lightThreshold = config.getSubkey('layout', 'clock_art_light_threshold', 160)
        self.shadowOffset = config.getSubkey('layout', 'clock_shadow_offset', 2)
        self.shadowBlur = config.getSubkey('layout', 'clock_shadow_blur', 6)
        self.shadowStrength = config.getSubkey('layout', 'clock_shadow_strength', 3)
        self.shadowColor = config.getSubkey('layout', 'clock_shadow_color', [0, 0, 0])
        self.artTextColor = config.getSubkey('layout', 'clock_art_text_color', [220, 220, 220])     # day and date over art
        self.darkTimeColor = config.getSubkey('layout', 'clock_dark_time_color', [20, 20, 20])
        self.darkTextColor = config.getSubkey('layout', 'clock_dark_text_color', [45, 45, 45])
        self.darkShadowColor = config.getSubkey('layout', 'clock_dark_shadow_color', [255, 255, 255])
        self.darkProblemColor = config.getSubkey('layout', 'clock_dark_problem_color', [150, 70, 0])
        self.art = None             # (surface, light, path) on screen
        self.previousArt = None     # the one it's fading from
        self.nextArt = None         # loaded ahead on its own thread
        self.artShownAt = 0.0
        self.artLoading = False
        self.artQueue = []

    def text(self, font, text, color):
        key = (id(font), text, tuple(color))
        if key not in self.surfaces:
            if len(self.surfaces) > 50:
                self.surfaces.clear()
            self.surfaces[key] = font.render(text, True, color)
        return self.surfaces[key]

    # a soft dark halo, the text blurred: it holds the text apart from busy art where a hard copy doesn't.
    # drawn clock_shadow_strength times over itself to make it denser
    def shadow(self, font, text, color):
        key = ('shadow', id(font), text, tuple(color))
        if key not in self.surfaces:
            textSurf = font.render(text, True, color)
            pad = self.shadowBlur * 2
            surf = pygame.Surface((textSurf.get_width() + pad * 2, textSurf.get_height() + pad * 2), pygame.SRCALPHA)
            # see-through pixels of the shadow's own colour, not black, or the blur greys a white halo
            surf.fill((*color[:3], 0))
            surf.blit(textSurf, (pad, pad))
            if self.shadowBlur > 0:
                surf = pygame.transform.gaussian_blur(surf, self.shadowBlur)
            dense = pygame.Surface(surf.get_size(), pygame.SRCALPHA)
            for _ in range(max(1, self.shadowStrength)):
                dense.blit(surf, (0, 0))
            self.surfaces[key] = (dense, pad)
        return self.surfaces[key]

    # what's keeping it from connecting, from the Sonos thread's status ("Kitchen device not found · retrying in 4s")
    def problem(self):
        if self.wpStatus.appState == WpAppState.CONNECTED:
            return ''
        if self.wpStatus.noNetwork:
            return 'No network'
        reason = (self.wpStatus.status or '').split(' · ')[0]
        return reason or 'Not connected'

    def render(self, screen):
        light = self.renderArt(screen)
        shadow = self.art is not None
        timeColor, textColor, problemColor, shadowColor = (
            (self.darkTimeColor, self.darkTextColor, self.darkProblemColor, self.darkShadowColor) if light else
            (self.timeColor, self.artTextColor if shadow else self.textColor, self.problemColor, self.shadowColor))
        now = time.localtime()
        clock = f"{int(time.strftime('%I', now))}:{now.tm_min:02d}"
        day = time.strftime('%A', now)
        date = f"{time.strftime('%b', now)} {now.tm_mday}"

        def draw(font, text, color, pos, offset):
            if shadow:
                surf, pad = self.shadow(font, text, shadowColor)
                screen.blit(surf, (pos[0] + offset - pad, pos[1] + offset - pad))
            screen.blit(self.text(font, text, color), pos)

        timeSurf = self.text(self.timeFont, clock, timeColor)
        # the digits' own height, not the font's line height, so the day and date sit close to them
        timeRect = timeSurf.get_bounding_rect()
        top = self.centerY - timeRect.height // 2
        draw(self.timeFont, clock, timeColor,
             (self.screenSize // 2 - timeRect.width // 2 - timeRect.x, top - timeRect.y), self.shadowOffset)

        small = max(1, self.shadowOffset - 1)
        dayRect = self.text(self.dayFont, day, textColor).get_bounding_rect()
        draw(self.dayFont, day, textColor, (self.screenSize // 2 - dayRect.width // 2 - dayRect.x,
                                            top - self.gap - dayRect.height - dayRect.y - self.gap * 3), small)

        dateRect = self.text(self.dateFont, date, textColor).get_bounding_rect()
        draw(self.dateFont, date, textColor, (self.screenSize // 2 - dateRect.width // 2 - dateRect.x,
                                              top + timeRect.height + self.gap * 4 - dateRect.y), small)

        problem = self.problem()
        if problem:
            rect = self.text(self.problemFont, problem, problemColor).get_rect(center=(self.screenSize // 2, self.problemY))
            draw(self.problemFont, problem, problemColor, rect.topleft, small)

        self.checkNetwork()
        if self.network:
            color = textColor if shadow else self.networkColor
            rect = self.text(self.networkFont, self.network, color).get_rect(center=(self.screenSize // 2, self.networkY))
            draw(self.networkFont, self.network, color, rect.topleft, 1)

    # the background, art or plain; returns whether what's behind the text is light
    def renderArt(self, screen):
        screen.fill(self.background)
        self.updateArt()
        if self.art is None:
            return False
        sinceShown = time.monotonic() - self.artShownAt
        fade = min(1.0, sinceShown / self.artFade) if self.artFade > 0 else 1.0
        if self.previousArt is not None and fade < 1.0:
            screen.blit(self.previousArt[0], (0, 0))
        surf = self.art[0]
        surf.set_alpha(int(255 * fade))
        screen.blit(surf, (0, 0))
        surf.set_alpha(None)
        # the text turns over halfway through the fade
        if fade < 0.5:
            return self.previousArt[1] if self.previousArt is not None else False
        return self.art[1]

    def updateArt(self):
        if self.artCache is None:
            return
        if self.nextArt is None and not self.artLoading:
            self.loadNextArt()
        due = self.art is None or time.monotonic() - self.artShownAt >= self.artInterval
        if due and self.nextArt is not None:
            self.previousArt, self.art, self.nextArt = self.art, self.nextArt, None
            self.artShownAt = time.monotonic()

    # on to the next cover as soon as it's loaded
    def skipArt(self):
        self.artShownAt = time.monotonic() - self.artInterval

    # the covers in a shuffled order, each once before any repeats; loading and scaling is slow on a Pi
    def loadNextArt(self):
        if not self.artQueue:
            self.artQueue = self.artCache.paths()
            random.shuffle(self.artQueue)
            # not the one on screen again straight away
            if len(self.artQueue) > 1 and self.art is not None and self.artQueue[0] == self.art[2]:
                self.artQueue.append(self.artQueue.pop(0))
        if not self.artQueue:
            return
        path = self.artQueue.pop(0)
        self.artLoading = True

        def work():
            try:
                self.nextArt = self.prepareArt(path)
            except Exception as e:
                logging.debug(f"Clock: couldn't load art {path}: {e}")
            finally:
                self.artLoading = False
        threading.Thread(target=work, daemon=True, name='clock art').start()

    def prepareArt(self, path):
        size = (self.screenSize, self.screenSize)
        image = pygame.image.load(path)
        # to 32 bit first: smoothscale won't take a paletted PNG. and no alpha channel, so set_alpha fades the
        # whole cover (see the clock layer in wp_display)
        full = pygame.Surface(image.get_size(), 0, 32)
        full.blit(image, (0, 0))
        surf = pygame.transform.smoothscale(full, size)
        # how light the cover is where the text goes. a light one gets dark text and is left as it is; the rest
        # are darkened for the light text
        rect = pygame.Rect(self.screenSize // 6, self.screenSize // 4, self.screenSize * 2 // 3, self.screenSize // 2)
        r, g, b = pygame.transform.average_color(surf, rect)[:3]
        light = 0.299 * r + 0.587 * g + 0.114 * b > self.lightThreshold
        if light:
            return (surf, light, path)
        # darkened by multiplying the cover by itself: darks and mids drop a lot, bright colours stay bright, so
        # colours get richer where a black overlay makes them muddy. clock_art_deepen is how much of that to mix in
        if self.artDeepen > 0:
            deep = surf.copy()
            deep.blit(surf, (0, 0), special_flags=pygame.BLEND_RGB_MULT)
            deep.set_alpha(self.artDeepen)
            surf.blit(deep, (0, 0))
        if self.artDim > 0:
            shade = pygame.Surface(size, 0, 32)
            shade.set_alpha(self.artDim)
            surf.blit(shade, (0, 0))
        return (surf, light, path)

    # looked up on its own thread every networkRefresh seconds while the clock is up, since iw can take a moment
    def checkNetwork(self):
        now = time.monotonic()
        if self.networkChecking or (self.networkCheckedAt is not None and now - self.networkCheckedAt < self.networkRefresh):
            return
        self.networkChecking = True

        def work():
            try:
                self.network = currentNetwork()
            finally:
                self.networkCheckedAt = time.monotonic()
                self.networkChecking = False
        threading.Thread(target=work, daemon=True, name='clock network').start()


# "Repeater · 5200 MHz · 192.168.5.35": the Wi-Fi network and frequency where the system says (the Pi; macOS hides
# the network name from apps), and this machine's address, from the route a packet would take (nothing is sent)
def currentNetwork():
    address = ''
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(('8.8.8.8', 80))
        address = sock.getsockname()[0]
    except OSError:
        pass
    finally:
        sock.close()
    if not address or address.startswith(('0.', '127.', '169.254.')):
        return 'No network'

    parts = []
    if sys.platform.startswith('linux'):
        try:
            link = subprocess.run(['iw', 'dev', 'wlan0', 'link'], capture_output=True, text=True, timeout=3).stdout
            ssid = re.search(r'SSID: (.+)', link)
            freq = re.search(r'freq: (\d+)', link)
            if ssid:
                parts.append(ssid.group(1).strip())
            if freq:
                parts.append(f"{freq.group(1)} MHz")
        except (OSError, subprocess.SubprocessError):
            pass
    parts.append(address)
    return ' · '.join(parts)


# a small clock face for the button that opens clock mode, drawn so no asset is needed
def clockIcon(size, color=(255, 255, 255)):
    scale = 4       # drawn large and scaled down, for smooth edges
    big = size * scale
    surf = pygame.Surface((big, big), pygame.SRCALPHA)
    center = (big // 2, big // 2)
    radius = big // 2 - 2 * scale
    pygame.draw.circle(surf, color, center, radius, width=3 * scale)
    for angle, length in ((-90, 0.55), (0, 0.4)):      # minute hand up, hour hand to three
        rad = math.radians(angle)
        end = (center[0] + math.cos(rad) * radius * length, center[1] + math.sin(rad) * radius * length)
        pygame.draw.line(surf, color, center, end, 3 * scale)
    return pygame.transform.smoothscale(surf, (size, size))
