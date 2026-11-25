import pygame
import re

class WPMarqueeText:
    def __init__(self, config, parent, pyFont, positionCenter, width, shadow = False, stripParens = False):
        self.config = config
        self.parent = parent
        self.text = ""
        self.pyFont = pyFont
        self.fontHeight = pyFont.get_height()
        self.widthPx = width
        self.textWidthPx = 0
        self.posCenter = positionCenter
        self.requiresScroll = False
        self.reset = False
        self.textPauseTime = config.getSubkey("display","text_pause_time",5)
        self.textMoveSpeed = config.getSubkey("display", "text_marquee_speed", 130)
        self.textColor = config.getSubkey("display","text_color",(255,255,255))
        self.pauseTimer = 0
        self.curOffset = 0
        self.shadow = shadow
        self.textSurf = None
        self.shadowSurf = None
        self.endGapPx = 50
        self.textShadowColor = config.getSubkey("display", "text_shadow_color", (0, 0, 0))
        self.textShadowOffset = config.getSubkey("display", "text_shadow_offset", (2, 2))
        self.isFirst = True
        self.stripParens = stripParens
        self.alpha = 255
        self.scrollMode = 'scrolling'
    
    def setScrollMode(self, newScrollMode):
        self.scrollMode = newScrollMode

    def setPosition(self, newPosCenter, newWidth):
        self.posCenter = newPosCenter
        self.widthPx = newWidth
        self.checkScroll()

    def resetScroll(self):
        self.pauseTimer = 0
        if self.isFirst:
            self.curOffset = 0
        else:
            self.curOffset = 0
        
        self.isFirst = False

    def checkScroll(self):
        pxWidth = self.pyFont.size(self.text)
        self.requiresScroll = pxWidth[0] > self.widthPx
        self.textWidthPx = pxWidth[0]

    def doStripParens(self, inText):
        clean = re.sub(r'[\(\[][^\)\]]+[\)\]]', '', inText).strip()
        return clean

    def setAlpha(self, newAlpha):
        self.alpha = newAlpha

    def setText(self, newText : str):
        if self.text == newText:
            return

        self.text = newText
        if not self.text:
            self.text = ""

        if self.stripParens:
            self.text = self.doStripParens(self.text)

        self.textSurf = self.pyFont.render(self.text, True, self.textColor, None)
        self.shadowSurf = self.pyFont.render(self.text, True, self.textShadowColor, None)
        
        self.isFirst = True
        self.checkScroll()
        self.resetScroll()

    def update(self, deltaTime):
        if not self.requiresScroll:
            return
        
        if not self.text or not self.textSurf:
            return
        
        if self.pauseTimer < self.textPauseTime:
            self.pauseTimer += deltaTime
            return
        
        self.curOffset += self.textMoveSpeed * deltaTime
        if self.curOffset >= self.textWidthPx + self.endGapPx:
            self.isFirst = False
            self.resetScroll()
    
    def draw_truncated_text(self, screen):
        text = self.text
        suffix = '...'
        while text and self.pyFont.size(text + suffix)[0] > self.widthPx:
            text = text[:-1]
        
        self.draw_centered_text(screen, text + suffix)

    def draw_centered_text(self, screen, text):
        if not self.pyFont or not self.text:
            return

        yPos = self.posCenter[1]

        xOff = self.textShadowOffset[0]
        yOff = self.textShadowOffset[1]
        screenSize = screen.get_width()
        
        if self.shadow:
            shadow_surf = self.pyFont.render(text, True, self.textShadowColor)
            shadow_rect = shadow_surf.get_rect(center=(screenSize // 2 + xOff, yPos + yOff))
            shadow_surf.set_alpha(self.alpha)
            screen.blit(shadow_surf, shadow_rect)
        surf = self.pyFont.render(text, True, self.textColor)
        rect = surf.get_rect(center=(screenSize // 2, yPos))
        surf.set_alpha(self.alpha)
        screen.blit(surf, rect)

    
    def draw_scrolling_text(self, screen):
        x = self.posCenter[0] - self.widthPx//2
        y = self.posCenter[1] - self.fontHeight//2
        clipRect = pygame.Rect(x,y,self.widthPx,self.fontHeight)

        screen.set_clip(clipRect)
        self.textSurf.set_alpha(self.alpha)
        if self.shadowSurf:
            self.shadowSurf.set_alpha(self.alpha)

        if self.shadow and self.shadowSurf:
            screen.blit(self.shadowSurf, (x-self.curOffset + self.textShadowOffset[0], y + self.textShadowOffset[1]))
        screen.blit(self.textSurf, (x-self.curOffset, y))

        if self.shadow and self.shadowSurf:
            screen.blit(self.shadowSurf, (x-self.curOffset + self.endGapPx + self.textWidthPx + + self.textShadowOffset[0], y + + self.textShadowOffset[1]))

        screen.blit(self.textSurf, (x-self.curOffset + self.endGapPx + self.textWidthPx, y))
        screen.set_clip(None)

    def render(self, screen):
        if not self.requiresScroll:
            self.draw_centered_text(screen, self.text)
        else:
            if self.scrollMode == 'truncate':
                self.draw_truncated_text(screen)
            else:
                self.draw_scrolling_text(screen)

# a marquee line drawn in runs of different fonts, [(text, font), ...], e.g. an italic show name then an upright host
class WpRunsText(WPMarqueeText):
    def setRuns(self, runs):
        runs = [(text, font) for text, font in runs if text]
        key = [(text, id(font)) for text, font in runs]
        if key == getattr(self, 'runsKey', None):
            return
        self.runsKey = key
        self.text = ''.join(text for text, _ in runs)
        self.textSurf = self.renderRuns(runs, self.textColor) if runs else None
        self.shadowSurf = self.renderRuns(runs, self.textShadowColor) if runs else None
        self.isFirst = True
        self.checkScroll()
        self.resetScroll()

    # each run sits on the line's shared baseline
    def renderRuns(self, runs, color):
        ascent = max(font.get_ascent() for _, font in runs)
        height = max(ascent - font.get_descent() for _, font in runs)
        surfs = [(font.render(text, True, color), font) for text, font in runs]
        surf = pygame.Surface((sum(s.get_width() for s, _ in surfs), max(height, self.fontHeight)), pygame.SRCALPHA)
        x = 0
        for s, font in surfs:
            surf.blit(s, (x, ascent - font.get_ascent()))
            x += s.get_width()
        return surf

    def checkScroll(self):
        self.textWidthPx = self.textSurf.get_width() if self.textSurf else 0
        self.requiresScroll = self.textWidthPx > self.widthPx

    def draw_centered_text(self, screen, text):
        if not self.textSurf:
            return
        center = (screen.get_width() // 2, self.posCenter[1])
        if self.shadow and self.shadowSurf:
            self.shadowSurf.set_alpha(self.alpha)
            offset = self.textShadowOffset
            screen.blit(self.shadowSurf, self.shadowSurf.get_rect(center=(center[0] + offset[0], center[1] + offset[1])))
        self.textSurf.set_alpha(self.alpha)
        screen.blit(self.textSurf, self.textSurf.get_rect(center=center))
