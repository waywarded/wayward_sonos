import pygame
import re

class WpAutoSplitText:
    def __init__(self, config, parent, pyFont, positionCenter, width, shadow = False, stripParens = False, lineSpace = 3):
        self.config = config
        self.parent = parent
        self.text = ""
        self.pyFont = pyFont
        self.fontHeight = pyFont.get_height()
        self.widthPx = width
        self.posCenter = positionCenter
        self.requiresSplit = False

        self.line1Text = "" 
        self.line1TextSurf = None
        self.line1ShadowSurf = None
        self.line2Text = ""
        self.line2TextSurf = None
        self.line2ShadowSurf = None
        self.doShadow = shadow
        
        self.textColor = config.getSubkey('display','text_color', (255,255,255))
        self.textShadowColor = config.getSubkey("display", "text_shadow_color", (0, 0, 0))
        self.textShadowOffset = config.getSubkey("display", "text_shadow_offset", (2, 2))
        self.shadowSurf = None

        self.lineSpace = lineSpace
        self.isFirst = True
        self.doStrip = stripParens
    

    def setPosition(self, newPosCenter, newWidth):
        self.posCenter = newPosCenter
        self.widthPx = newWidth
        self.checkWrap()
    
    def doStripParens(self, inText):
        clean = re.sub(r'[\(\[][^\)\]]+[\)\]]', '', inText).strip()
        return clean

    def setText(self, newText : str):
        if self.text == newText:
            return
        
        self.text = newText
        if not self.text:
            self.text = ''
        
        if self.doStrip:
            self.text = self.doStripParens(self.text)

        self.checkWrap()

        if self.line1Text:
            self.line1TextSurf = self.pyFont.render(self.line1Text, True, self.textColor, None)
            self.line1ShadowSurf = self.pyFont.render(self.line1Text, True, self.textShadowColor, None) if self.doShadow else None

        if self.requiresSplit and self.line2Text:
            self.line2TextSurf = self.pyFont.render(self.line2Text, True, self.textColor, None)
            self.line2ShadowSurf = self.pyFont.render(self.line2Text, True, self.textShadowColor, None) if self.doShadow else None

        self.isFirst = True

    def checkWrap(self):
        # look at self.text and determine (a) if it needs to wrap, and (b) if so, do apply an optimal wrap.
        
        # Trivial reject
        if not self.text:
            self.line1Text = ''
            self.line2Text = ''
            self.requiresSplit = False
            return False
    
        # Maybe we don't need to wrap.  Try that first.
        fullLen = self.pyFont.size(self.text)[0]
        if fullLen < self.widthPx:
            self.requiresSplit = False
            self.line1Text = self.text
            self.line2Text = None
            return False
        

        # if we get here, we need to wrap.  Let's do it.

        # first, let's cut it down to size. If we are too big to fit into 2 lines
        # do truncation and elipsis
        truncatedText = self.text
        suffix = '...'
        self.requiresSplit = True

        while truncatedText and self.pyFont.size(truncatedText + suffix)[0] > (2*self.widthPx):
            truncatedText = truncatedText[:-1]

        # Now search for a balance split (on word boundaries)
        words = truncatedText.split()
        bestSplit = 1
        bestLineDif = float('inf')

        line1 = ''
        line2 = ''
        for i in range(1,len(words)):
            line1 = ' '.join(words[:i])
            line2 = ' '.join(words[i:])
            width1 = self.pyFont.size(line1)[0]
            width2 = self.pyFont.size(line2)[0]
            
            if (width1 > self.widthPx) or (width2 > self.widthPx):
                # invalid combination - one of them is too long
                continue
            
            dif = abs(width1 - width2)
            if dif < bestLineDif:
                bestSplit = i
                bestLineDif = dif
        
        self.line1Text = ' '.join(words[:bestSplit])
        self.line2Text = ' '.join(words[bestSplit:])


    def render(self, screen):
        if not self.requiresSplit:
            if self.doShadow and self.line1ShadowSurf:
                shadowRect = self.line1ShadowSurf.get_rect(center=(self.posCenter[0] + self.textShadowOffset[0], self.posCenter[1] + self.textShadowOffset[1]))
                screen.blit(self.line1ShadowSurf, shadowRect)
            
            if self.line1TextSurf:
                textRect = self.line1TextSurf.get_rect(center=(self.posCenter[0],self.posCenter[1]))
                screen.blit(self.line1TextSurf, textRect)

        else:
            line1Y = self.posCenter[1] - self.fontHeight//2 - self.lineSpace//2
            line2Y = self.posCenter[1] + self.fontHeight//2 + self.lineSpace//2

            if self.line1TextSurf:
                if self.doShadow and self.line1ShadowSurf:
                    shadowRect = self.line1ShadowSurf.get_rect(center=(self.posCenter[0] + self.textShadowOffset[0], line1Y + self.textShadowOffset[1]))
                    screen.blit(self.line1ShadowSurf, shadowRect)
                
                textRect = self.line1TextSurf.get_rect(center=(self.posCenter[0],line1Y))
                screen.blit(self.line1TextSurf, textRect)

            if self.line2TextSurf:
                if self.doShadow and self.line2ShadowSurf:
                    shadowRect = self.line2ShadowSurf.get_rect(center=(self.posCenter[0] + self.textShadowOffset[0], line2Y + self.textShadowOffset[1]))
                    screen.blit(self.line2ShadowSurf, shadowRect)
                textRect = self.line2TextSurf.get_rect(center=(self.posCenter[0],line2Y))
                screen.blit(self.line2TextSurf, textRect)
        
    def update(self, deltaTime):
        pass