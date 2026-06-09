import pygame
import sys
import logging
import requests
from io import BytesIO
from play_state_display import PlayStateDisplay
from wp_marquee_text import WPMarqueeText
from wp_app_state import WpAppState

class WPDisplay:
    def __init__(self, config, appStatus, fullScreen=False):
        self.wpStatus = appStatus
        self.config = config
        self.screenSize = config.get("display", {}).get("screen_size", 720)
        self.defaultFontSize = config.get("display", {}).get("font_size", 24)
        self.largeFontSize = config.get("display", {}).get("large_font_size", 32)
        self.bgImagePath = config.get("display", {}).get("background_image", "assets/background.png")
        self.statusFontSize = config.get("display", {}).get("status_font_size", 14)
        self.speakerNameFontSize = config.getSubkey("display","speakerNameFontSize",16)

        displayFlags = 0
        if (fullScreen):
            displayFlags |= pygame.FULLSCREEN 
            displayFlags |= pygame.SCALED

        self.wpStatus.updateStatus(f"Initializing pygame (size:{self.screenSize}x{self.screenSize})...")
        pygame.init()
        self.screen = pygame.display.set_mode((self.screenSize, self.screenSize),flags=displayFlags)
        pygame.display.set_caption("Wayward Sonos")
        self.font = pygame.font.SysFont("Arial", self.defaultFontSize)
        self.trackFont = pygame.font.Font('assets/PublicSans-Bold.ttf', self.largeFontSize)
        self.artistFont = pygame.font.Font('assets/PublicSans-Medium.ttf', self.defaultFontSize)
        self.albumFont = pygame.font.Font('assets/PublicSans-MediumItalic.ttf', self.defaultFontSize)
        self.speakerFont = pygame.font.Font('assets/PublicSans-Medium.ttf', self.speakerNameFontSize)
        
        self.statusFont = pygame.font.SysFont("Arial", self.statusFontSize)
        
        self.lineInImagePath = config.get("display",{}).get("line_in_track_image", "assets/default.png")
        self.lineInTrackName = config.getSubkey("display","line_in_track_name","Line-In")
        self.lineInImage = None
        self.bgImage = None
        self.running = False

        self.trackArtSurface = None
        self.trackArtUrl = None

        self.textColor = config.getSubkey("display", "text_color", (255, 255, 255))
        self.textShadowColor = config.getSubkey("display", "text_shadow_color", (0, 0, 0))
        self.textShadowOffset = config.getSubkey("display", "text_shadow_offset", (2, 2))

        self.trackTextItem = WPMarqueeText(config, self, self.trackFont, (self.screenSize//2, 114), self.screenSize//1.5, False, True)
        self.artistTextItem = WPMarqueeText(config, self, self.artistFont, (self.screenSize//2, 152), self.screenSize//1.5, False, True)
        self.albumTextItem = WPMarqueeText(config, self, self.albumFont, (self.screenSize//2, 570), self.screenSize//1.5, True, True)
        self.speakerTextItem = WPMarqueeText(config, self, self.speakerFont, (self.screenSize//2, 650), self.screenSize//2, False, False)

        self.playStateDisplay = PlayStateDisplay(self)

        self.wpStatus.log("Pygame initialized", logging.INFO)

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
                
        try:
            response = requests.get(artUrl)
            response.raise_for_status()  # Check if the request was successful
            imageFile = BytesIO(response.content)
            albumArtImage = pygame.image.load(imageFile)
            self.trackArtSurface = pygame.transform.scale(albumArtImage, (self.screenSize/2, self.screenSize/2))
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
            self.screen.blit(self.trackArtSurface, (self.screenSize/4, self.screenSize/4))  # Draw album art

        self.trackTextItem.setText(trackInfo.title)
        self.artistTextItem.setText(trackInfo.artist)
        self.albumTextItem.setText(trackInfo.album)
        self.speakerTextItem.setText(trackInfo.device_string)
        self.speakerTextItem.setAlpha(180)
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

        self.speakerTextItem.setAlpha(180)
        self.speakerTextItem.setScrollMode('truncate')
        self.speakerTextItem.update(deltaTime)
        self.speakerTextItem.render(self.screen)

    def renderTrackInfo(self, deltaTime):
        trackInfo = self.wpStatus.latestTrackInfo

        displayStatePosX = self.screenSize//2
        displayStatePosY = 615

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
        self.speakerTextItem.setAlpha(255)
        self.speakerTextItem.setScrollMode('scrolling')
        self.speakerTextItem.update(deltaTime)
        self.speakerTextItem.render(self.screen)

    def _draw_centered_text(self, text, color=(255,255,255), shadow=True, yPos = -999, font = None):
        if font is None:
            renderFont = self.font
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


    def render(self, deltaTime):
        if self.bgImage:
            self.screen.blit(self.bgImage, (0, 0))  # Draw background image
        else:
            self.screen.fill((128, 128, 128)) 

        # figure out if we are connected
        if (self.wpStatus.appState != WpAppState.CONNECTED):
            # Not connected - display app status so we can get a sense of why.
            statusText = self.statusFont.render(self.wpStatus.status + f"({str(self.wpStatus.appState)})", True, (255, 255, 255))
            self.screen.blit(statusText, (20, self.screenSize - self.statusFontSize - 20))
            self.renderNoConnectionInfo(self.wpStatus.status, deltaTime)
        else:
            self.renderTrackInfo(deltaTime)
        
        pygame.display.flip()  # Update the display

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

                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE or event.key == pygame.K_q:
                        pygame.quit()
                        sys.exit()

            self.render(dt)
            
        self.wpStatus.updateStatus("Shutting down display...")
        pygame.quit()
        sys.exit()