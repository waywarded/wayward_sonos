import pygame
import sys
import logging
import requests
from io import BytesIO
from play_state_display import PlayStateDisplay, moveToward
from wp_marquee_text import WPMarqueeText
from wp_autosplit_text import WpAutoSplitText
from wp_app_state import WpAppState
from wp_display_button import WPDisplayButton
from wp_fav_content_display import WpFavContentDisplay
from wp_rooms_display import WpRoomsDisplay
from wp_volume_dial import WpVolumeDial
from wp_command_feedback import WpCommandFeedback
from wp_soco import NowPlayingInfo

from enum import Enum

class WpDisplayState(Enum):
    INFO="Info"
    FAVORITES="Favorites"
    ROOMS="Rooms"
    VOLUME="Volume"
    QUIT_CONFIRM="QuitConfirm"
    QUITTING="Quitting"

class WPDisplay:
    def __init__(self, config, appStatus, fullScreen=False, roundMask=False):
        self.wpStatus = appStatus
        self.config = config
        self.screenSize = config.getSubkey('display', 'screen_size', 720)
        self.bgImagePath = config.getSubkey('display', 'background_image', 'assets/background.png')
        self.displayState = WpDisplayState.INFO
        self.roundMask = roundMask
        self.roundMaskSurface = None
        self.screenshotRequested = False

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

        hitPadding = config.getSubkey('layout', 'button_hit_padding', 20)

        self.nextButton = WPDisplayButton(
            config.getSubkey('layout', 'next_button_pos', [600, 320]),
            config.getSubkey('layout', 'next_button_size', [60, 60]),
            config.getSubkey('layout', 'next_button_asset', 'assets/NextTrackBtn.png'),
            hitPadding=hitPadding
        )

        self.prevButton = WPDisplayButton(
            config.getSubkey('layout', 'prev_button_pos', [540, 320]),
            config.getSubkey('layout', 'prev_button_size', [30, 30]),
            config.getSubkey('layout', 'prev_button_asset', 'assets/PrevTrackBtn.png'),
            hitPadding=hitPadding
        )

        self.playButton = WPDisplayButton(
            config.getSubkey('layout', 'play_button_pos', [340, 700]),
            config.getSubkey('layout', 'play_button_size', [40, 40]),
            config.getSubkey('layout', 'play_button_asset', 'assets/PlayBtn.png'),
            hitPadding=hitPadding
        )

        self.pauseButton = WPDisplayButton(
            config.getSubkey('layout', 'play_button_pos', [340, 640]),
            config.getSubkey('layout', 'play_button_size', [30, 30]),
            config.getSubkey('layout', 'pause_button_asset', 'assets/PauseBtn.png'),
            hitPadding=hitPadding
        )

        self.favsButton = WPDisplayButton(
            config.getSubkey('layout', 'favs_button_pos', [230, 640]),
            config.getSubkey('layout', 'favs_button_size', [45, 45]),
            config.getSubkey('layout', 'favs_button_asset', 'assets/FavsBtn.png'),
            hitPadding=hitPadding
        )

        # press and hold for the volume dial
        self.volumeButton = WPDisplayButton(
            config.getSubkey('layout', 'volume_button_pos', [450, 640]),
            config.getSubkey('layout', 'volume_button_size', [45, 45]),
            config.getSubkey('layout', 'volume_button_asset', 'assets/VolBtn.png'),
            hitPadding=hitPadding
        )

        # one button, drawn bright when shuffle is on and dim when off
        shufflePos = config.getSubkey('layout', 'shuffle_button_pos', [62, 410])
        shuffleSize = config.getSubkey('layout', 'shuffle_button_size', [30, 30])
        shuffleAsset = config.getSubkey('layout', 'shuffle_button_asset', 'assets/ShuffleBtn.png')
        self.shuffleOnButton = WPDisplayButton(shufflePos, shuffleSize, shuffleAsset, hitPadding=hitPadding)
        self.shuffleOffButton = WPDisplayButton(shufflePos, shuffleSize, shuffleAsset, hitPadding=hitPadding)
        self.shuffleOffButton.button_surface.set_alpha(config.getSubkey('layout', 'shuffle_off_alpha', 90))

        # opens the rooms screen (grouping)
        self.groupButton = WPDisplayButton(
            config.getSubkey('layout', 'group_button_pos', [500, 640]),
            config.getSubkey('layout', 'group_button_size', [30, 30]),
            config.getSubkey('layout', 'group_button_asset', 'assets/SpeakerGroup.png'),
            hitPadding=hitPadding
        )

        self.favsBackButton = WPDisplayButton(
            config.getSubkey('layout', 'favs_back_button_pos', [340, 640]),
            config.getSubkey('layout', 'favs_back_button_size', [45, 45]),
            config.getSubkey('layout', 'favs_back_button_asset', 'assets/DownBtn.png'),
            hitPadding=hitPadding
        )

        self.favsRefreshButton = WPDisplayButton(
            config.getSubkey('layout', 'favs_refresh_button_pos', [425, 45]),
            config.getSubkey('layout', 'favs_refresh_button_size', [30, 30]),
            config.getSubkey('layout', 'favs_refresh_button_asset', 'assets/RefreshBtn.png'),
            hitPadding=hitPadding
        )

        self.favContentDisplay = WpFavContentDisplay(config, appStatus, self)
        self.roomsDisplay = WpRoomsDisplay(config, appStatus, self)
        self.volumeDial = WpVolumeDial(config, appStatus, self)
        self.commandFeedback = WpCommandFeedback(config, appStatus, self)

        # favorites (or rooms) slides up over now playing: 0 = hidden, 1 = fully open
        self.favsSlide = 0.0
        self.favsSlideTarget = 0.0
        self.favsSlideTime = config.getSubkey('layout', 'favs_slide_time', 0.3)
        self.favsPanel = pygame.Surface((self.screenSize, self.screenSize))
        self.favsPanelColor = config.getSubkey('layout', 'favs_panel_color', [0, 0, 0])

        # quitting is press-and-hold on an invisible area above the song title, so it can't happen by accident
        holdArea = config.getSubkey('layout', 'quit_hold_area', [200, 10, 320, 85])
        self.quitHoldRect = pygame.Rect(holdArea[0], holdArea[1], holdArea[2], holdArea[3])
        self.quitHoldTime = config.getSubkey('layout', 'quit_hold_time', 1.5)
        self.quitHoldElapsed = None     # None when not holding

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

    def buttonsVisible(self):
        return self.wpStatus.appState == WpAppState.CONNECTED and self.wpStatus.latestTrackInfo is not None

    # line-in can play/pause but has no tracks to skip
    def skipButtonsVisible(self):
        return self.buttonsVisible() and not self.wpStatus.latestTrackInfo.line_in

    def updateButtonVisibility(self):
        show = self.buttonsVisible()
        playing = show and self.wpStatus.latestTrackInfo.isPlaying()
        self.nextButton.setVisible(self.skipButtonsVisible())
        self.prevButton.setVisible(self.skipButtonsVisible())
        self.playButton.setVisible(show and not playing)
        self.pauseButton.setVisible(playing)
        # dimmed and ignoring taps until the speaker has done what was last asked, so taps can't pile up
        ready = not self.wpStatus.commandsBusy()
        shuffleOn = bool(self.wpStatus.shuffle)
        self.shuffleOnButton.setVisible(self.skipButtonsVisible() and shuffleOn)
        self.shuffleOffButton.setVisible(self.skipButtonsVisible() and not shuffleOn)
        for button in (self.nextButton, self.prevButton, self.playButton, self.pauseButton,
                       self.shuffleOnButton, self.shuffleOffButton):
            button.setEnabled(ready)
        self.favsButton.setVisible(show)
        self.volumeButton.setVisible(show)
        self.groupButton.setVisible(show)

    def renderButtons(self, trackinfo : NowPlayingInfo ):
        if self.nextButton:
            self.nextButton.render(self.screen)
        if self.prevButton:
            self.prevButton.render(self.screen)
        if self.pauseButton:
            self.pauseButton.render(self.screen)
        if self.playButton:
            self.playButton.render(self.screen)
        if self.favsButton:
            self.favsButton.render(self.screen)
        if self.volumeButton:
            self.volumeButton.render(self.screen)
        self.shuffleOnButton.render(self.screen)
        self.shuffleOffButton.render(self.screen)
        self.groupButton.render(self.screen)


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

            self.renderButtons(trackInfo)

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


    def _draw_centered_text(self, text, color=(255,255,255), shadow=True, yPos = -999, font = None, surface = None):
        target = self.screen if surface is None else surface
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
            target.blit(shadow_surf, shadow_rect)
        surf = renderFont.render(text, True, color)
        rect = surf.get_rect(center=(self.screenSize // 2, yPos))
        target.blit(surf, rect)


    def renderInfo(self, deltaTime):
        # set every frame so taps match what's on screen
        self.updateButtonVisibility()

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
            self.commandFeedback.update(deltaTime)
            self.commandFeedback.render(self.screen)
        
    def renderQuitConfirm(self, deltaTime):
        self.screen.fill((25, 25, 25))

        pygame.draw.rect(self.screen, (140, 30, 20), pygame.Rect(0, 80, self.screenSize, self.screenSize // 2 - 80))
        pygame.draw.rect(self.screen, (45, 45, 45), pygame.Rect(0, self.screenSize // 2, self.screenSize, self.screenSize // 2))

        self._draw_centered_text("Really Quit?", (200,0,0), shadow=True, yPos = 45, font=self.uiHeaderFont)
        self._draw_centered_text("Yes", (255,255,255), shadow=True, yPos = 200, font=self.uiHeaderFont)
        self._draw_centered_text("No", (255,255,255), shadow=True, yPos = 500, font=self.uiHeaderFont)

    def openFavorites(self):
        self.displayState = WpDisplayState.FAVORITES
        self.favsSlideTarget = 1.0

    # the rooms screen slides up the same way, on the same slide
    def openRooms(self):
        self.displayState = WpDisplayState.ROOMS
        self.favsSlideTarget = 1.0
        self.roomsDisplay.reset()
        self.wpStatus.requestRoomsRefresh()

    def closeFavorites(self):
        self.favsSlideTarget = 0.0

    def favsSliding(self):
        return self.favsSlide != self.favsSlideTarget

    def renderFavorites(self, deltaTime):
        self.renderSlidingPanel(deltaTime, self.drawFavoritesPanel)

    def drawFavoritesPanel(self, panel):
        self._draw_centered_text("Favorites", (255,255,255), shadow=True, yPos = 60, font=self.uiHeaderFont, surface=panel)
        self.favContentDisplay.render(panel)
        if self.favsBackButton:
            self.favsBackButton.render(panel)
        if self.favsRefreshButton:
            self.favsRefreshButton.setEnabled(not self.wpStatus.favsRefreshPending())
            self.favsRefreshButton.render(panel)

    def drawRoomsPanel(self, panel):
        self._draw_centered_text(self.roomsDisplay.title(), (255,255,255), shadow=True, yPos = 60, font=self.uiHeaderFont, surface=panel)
        self.roomsDisplay.render(panel)
        self.favsBackButton.render(panel)

    def renderSlidingPanel(self, deltaTime, drawPanel):
        self.favsSlide = moveToward(self.favsSlide, self.favsSlideTarget, deltaTime / self.favsSlideTime)
        if self.favsSlide == 0.0 and self.favsSlideTarget == 0.0:
            self.displayState = WpDisplayState.INFO
            self.renderInfo(deltaTime)
            return

        # now playing stays live underneath while the panel moves
        if self.favsSlide < 1.0:
            self.renderInfo(deltaTime)

        panel = self.favsPanel
        panel.fill(self.favsPanelColor)
        drawPanel(panel)

        # ease out: fast start, gentle stop
        eased = 1 - (1 - self.favsSlide) ** 3
        self.screen.blit(panel, (0, int((1 - eased) * self.screenSize)))

    def updateQuitHold(self, deltaTime):
        if self.quitHoldElapsed is None:
            return
        self.quitHoldElapsed += deltaTime
        if self.quitHoldElapsed >= self.quitHoldTime:
            self.quitHoldElapsed = None
            self.displayState = WpDisplayState.QUIT_CONFIRM

    def render(self, deltaTime):
        if self.displayState == WpDisplayState.INFO:
            self.updateQuitHold(deltaTime)
        if self.displayState == WpDisplayState.INFO:
            self.renderInfo(deltaTime)
        elif self.displayState == WpDisplayState.FAVORITES:
            self.renderFavorites(deltaTime)
        elif self.displayState == WpDisplayState.ROOMS:
            self.renderSlidingPanel(deltaTime, self.drawRoomsPanel)
        elif self.displayState == WpDisplayState.VOLUME:
            self.renderInfo(deltaTime)
            self.volumeDial.update(deltaTime)
            self.volumeDial.render(self.screen)
        elif self.displayState == WpDisplayState.QUIT_CONFIRM:
            self.renderQuitConfirm(deltaTime)

        if self.roundMask:
            self.renderRoundMask()

        pygame.display.flip()  # Update the display

        if self.screenshotRequested:
            self.screenshotRequested = False
            self.saveScreenshot()

    # dev aid: paint over everything outside the circle so a desktop window looks like the round Pi display
    def renderRoundMask(self):
        if self.roundMaskSurface is None:
            self.roundMaskSurface = pygame.Surface((self.screenSize, self.screenSize), pygame.SRCALPHA)
            maskColor = self.config.getSubkey('display', 'round_mask_color', [255, 255, 255])
            self.roundMaskSurface.fill((*maskColor, 255))
            # draw functions write pixels without blending, so this punches a transparent hole
            pygame.draw.circle(self.roundMaskSurface, (0, 0, 0, 0), (self.screenSize//2, self.screenSize//2), self.screenSize//2)
        self.screen.blit(self.roundMaskSurface, (0, 0))

    def requestScreenshot(self):
        self.screenshotRequested = True

    def saveScreenshot(self):
        path = 'logs/screen.png'
        try:
            pygame.image.save(self.screen, path)
            self.wpStatus.log(f"Saved screenshot to {path}", logging.INFO)
        except Exception as e:
            self.wpStatus.log(f"Failed to save screenshot: {e}", logging.ERROR)


    def checkButtonTap(self, event_pos):
        if self.favsButton and self.favsButton.check_tap(event_pos):
            self.openFavorites()
            return True
        if self.volumeButton and self.volumeButton.check_tap(event_pos):
            self.displayState = WpDisplayState.VOLUME
            self.volumeDial.begin(event_pos)
            return True

        if (self.pauseButton and self.pauseButton.check_tap(event_pos)) or (self.playButton and self.playButton.check_tap(event_pos)):
            print("pause button pressed")
            trackInfo = self.wpStatus.latestTrackInfo
            if trackInfo.isPlaying():
                self.wpStatus.dispatchEvent('transport', control='pause')
            else:
                self.wpStatus.dispatchEvent('transport', control='play')
            return True
        if self.nextButton and self.nextButton.check_tap(event_pos):
            self.wpStatus.dispatchEvent('transport', control='next')
            print("next button pressed")
            return True
        if self.prevButton and self.prevButton.check_tap(event_pos):
            self.wpStatus.dispatchEvent('transport', control='prev')
            print("prev button pressed")
            return True
        if self.groupButton.check_tap(event_pos):
            self.openRooms()
            return True
        if self.shuffleOnButton.check_tap(event_pos) or self.shuffleOffButton.check_tap(event_pos):
            self.wpStatus.dispatchEvent('transport', control='shuffle')
            return True
        return False

    def handleTap(self, position):
        self.wpStatus.logSilent(f"Tap: {str(position)}")

        if self.displayState == WpDisplayState.QUIT_CONFIRM:
            self.handleTapConfirm(position)
        elif self.displayState == WpDisplayState.INFO:
            self.handleTapInfo(position)
        elif self.displayState == WpDisplayState.FAVORITES:
            self.handleTapFavorites(position)
        elif self.displayState == WpDisplayState.ROOMS:
            self.handleTapRooms(position)
        elif self.displayState == WpDisplayState.VOLUME:
            # the release went missing (e.g. dropped touch event); a new touch closes the dial
            self.displayState = WpDisplayState.INFO
            
    def handleTapInfo(self, position):
        # same condition renderInfo draws it under, so taps never go to an overlay that isn't on screen
        if self.wpStatus.appState == WpAppState.CONNECTED and self.commandFeedback.active():
            self.commandFeedback.handleTap(position)
            return
        if self.checkButtonTap(position):
            return
        if self.quitHoldRect.collidepoint(position):
            self.quitHoldElapsed = 0.0

    def handleRelease(self, position):
        self.quitHoldElapsed = None
        if self.displayState == WpDisplayState.VOLUME:
            self.displayState = WpDisplayState.INFO

    def handleMotion(self, position):
        if self.displayState == WpDisplayState.VOLUME:
            self.volumeDial.motion(position)

    def handleTapFavorites(self, position):
        # button rects are in panel coordinates, which only match the screen once fully open
        if self.favsSliding():
            return

        if self.favsBackButton and self.favsBackButton.check_tap(position):
            self.closeFavorites()
        elif self.favsRefreshButton and self.favsRefreshButton.check_tap(position):
            self.wpStatus.requestFavsRefresh()
        elif self.favContentDisplay.checkPageTap(position):
            pass
        elif self.favContentDisplay.checkTileTap(position):
            self.closeFavorites()

    def handleTapRooms(self, position):
        if self.favsSliding():
            return
        if self.favsBackButton.check_tap(position):
            self.closeFavorites()
        elif self.roomsDisplay.checkPageTap(position):
            pass
        elif self.roomsDisplay.checkSetMainTap(position):
            pass
        else:
            self.roomsDisplay.checkRowTap(position)

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
                    elif event.key == pygame.K_s:
                        self.requestScreenshot()

                elif event.type == pygame.MOUSEBUTTONDOWN:
                    self.handleTap(event.pos)

                elif event.type == pygame.MOUSEBUTTONUP:
                    self.handleRelease(event.pos)

                elif event.type == pygame.MOUSEMOTION:
                    self.handleMotion(event.pos)
                
            
            if self.displayState == WpDisplayState.QUITTING:
                self.running = False

            if self.running:
                self.render(dt)
            
        self.wpStatus.updateStatus("Shutting down display...")
        pygame.quit()
        sys.exit()