import logging
import math
import re
import time
from collections import deque

import pygame
from wp_display_button import WPDisplayButton


# keeps the recent log lines worth reading on the device: warnings, errors, and the connection and network
# changes. filtered as they come in, so the frequent track and timing lines don't push them out
class WpLogBuffer(logging.Handler):
    DEFAULT_PATTERNS = [r'Subscrib', r'address changed', r'come to', r'Attached to', r'Found ', r'not found',
                        r'Discover', r'No Sonos devices', r'Main room is now', r'Fix screen', r'TRYCONNECT',
                        r'App status: (Looking|Couldn|No speakers|Can\'t)']

    def __init__(self, size=300):
        super().__init__(level=logging.INFO)
        self.lines = deque(maxlen=size)     # (time, levelno, message)
        self.setPatterns(self.DEFAULT_PATTERNS)

    def setPatterns(self, patterns):
        self.pattern = re.compile('|'.join(patterns)) if patterns else None

    def emit(self, record):
        try:
            message = record.getMessage()
        except Exception:
            return
        if record.levelno >= logging.WARNING or (self.pattern and self.pattern.search(message)):
            self.lines.append((record.created, record.levelno, message))


logBuffer = WpLogBuffer()


# the buffer's lines, newest at the bottom, wrapped to fit the circle; the arrows page back in time and forward
class WpLogView:
    def __init__(self, config, parent):
        self.parent = parent
        self.screenSize = parent.screenSize
        self.font = parent.getFontForElement('log')
        self.lineHeight = self.font.get_height() + config.getSubkey('layout', 'log_line_space', 2)
        self.top = config.getSubkey('layout', 'log_top', 105)
        self.bottom = config.getSubkey('layout', 'log_bottom', 600)
        # one width for every line, the circle's narrowest chord in the area, so wrapping doesn't depend on position
        self.margin = config.getSubkey('layout', 'log_margin', 20)
        radius = self.screenSize // 2
        edge = max(abs(self.top - radius), abs(self.bottom - radius))
        self.width = int(2 * math.sqrt(radius * radius - edge * edge)) - 2 * self.margin
        self.colors = {
            logging.ERROR: config.getSubkey('layout', 'log_error_color', [235, 95, 75]),
            logging.WARNING: config.getSubkey('layout', 'log_warning_color', [240, 190, 80]),
            logging.INFO: config.getSubkey('layout', 'log_info_color', [200, 200, 200]),
        }
        self.maxWrap = config.getSubkey('layout', 'log_max_lines_per_entry', 3)
        self.pageLines = max(1, (self.bottom - self.top) // self.lineHeight)
        self.offset = 0     # how many lines back from the newest the bottom of the screen is

        hitPadding = config.getSubkey('layout', 'button_hit_padding', 20)
        self.olderButton = WPDisplayButton(
            config.getSubkey('layout', 'favs_prev_page_pos', [50, 320]),
            config.getSubkey('layout', 'favs_prev_page_size', [30, 30]),
            config.getSubkey('layout', 'favs_prev_page_asset', 'assets/PagePrevBtn.png'),
            hitPadding=hitPadding)
        self.newerButton = WPDisplayButton(
            config.getSubkey('layout', 'favs_next_page_pos', [650, 320]),
            config.getSubkey('layout', 'favs_next_page_size', [30, 30]),
            config.getSubkey('layout', 'favs_next_page_asset', 'assets/PageNextBtn.png'),
            hitPadding=hitPadding)

    # opens on the newest lines
    def reset(self):
        self.offset = 0

    def wrap(self, text):
        words, lines, line = text.split(' '), [], ''
        for word in words:
            candidate = f"{line} {word}" if line else word
            if self.font.size(candidate)[0] <= self.width or not line:
                line = candidate
            else:
                lines.append(line)
                line = word
        lines.append(line)
        if len(lines) > self.maxWrap:
            lines = lines[:self.maxWrap]
            lines[-1] = lines[-1] + '...'
        # a single word wider than the line (a long address) is cut
        return [self.cut(l) for l in lines]

    def cut(self, text):
        if self.font.size(text)[0] <= self.width:
            return text
        while text and self.font.size(text + '...')[0] > self.width:
            text = text[:-1]
        return text + '...'

    def displayLines(self):
        out = []
        for created, level, message in list(logBuffer.lines):
            color = self.colors.get(level) or (self.colors[logging.ERROR] if level > logging.WARNING else self.colors[logging.INFO])
            stamp = time.strftime('%H:%M:%S', time.localtime(created))
            message = re.sub(r'^-+App status: (.*?)-+$', r'Status: \1', message)
            for i, text in enumerate(self.wrap(f"{stamp} {message}")):
                out.append((text if i == 0 else '   ' + text, color))
        return out

    def render(self, screen):
        screen.fill((10, 10, 10))
        self.parent._draw_centered_text("Log", (255, 255, 255), shadow=True, yPos=60, font=self.parent.uiHeaderFont)
        lines = self.displayLines()
        self.offset = max(0, min(self.offset, len(lines) - self.pageLines))
        end = len(lines) - self.offset
        shown = lines[max(0, end - self.pageLines):end]
        left = self.screenSize // 2 - self.width // 2
        y = self.bottom - len(shown) * self.lineHeight
        if not shown:
            self.parent._draw_centered_text("Nothing logged yet", self.colors[logging.INFO], shadow=False,
                                            yPos=self.screenSize // 2, font=self.font)
        for text, color in shown:
            screen.blit(self.font.render(text, True, color), (left, y))
            y += self.lineHeight
        self.olderButton.setVisible(end - self.pageLines > 0)
        self.newerButton.setVisible(self.offset > 0)
        self.olderButton.render(screen)
        self.newerButton.render(screen)

    def checkPageTap(self, position):
        if self.olderButton.check_tap(position):
            self.offset += self.pageLines - 1
            return True
        if self.newerButton.check_tap(position):
            self.offset = max(0, self.offset - (self.pageLines - 1))
            return True
        return False
