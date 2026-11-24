import math
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
