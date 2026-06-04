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
        pass
    
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
            

    def draw_centered_text(self, screen):
        if not self.pyFont or not self.text:
            return

        text = self.text
        yPos = self.posCenter[1]

        xOff = self.textShadowOffset[0]
        yOff = self.textShadowOffset[1]
        screenSize = screen.get_width()
        
        if self.shadow:
            shadow_surf = self.pyFont.render(text, True, self.textShadowColor)
            shadow_rect = shadow_surf.get_rect(center=(screenSize // 2 + xOff, yPos + yOff))
            screen.blit(shadow_surf, shadow_rect)
        surf = self.pyFont.render(text, True, self.textColor)
        rect = surf.get_rect(center=(screenSize // 2, yPos))
        screen.blit(surf, rect)

    
    def draw_scrolling_text(self, screen):
        x = self.posCenter[0] - self.widthPx//2
        y = self.posCenter[1] - self.fontHeight//2
        clipRect = pygame.Rect(x,y,self.widthPx,self.fontHeight)

        screen.set_clip(clipRect)


        if self.shadow and self.shadowSurf:
            screen.blit(self.shadowSurf, (x-self.curOffset + self.textShadowOffset[0], y + self.textShadowOffset[1]))
        screen.blit(self.textSurf, (x-self.curOffset, y))

        if self.shadow and self.shadowSurf:
            screen.blit(self.shadowSurf, (x-self.curOffset + self.endGapPx + self.textWidthPx + + self.textShadowOffset[0], y + + self.textShadowOffset[1]))

        screen.blit(self.textSurf, (x-self.curOffset + self.endGapPx + self.textWidthPx, y))
        screen.set_clip(None)

    def render(self, screen):
        if not self.requiresScroll:
            self.draw_centered_text(screen)
        else:
            self.draw_scrolling_text(screen)