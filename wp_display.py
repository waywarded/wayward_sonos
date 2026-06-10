import pygame
import sys
import logging
import requests
from io import BytesIO
from play_state_display import PlayStateDisplay
from wp_marquee_text import WPMarqueeText
from wp_autosplit_text import WpAutoSplitText
from wp_app_state import WpAppState
from enum import Enum

class WpDisplayState(Enum):
    INFO="Info"
    QUIT_CONFIRM="QuitConfirm"
    QUITTING="Quitting"

class WPDisplay:
    def __init__(self, config, appStatus, fullScreen=False):
        self.wpStatus = appStatus
        self.config = config
        self.screenSize = config.getSubkey('display', 'screen_size', 720)
        self.bgImagePath = config.getSubkey('display', 'background_image', 'assets/background.png')
        self.displayState = WpDisplayState.INFO

        displayFlags = 0
        if (fullScreen):
            displayFlags |= pygame.FULLSCREEN 
            displayFlags |= pygame.SCALED

        self.wpStatus.updateStatus(f"Initializing pygame (size:{self.screenSize}x{self.screenSize})...")
        pygame.init()
        self.screen = pygame.display.set_mode((self.screenSize, self.screenSize),flags=displayFlags)
        pygame.display.set_caption("Wayward Sonos")

        defaultFontSize = config.getSubkey('display', 'fallback_font_size', 24)
        self.fallbackFont = pygame.font.SysFont("Arial", defaultFontSize)
        
        self.lineInImagePath = config.getSubkey('display', 'line_in_track_image', 'assets/lineIn01.png')
        self.lineInTrackName = config.getSubkey('display','line_in_track_name','Line-In')

        self.lineInImage = None
        self.bgImage = None
        self.running = False

        self.trackArtSurface = None
        self.trackArtUrl = None

        self.textColor = config.getSubkey("display", "text_color", (255, 255, 255))
        self.textShadowColor = config.getSubkey("display", "text_shadow_color", (0, 0, 0))
        self.textShadowOffset = config.getSubkey("display", "text_shadow_offset", (2, 2))

        self.artSize = config.getSubkey('layout', 'album_art_size',360)
        self.artPosY = config.getSubkey('layout', 'album_art_y', 360)

        self.trackFont = self.getFontForElement('track')
        # self.trackTextItem = self.createMarqueeForElement('track', self.trackFont)
        self.trackTextItem = self.createWrappingTextElement('track', self.trackFont)
        self.artistFont = self.getFontForElement('artist')
        self.artistTextItem = self.createMarqueeForElement('artist', self.artistFont)

        self.albumFont = self.getFontForElement('album')
        self.albumTextItem = self.createMarqueeForElement('album', self.albumFont)

        self.speakerFont = self.getFontForElement('speaker')
        self.speakerTextItem = self.createMarqueeForElement('speaker', self.speakerFont)

        self.statusFont = self.getFontForElement('status')
        self.statusTextItem = self.createMarqueeForElement('status', self.statusFont)

        self.uiHeaderFont = self.getFontForElement('ui_header')

        self.playStateY = config.getSubkey('layout', 'play_state_y')

        self.playStateDisplay = PlayStateDisplay(self)
        self.wpStatus.log("Pygame initialized", logging.INFO)

        

    def getFontForElement(self, itemName):
        fontName = self.config.getSubkey('layout', f'{itemName}_font_asset', 'assets/PublicSans-Medium.ttf')
        fontSize = self.config.getSubkey('layout', f'{itemName}_font_size', 24)
        font = pygame.font.Font(fontName, fontSize)
        return font

    def createWrappingTextElement(self, itemName, font):
        centerX = self.screenSize//2
        centerY = self.config.getSubkey('layout', f'{itemName}_text_y', self.screenSize//2)
        doShadow = self.config.getSubkey('layout', f'{itemName}_text_shadow', False)
        doStrip = self.config.getSubkey('layout', f'{itemName}_strip_parens', True)
        textWidth = self.config.getSubkey('layout', f'{itemName}_text_width', self.screenSize//2)
        lineSpace = self.config.getSubkey('layout', f'{itemName}_line_space', 5)
        itemAlpha = self.config.getSubkey('layout', f'{itemName}_text_alpha', 255)

        item = WpAutoSplitText(self.config, self, font, (centerX, centerY), textWidth, doShadow, doStrip, lineSpace = lineSpace)
        # item = WPMarqueeText(self.config, self, font, (centerX, centerY), textWidth, doShadow, doStrip)
        # item.setAlpha(itemAlpha)
        return item        

    
    def createMarqueeForElement(self, itemName, font):
        centerX = self.screenSize//2
        centerY = self.config.getSubkey('layout', f'{itemName}_text_y', self.screenSize//2)
        doShadow = self.config.getSubkey('layout', f'{itemName}_text_shadow', False)
        doStrip = self.config.getSubkey('layout', f'{itemName}_strip_parens', True)
        textWidth = self.config.getSubkey('layout', f'{itemName}_text_width', self.screenSize//2)

        itemAlpha = self.config.getSubkey('layout', f'{itemName}_text_alpha', 255)

        item = WPMarqueeText(self.config, self, font, (centerX, centerY), textWidth, doShadow, doStrip)
        item.setAlpha(itemAlpha)
        return item        


    def loadBackgroundImage(self):
        self.wpStatus.updateStatus("Loading background image...")
        try:
            self.bgImage = pygame.image.load(self.bgImagePath)
            self.bgImage = pygame.transform.scale(self.bgImage, (self.screenSize, self.screenSize))
            self.wpStatus.log("Background image loaded successfully.", logging.INFO)
        except Exception as e:
            self.wpStatus.log(f"Failed to load background image: {e}", logging.ERROR)


    def fetchLineInArt(self):
        try:
            if not self.lineInImage:
                self.wpStatus.logSilent(f"Attempt to load Line-In album art from {self.lineInImagePath}...")
                self.lineInImage = pygame.image.load(self.lineInImagePath)

            if self.lineInImage:
                self.trackArtSurface = pygame.transform.scale(self.lineInImage, (self.screenSize/2, self.screenSize/2))
                self.trackArtUrl = self.lineInImagePath
                self.wpStatus.logSilent(f"Loaded album art from {self.trackArtUrl}", logging.INFO)
            else:
                self.wpStatus.logSilent(f"Failed to load line in album art from {self.lineInImagePath}", logging.INFO)
                self.trackArtUrl = None
                self.trackArtSurface = None
        except Exception as e:
            self.wpStatus.logSilent(f"Exception: failed to load line in art {str(e)}")
            self.trackArtUrl = None
            self.trackArtSurface = None

    def fetchAlbumArt(self, artUrl):
        if (not artUrl) or (not 'http' in artUrl):
            self.trackArtUrl = None
            self.trackArtSurface = None
            return

        self.wpStatus.updateStatus("Loading album art...")
        artSize = self.config.getSubkey('layout', 'album_art_size', self.screenSize//2 )

        try:
            response = requests.get(artUrl)
            response.raise_for_status()  # Check if the request was successful
            imageFile = BytesIO(response.content)
            albumArtImage = pygame.image.load(imageFile)
            self.trackArtSurface = pygame.transform.scale(albumArtImage, (artSize, artSize))
            self.wpStatus.logSilent(f"Loaded album art from {artUrl}", logging.INFO)
            self.trackArtUrl = artUrl
        except Exception as e:
            self.trackArtSurface = None
            self.wpStatus.log(f"Failed to load album art from {artUrl}: {e}", logging.ERROR)
            self.trackArtUrl = None

    def renderTrackInfoStreaming(self,trackInfo, deltaTime):
        if trackInfo.album_art_url != self.trackArtUrl:
            self.fetchAlbumArt(trackInfo.album_art_url)
        
        if self.trackArtSurface:
            posX = (self.screenSize//2 - self.artSize//2)
            posY = (self.artPosY - self.artSize//2)
            self.screen.blit(self.trackArtSurface, (posX, posY))  # Draw album art

        self.trackTextItem.setText(trackInfo.title)
        self.artistTextItem.setText(trackInfo.artist)
        self.albumTextItem.setText(trackInfo.album)
        self.albumTextItem.setScrollMode('scrolling')
        
        self.speakerTextItem.setText(trackInfo.device_string)
        self.speakerTextItem.setScrollMode('truncate')

        self.trackTextItem.update(deltaTime)
        self.artistTextItem.update(deltaTime)
        self.albumTextItem.update(deltaTime)
        self.speakerTextItem.update(deltaTime)

        self.trackTextItem.render(self.screen)        
        self.artistTextItem.render(self.screen)        
        self.albumTextItem.render(self.screen)
        self.speakerTextItem.render(self.screen)


    def renderTrackInfoLineIn(self,trackInfo, deltaTime):
        if self.trackArtUrl != self.lineInImagePath:
            self.fetchLineInArt()

        if self.trackArtSurface:
            self.screen.blit(self.trackArtSurface, (self.screenSize/4, self.screenSize/4))  # Draw album art

        self.trackTextItem.setText(self.lineInTrackName)
        self.trackTextItem.update(deltaTime)
        self.trackTextItem.render(self.screen)        
        self.speakerTextItem.setText(trackInfo.device_string)

        self.speakerTextItem.setScrollMode('truncate')
        self.speakerTextItem.update(deltaTime)
        self.speakerTextItem.render(self.screen)

    def renderTrackInfo(self, deltaTime):
        trackInfo = self.wpStatus.latestTrackInfo

        displayStatePosX = self.screenSize//2
        displayStatePosY = self.playStateY

        if trackInfo:
            if trackInfo.line_in:
                self.renderTrackInfoLineIn(trackInfo, deltaTime)
            else:
                self.renderTrackInfoStreaming(trackInfo, deltaTime)

            self.playStateDisplay.update(deltaTime, trackInfo.isPlaying())
            self.playStateDisplay.render(self.screen, displayStatePosX, displayStatePosY)
        else:
            self.playStateDisplay.update(deltaTime, False)
            self.playStateDisplay.render(self.screen, displayStatePosX, displayStatePosY)
            return


    def renderNoConnectionInfo(self, statusString, deltaTime):
        self.trackTextItem.setText("Not Connected")
        self.trackTextItem.update(deltaTime)
        self.trackTextItem.render(self.screen)        

        self.speakerTextItem.setText(statusString)
        self.speakerTextItem.setScrollMode('scrolling')
        self.speakerTextItem.update(deltaTime)
        self.speakerTextItem.render(self.screen)


    def _draw_centered_text(self, text, color=(255,255,255), shadow=True, yPos = -999, font = None):
        if font is None:
            renderFont = self.fallbackFont
        else:
            renderFont = font

        if (yPos == -999):
            yPos = self.screenSize // 2

        xOff = self.textShadowOffset[0]
        yOff = self.textShadowOffset[1]

        if shadow:
            shadow_surf = renderFont.render(text, True, self.textShadowColor)
            shadow_rect = shadow_surf.get_rect(center=(self.screenSize // 2 + xOff, yPos + yOff))
            self.screen.blit(shadow_surf, shadow_rect)
        surf = renderFont.render(text, True, color)
        rect = surf.get_rect(center=(self.screenSize // 2, yPos))
        self.screen.blit(surf, rect)


    def renderInfo(self, deltaTime):
        if self.bgImage:
            self.screen.blit(self.bgImage, (0, 0))  # Draw background image
        else:
            self.screen.fill((128, 128, 128)) 

        # figure out if we are connected
        if (self.wpStatus.appState != WpAppState.CONNECTED):
            # Not connected - display app status so we can get a sense of why.
            statusText = self.statusFont.render(self.wpStatus.status + f"({str(self.wpStatus.appState)})", True, (255, 255, 255))
            statusHeight = self.config.getSubkey('layout', 'status_font_size', 10)
            self.screen.blit(statusText, (20, self.screenSize - statusHeight - 20))
            self.renderNoConnectionInfo(self.wpStatus.status, deltaTime)
        else:
            self.renderTrackInfo(deltaTime)
        
    def renderQuitConfirm(self, deltaTime):
        self.screen.fill((25, 25, 25))

        pygame.draw.rect(self.screen, (140, 30, 20), pygame.Rect(0, 80, self.screenSize, self.screenSize // 2 - 80))
        pygame.draw.rect(self.screen, (45, 45, 45), pygame.Rect(0, self.screenSize // 2, self.screenSize, self.screenSize // 2))

        self._draw_centered_text("Really Quit?", (200,0,0), shadow=True, yPos = 45, font=self.uiHeaderFont)
        self._draw_centered_text("Yes", (255,255,255), shadow=True, yPos = 200, font=self.uiHeaderFont)
        self._draw_centered_text("No", (255,255,255), shadow=True, yPos = 500, font=self.uiHeaderFont)

    def render(self, deltaTime):

        if self.displayState == WpDisplayState.INFO:
            self.renderInfo(deltaTime)
        elif self.displayState == WpDisplayState.QUIT_CONFIRM:
            self.renderQuitConfirm(deltaTime)

        pygame.display.flip()  # Update the display


 
    def handleTap(self, position):
        self.wpStatus.logSilent(f"Tap: {str(position)}")
        if self.displayState == WpDisplayState.QUIT_CONFIRM:
            self.handleTapConfirm(position)
        elif self.displayState == WpDisplayState.INFO:
            self.handleTapInfo(position)
            
    def handleTapInfo(self, position):
        self.displayState = WpDisplayState.QUIT_CONFIRM

    def handleTapConfirm(self, position):
        if position[1] > self.screenSize//2:
            self.displayState = WpDisplayState.INFO
        else:
            self.displayState = WpDisplayState.QUITTING

    def run(self):
        self.wpStatus.updateStatus("Starting display loop...")
        self.loadBackgroundImage()

        self.running = True
        clock = pygame.time.Clock()

        while self.running:
            dt = clock.tick(30) / 1000.0

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False

                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE or event.key == pygame.K_q:
                        self.running = False

                elif event.type == pygame.MOUSEBUTTONDOWN:
                    self.handleTap(event.pos)
                
            
            if self.displayState == WpDisplayState.QUITTING:
                self.running = False

            if self.running:
                self.render(dt)
            
        self.wpStatus.updateStatus("Shutting down display...")
        pygame.quit()
        sys.exit()