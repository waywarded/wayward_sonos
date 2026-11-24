import math
import re
import socket
import subprocess
import sys
import threading
import time

import pygame
from wp_app_state import WpAppState


# the idle screen: day, time and date, and a line saying what's wrong when not connected
class WpClockDisplay:
    def __init__(self, config, appStatus, parent):
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

    def text(self, font, text, color):
        key = (id(font), text, tuple(color))
        if key not in self.surfaces:
            if len(self.surfaces) > 50:
                self.surfaces.clear()
            self.surfaces[key] = font.render(text, True, color)
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
        screen.fill(self.background)
        now = time.localtime()
        clock = f"{int(time.strftime('%I', now))}:{now.tm_min:02d}"
        day = time.strftime('%A', now)
        date = f"{time.strftime('%b', now)} {now.tm_mday}"

        timeSurf = self.text(self.timeFont, clock, self.timeColor)
        # the digits' own height, not the font's line height, so the day and date sit close to them
        timeRect = timeSurf.get_bounding_rect()
        top = self.centerY - timeRect.height // 2
        screen.blit(timeSurf, (self.screenSize // 2 - timeRect.width // 2 - timeRect.x, top - timeRect.y))

        daySurf = self.text(self.dayFont, day, self.textColor)
        dayRect = daySurf.get_bounding_rect()
        screen.blit(daySurf, (self.screenSize // 2 - dayRect.width // 2 - dayRect.x,
                              top - self.gap - dayRect.height - dayRect.y - self.gap * 3))

        dateSurf = self.text(self.dateFont, date, self.textColor)
        dateRect = dateSurf.get_bounding_rect()
        screen.blit(dateSurf, (self.screenSize // 2 - dateRect.width // 2 - dateRect.x,
                               top + timeRect.height + self.gap * 4 - dateRect.y))

        problem = self.problem()
        if problem:
            surf = self.text(self.problemFont, problem, self.problemColor)
            screen.blit(surf, surf.get_rect(center=(self.screenSize // 2, self.problemY)))

        self.checkNetwork()
        if self.network:
            surf = self.text(self.networkFont, self.network, self.networkColor)
            screen.blit(surf, surf.get_rect(center=(self.screenSize // 2, self.networkY)))

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
