import pygame
import sys
import logging
import requests
import os
import subprocess
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
from wp_log_view import WpLogView
from wp_clock_display import WpClockDisplay, clockIcon
from wp_art_cache import WpArtCache
from wp_soco import NowPlayingInfo

from enum import Enum

class WpDisplayState(Enum):
    INFO="Info"
    FAVORITES="Favorites"
    ROOMS="Rooms"
    VOLUME="Volume"
    QUIT_CONFIRM="QuitConfirm"
    LOG="Log"
    CLOCK="Clock"
    QUITTING="Quitting"

class WPDisplay:
    def __init__(self, config, appStatus, fullScreen=False, roundMask=False):
        self.wpStatus = appStatus
        self.config = config
        self.screenSize = config.getSubkey('display', 'screen_size', 720)
        self.bgImagePath = config.getSubkey('display', 'background_image', 'assets/background.png')
        # the background's horizon line (in screen pixels, unshifted); the image is moved so it lines up with the art's bottom
        self.bgHorizonY = config.getSubkey('display', 'background_horizon_y', 538)
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
        self.trackArtKey = None     # (art url, favorite) the art was last picked for, so a failed fetch isn't retried every frame
        # art for favorites that have none of their own (radio streams), by favorite name
        self.fallbackArt = config.getSubkey('favorites', 'fallback_art', {}) or {}

        self.textColor = config.getSubkey("display", "text_color", (255, 255, 255))
        self.textShadowColor = config.getSubkey("display", "text_shadow_color", (0, 0, 0))
        self.textShadowOffset = config.getSubkey("display", "text_shadow_offset", (2, 2))

        self.artSize = config.getSubkey('layout', 'album_art_size',360)
        self.artPosY = config.getSubkey('layout', 'album_art_y', 360)
        # full screen: the art fills the circle in place of the background image, and the text gets a dark band
        self.artFullScreen = config.getSubkey('layout', 'album_art_full_screen', False)
        # the band's bottom stays put; its top follows the title, so one-line titles get a shorter band
        self.textBandBottom = config.getSubkey('layout', 'text_band_bottom', None)     # None for no band
        self.textBandPadding = config.getSubkey('layout', 'text_band_padding', 10)
        self.textBandTop = None
        self.trackTextBottom = config.getSubkey('layout', 'track_text_bottom', None)   # None: centred on track_text_y
        self.skipButtonsFollowTitle = config.getSubkey('layout', 'skip_buttons_follow_title', False)
        # one-line titles: the text moves up this much and the band gains it at the top, so it isn't a thin strip
        self.textBandSingleLinePadding = config.getSubkey('layout', 'text_band_single_line_padding', 0)
        self.artistBaseY = config.getSubkey('layout', 'artist_text_y', self.screenSize // 2)
        self.albumBaseY = config.getSubkey('layout', 'album_text_y', self.screenSize // 2)
        self.textBandAlpha = config.getSubkey('layout', 'text_band_alpha', 150)
        self.textBandSurface = None
        self.textBandFeather = config.getSubkey('layout', 'text_band_feather', 0)     # soft top and bottom edges
        self.textBandEdges = {}     # height -> edge surface
        # tapping the band fades it and its text out, to see the whole cover, and back in
        self.textHidden = False
        self.textFade = 1.0         # how much of the band and its text shows, 0 to 1
        self.textFadeTime = config.getSubkey('layout', 'text_fade_time', 0.4)
        self.textLayer = None

        # artist and album take turns in one spot, fading out and back in between
        self.artistShowTime = config.getSubkey('layout', 'artist_show_time', 8.0)
        self.albumShowTime = config.getSubkey('layout', 'album_show_time', 4.0)
        self.artistAlbumFadeTime = config.getSubkey('layout', 'artist_album_fade_time', 0.4)
        self.artistAlpha = config.getSubkey('layout', 'artist_text_alpha', 255)
        self.albumAlpha = config.getSubkey('layout', 'album_text_alpha', 255)
        self.artistAlbumTime = 0.0
        self.artistAlbumTrack = None    # the track the cycle started on; a new one starts with the artist

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
        # prev/next are thin arrows out at the edge: a bigger target than the art suggests
        skipHitPadding = config.getSubkey('layout', 'skip_button_hit_padding', hitPadding)

        self.nextButton = WPDisplayButton(
            config.getSubkey('layout', 'next_button_pos', [600, 320]),
            config.getSubkey('layout', 'next_button_size', [60, 60]),
            config.getSubkey('layout', 'next_button_asset', 'assets/NextTrackBtn.png'),
            hitPadding=skipHitPadding
        )

        self.prevButton = WPDisplayButton(
            config.getSubkey('layout', 'prev_button_pos', [540, 320]),
            config.getSubkey('layout', 'prev_button_size', [30, 30]),
            config.getSubkey('layout', 'prev_button_asset', 'assets/PrevTrackBtn.png'),
            hitPadding=skipHitPadding
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
        # fainter than off, so line-in's greyed-out shuffle doesn't read as just "off"
        self.shuffleOffButton.disabled_surface.set_alpha(config.getSubkey('layout', 'shuffle_disabled_alpha', 35))

        # opens the rooms screen (grouping)
        self.groupButton = WPDisplayButton(
            config.getSubkey('layout', 'group_button_pos', [500, 640]),
            config.getSubkey('layout', 'group_button_size', [30, 30]),
            config.getSubkey('layout', 'group_button_asset', 'assets/SpeakerGroup.png'),
            hitPadding=hitPadding
        )

        backdropAlpha = config.getSubkey('layout', 'button_backdrop_alpha', 0)
        if backdropAlpha:
            backdropPadding = config.getSubkey('layout', 'button_backdrop_padding', 10)
            for button in (self.playButton, self.pauseButton, self.favsButton,
                           self.volumeButton, self.shuffleOnButton, self.shuffleOffButton, self.groupButton):
                button.setBackdrop(backdropPadding, backdropAlpha)

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

        # same art and size as favorites' refresh; placed just right of the "Rooms" title each frame
        self.roomsRefreshButton = WPDisplayButton(
            [0, 0],
            config.getSubkey('layout', 'favs_refresh_button_size', [30, 30]),
            config.getSubkey('layout', 'favs_refresh_button_asset', 'assets/RefreshBtn.png'),
            hitPadding=config.getSubkey('layout', 'rooms_refresh_button_hit_padding', 10)
        )
        self.roomsRefreshGap = config.getSubkey('layout', 'rooms_refresh_button_gap', 22)

        self.logView = WpLogView(config, self)
        # album art as it's shown, for the clock's background
        self.artCache = WpArtCache(config.getSubkey('layout', 'clock_art_folder', 'art_cache'),
                                   config.getSubkey('layout', 'clock_art_count', 40))
        self.clockDisplay = WpClockDisplay(config, appStatus, self, self.artCache)
        # the clock comes up after clock_idle_time seconds on now playing with nothing playing, or not connected
        self.clockIdleTime = config.getSubkey('layout', 'clock_idle_time', 300)
        self.idleTime = 0.0
        self.clockSawStopped = False    # leaves on its own only when playback starts after being stopped
        self.clockFadeTime = config.getSubkey('layout', 'clock_fade_time', 0.6)
        self.clockFade = 0.0            # 1 just after leaving the clock, down to 0 as it fades out
        # no alpha channel: on the Mac the window's format has one, a plain Surface inherits it, and the clock's
        # text then left see-through boxes that flashed now playing through as it faded
        self.clockLayer = pygame.Surface((self.screenSize, self.screenSize), 0, 32)
        clockButtonSize = config.getSubkey('layout', 'favs_refresh_button_size', [30, 30])
        # favorites' header, mirroring its refresh button on the other side of the title
        self.favsClockButton = WPDisplayButton(
            config.getSubkey('layout', 'favs_clock_button_pos', [265, 45]),
            clockButtonSize,
            clockIcon(clockButtonSize[0]),
            hitPadding=hitPadding
        )
        self.favContentDisplay = WpFavContentDisplay(config, appStatus, self)
        self.roomsDisplay = WpRoomsDisplay(config, appStatus, self)
        self.volumeDial = WpVolumeDial(config, appStatus, self)
        self.commandFeedback = WpCommandFeedback(config, appStatus, self)
        self.configMainRoom = config.mainRoomName()     # named on the connecting screen until the speakers report it

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
        # a strip at the bottom of the quit confirm that re-syncs a glitching panel instead of quitting
        self.resyncTop = config.getSubkey('layout', 'quit_resync_top', 620)
        # and above it, one that opens the log
        self.logTop = config.getSubkey('layout', 'quit_log_top', 520)
        self.resyncScript = config.getSubkey('display', 'resync_script', 'resync_display.sh')

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

        # optional larger sizes, largest first: the biggest that fits in two lines without cutting the text is used
        fontName = self.config.getSubkey('layout', f'{itemName}_font_asset', 'assets/PublicSans-Medium.ttf')
        fitSizes = self.config.getSubkey('layout', f'{itemName}_font_sizes', [])
        fitFonts = [pygame.font.Font(fontName, size) for size in fitSizes]

        item = WpAutoSplitText(self.config, self, font, (centerX, centerY), textWidth, doShadow, doStrip, lineSpace = lineSpace, fitFonts = fitFonts)
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
                self.trackArtSurface = self.scaleArt(self.lineInImage)
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
            self.trackArtSurface = self.scaleArt(albumArtImage)
            self.wpStatus.logSilent(f"Loaded album art from {artUrl}", logging.INFO)
            self.trackArtUrl = artUrl
            self.artCache.save(response.content)
        except Exception as e:
            self.trackArtSurface = None
            self.wpStatus.log(f"Failed to load album art from {artUrl}: {e}", logging.ERROR)
            self.trackArtUrl = None

    def scaleArt(self, image):
        if self.artFullScreen:
            return pygame.transform.smoothscale(image.convert(), (self.screenSize, self.screenSize))
        return pygame.transform.scale(image, (self.artSize, self.artSize))

    def renderTrackArt(self):
        if self.trackArtSurface:
            if self.artFullScreen:
                self.screen.blit(self.trackArtSurface, (0, 0))
            else:
                posX = (self.screenSize//2 - self.artSize//2)
                posY = (self.artPosY - self.artSize//2)
                self.screen.blit(self.trackArtSurface, (posX, posY))

    # the band and the text on it; while fading they're drawn to a layer that's blended in whole
    def renderTextBand(self, deltaTime, textItems):
        step = deltaTime / self.textFadeTime if self.textFadeTime > 0 else 1.0
        goal = 0.0 if self.textHidden else 1.0
        self.textFade = goal if abs(goal - self.textFade) <= step else self.textFade + (step if goal > self.textFade else -step)
        if self.textFade <= 0:
            return

        target = self.screen
        if self.textFade < 1:
            if self.textLayer is None:
                self.textLayer = pygame.Surface((self.screenSize, self.screenSize), pygame.SRCALPHA)
            self.textLayer.fill((0, 0, 0, 0))
            target = self.textLayer

        if self.textBandBottom is not None:
            # soft edges are centred on the band's edges, half inside and half out, so it reaches only a little
            # further than a hard one would (into the controls, at the bottom)
            feather = self.textBandFeather
            top, bottom = self.textBandTop + feather // 2, self.textBandBottom - feather // 2
            height = bottom - top
            if self.textBandSurface is None or self.textBandSurface.get_height() != height:
                self.textBandSurface = pygame.Surface((self.screenSize, height), pygame.SRCALPHA)
                self.textBandSurface.fill((0, 0, 0, self.textBandAlpha))
            target.blit(self.textBandSurface, (0, top))
            if feather > 0:
                edge = self.textBandEdge(feather)
                target.blit(edge, (0, top - feather))
                target.blit(pygame.transform.flip(edge, False, True), (0, bottom))
        for item in textItems:
            item.render(target)

        if target is self.textLayer:
            self.textLayer.set_alpha(int(255 * self.textFade))
            self.screen.blit(self.textLayer, (0, 0))

    # the band's soft edge: clear to its own darkness over text_band_feather pixels, eased so there's no line
    def textBandEdge(self, height):
        if height not in self.textBandEdges:
            surf = pygame.Surface((self.screenSize, height), pygame.SRCALPHA)
            for y in range(height):
                t = (y + 0.5) / height
                t = t * t * (3 - 2 * t)
                pygame.draw.line(surf, (0, 0, 0, int(self.textBandAlpha * t)), (0, y), (self.screenSize, y))
            self.textBandEdges[height] = surf
        return self.textBandEdges[height]

    # the artist, or the album for album_show_time of each cycle, faded out and in at the swaps
    def artistOrAlbum(self, trackInfo, deltaTime):
        track = (trackInfo.title, trackInfo.artist, trackInfo.album)
        if track != self.artistAlbumTrack:
            self.artistAlbumTrack = track
            self.artistAlbumTime = 0.0
        if not trackInfo.album or trackInfo.album == trackInfo.artist:
            self.artistTextItem.setAlpha(self.artistAlpha)
            return self.artistTextItem

        fade = self.artistAlbumFadeTime
        cycle = self.artistShowTime + self.albumShowTime + 4 * fade
        self.artistAlbumTime = (self.artistAlbumTime + deltaTime) % cycle
        t = self.artistAlbumTime
        albumStart = self.artistShowTime + fade         # artist faded out, album fading in
        albumEnd = albumStart + fade + self.albumShowTime + fade    # album faded out, artist fading in
        if albumStart <= t < albumEnd:
            item, alpha = self.albumTextItem, self.albumAlpha
            sinceIn, untilOut = t - albumStart, albumEnd - t
        else:
            item, alpha = self.artistTextItem, self.artistAlpha
            sinceIn = t - albumEnd if t >= albumEnd else t + fade   # the first showing starts already faded in
            untilOut = albumStart - t if t < albumStart else cycle - t + albumStart
        if fade > 0:
            alpha = int(alpha * min(1.0, sinceIn / fade, untilOut / fade))
        item.setAlpha(alpha)
        return item

    def textBandTapped(self, position):
        return (self.textBandBottom is not None and self.textBandTop is not None and self.buttonsVisible()
                and self.textBandTop <= position[1] <= self.textBandBottom)

    # one or two lines of title sit on track_text_bottom, so the artist and album under it never move
    def placeTitle(self):
        item = self.trackTextItem
        # at least one line's worth, so the band keeps its shape with no title
        height = max(item.blockHeight(), item.fontHeight)
        lift = 0 if item.requiresSplit else self.textBandSingleLinePadding
        if self.trackTextBottom is not None:
            item.posCenter = (item.posCenter[0], self.trackTextBottom - lift - height // 2)
            self.artistTextItem.posCenter = (self.artistTextItem.posCenter[0], self.artistBaseY - lift)
            self.albumTextItem.posCenter = (self.albumTextItem.posCenter[0], self.albumBaseY - lift)
        self.textBandTop = item.posCenter[1] - height // 2 - self.textBandPadding - lift
        # prev/next level with the title's middle: between its lines when it has two
        if self.skipButtonsFollowTitle:
            for button in (self.prevButton, self.nextButton):
                button.moveCenter((button.rect.centerx, item.posCenter[1]))

    # the track's art, else the playing favorite's fallback_art
    def pickTrackArt(self, trackInfo):
        key = (trackInfo.album_art_url, trackInfo.favorite)
        if key == self.trackArtKey:
            return
        self.trackArtKey = key
        self.fetchAlbumArt(trackInfo.album_art_url)
        path = self.fallbackArt.get(trackInfo.favorite)
        if self.trackArtSurface is None and path:
            try:
                self.trackArtSurface = self.scaleArt(pygame.image.load(path))
                self.trackArtUrl = path
            except Exception as e:
                self.wpStatus.logSilent(f"Failed to load fallback art {path}: {e}")

    def renderTrackInfoStreaming(self,trackInfo, deltaTime):
        self.pickTrackArt(trackInfo)

        self.renderTrackArt()

        self.trackTextItem.setText(self.streamTitle(trackInfo))
        self.artistTextItem.setText(self.streamStatus(trackInfo) or trackInfo.artist)
        self.albumTextItem.setText(trackInfo.album)
        self.albumTextItem.setScrollMode('scrolling')
        self.placeTitle()
        
        self.speakerTextItem.setText(trackInfo.device_string)
        self.speakerTextItem.setScrollMode('truncate')

        self.trackTextItem.update(deltaTime)
        self.artistTextItem.update(deltaTime)
        self.albumTextItem.update(deltaTime)
        self.speakerTextItem.update(deltaTime)

        self.renderTextBand(deltaTime, (self.trackTextItem, self.artistOrAlbum(trackInfo, deltaTime)))
        self.speakerTextItem.render(self.screen)

    # a stopped stream has no title, and a starting one says ZPSTR_BUFFERING or ZPSTR_CONNECTING:
    # show the station's favorite name instead
    def streamTitle(self, trackInfo):
        title = trackInfo.title or ''
        if title.startswith('ZPSTR_'):
            title = ''
        if not title and trackInfo.radio:
            title = trackInfo.favorite
        return title

    # Sonos's ZPSTR_BUFFERING, ZPSTR_CONNECTING... as words, shown under the station name while it tunes in
    def streamStatus(self, trackInfo):
        title = trackInfo.title or ''
        if not title.startswith('ZPSTR_'):
            return ''
        return title[len('ZPSTR_'):].replace('_', ' ').capitalize() + '...'

    def buttonsVisible(self):
        return self.wpStatus.appState == WpAppState.CONNECTED and self.wpStatus.latestTrackInfo is not None

    # line-in can play/pause but has no tracks to skip
    def skipButtonsVisible(self):
        return self.buttonsVisible() and not self.wpStatus.latestTrackInfo.line_in

    # a radio stream has no tracks to skip or shuffle either: shown greyed out
    def canSkip(self):
        return self.skipButtonsVisible() and not self.wpStatus.latestTrackInfo.radio

    def updateButtonVisibility(self):
        show = self.buttonsVisible()
        playing = show and self.wpStatus.latestTrackInfo.isPlaying()
        self.nextButton.setVisible(self.skipButtonsVisible())
        self.prevButton.setVisible(self.skipButtonsVisible())
        self.playButton.setVisible(show and not playing)
        self.pauseButton.setVisible(playing)
        # dimmed and ignoring taps until the speaker has done what was last asked, so taps can't pile up
        ready = not self.wpStatus.commandsBusy()
        # line-in and radio have no queue to shuffle: shown greyed out rather than leaving a gap in the row
        canShuffle = self.canSkip()
        shuffleOn = canShuffle and bool(self.wpStatus.shuffle)
        self.shuffleOnButton.setVisible(shuffleOn)
        self.shuffleOffButton.setVisible(show and not shuffleOn)
        for button in (self.nextButton, self.prevButton, self.playButton, self.pauseButton,
                       self.shuffleOnButton, self.shuffleOffButton):
            button.setEnabled(ready)
        self.shuffleOffButton.setEnabled(ready and canShuffle)
        self.nextButton.setEnabled(ready and canShuffle)
        self.prevButton.setEnabled(ready and canShuffle)
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
        self.trackArtKey = None

        self.renderTrackArt()

        self.trackTextItem.setText(self.lineInTrackName)
        self.placeTitle()
        self.trackTextItem.update(deltaTime)
        self.renderTextBand(deltaTime, (self.trackTextItem,))
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


    # wpStatus.status is the step the Sonos thread is on, written to be read on the screen
    def renderConnecting(self, deltaTime):
        failed = self.wpStatus.appState == WpAppState.NO_CONNECTION
        headline = "Not connected" if failed else "Connecting..."
        room = self.wpStatus.mainRoom or self.configMainRoom
        self.commandFeedback.update(deltaTime)
        self.commandFeedback.renderConnecting(self.screen, room, headline, self.wpStatus.status, failed)


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
            # below the shifted image the reflection has faded to near black
            bgOffsetY = 0 if self.artFullScreen else self.artPosY + self.artSize//2 - self.bgHorizonY
            self.screen.fill((0, 0, 0))
            self.screen.blit(self.bgImage, (0, bgOffsetY))
        else:
            self.screen.fill((128, 128, 128)) 

        # figure out if we are connected
        if (self.wpStatus.appState != WpAppState.CONNECTED):
            self.renderConnecting(deltaTime)
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
        self._draw_centered_text("No", (255,255,255), shadow=True, yPos = (self.screenSize // 2 + self.logTop) // 2, font=self.uiHeaderFont)
        pygame.draw.rect(self.screen, (60, 60, 60), pygame.Rect(0, self.logTop, self.screenSize, self.resyncTop - self.logTop))
        self._draw_centered_text("Log", (255,255,255), shadow=True, yPos = (self.logTop + self.resyncTop) // 2, font=self.uiHeaderFont)
        pygame.draw.rect(self.screen, (25, 55, 85), pygame.Rect(0, self.resyncTop, self.screenSize, self.screenSize - self.resyncTop))
        self._draw_centered_text("Fix screen", (255,255,255), shadow=True, yPos = self.resyncTop + 45, font=self.uiHeaderFont)

    def openFavorites(self):
        self.displayState = WpDisplayState.FAVORITES
        self.favsSlideTarget = 1.0
        self.favContentDisplay.pickShuffleArt()

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
        self.favsClockButton.render(panel)

    def isPlaying(self):
        trackInfo = self.wpStatus.latestTrackInfo
        return self.wpStatus.appState == WpAppState.CONNECTED and trackInfo is not None and trackInfo.isPlaying()

    def openClock(self):
        self.favsSlide = self.favsSlideTarget = 0.0
        self.clockSawStopped = not self.isPlaying()
        self.displayState = WpDisplayState.CLOCK

    # counts only while now playing is up with nothing playing (or not connected); any tap starts it over
    def updateIdle(self, deltaTime):
        if self.displayState != WpDisplayState.INFO or self.isPlaying():
            self.idleTime = 0.0
            return
        self.idleTime += deltaTime
        if self.idleTime >= self.clockIdleTime:
            self.openClock()

    def updateClock(self):
        if not self.isPlaying():
            self.clockSawStopped = True
        elif self.clockSawStopped:
            self.closeClock()

    # the clock fades out over whatever is underneath, over clock_fade_time
    def closeClock(self):
        self.idleTime = 0.0
        self.displayState = WpDisplayState.INFO
        self.clockFade = 1.0

    def renderClockFade(self, deltaTime):
        if self.clockFade <= 0:
            return
        self.clockDisplay.render(self.clockLayer)
        self.clockLayer.set_alpha(int(255 * self.clockFade))
        self.screen.blit(self.clockLayer, (0, 0))
        # a slow frame (the first draw of now playing after a while) moves the fade one normal step, not a jump
        step = min(deltaTime, 1 / 20)
        self.clockFade = max(0.0, self.clockFade - (step / self.clockFadeTime if self.clockFadeTime > 0 else 1.0))

    def drawRoomsPanel(self, panel):
        title = self.roomsDisplay.title()
        self._draw_centered_text(title, (255,255,255), shadow=True, yPos = 60, font=self.uiHeaderFont, surface=panel)
        # not while picking the main room: that title is too wide to fit it beside
        self.roomsRefreshButton.setVisible(not self.roomsDisplay.choosingMain)
        if self.roomsRefreshButton.visible:
            titleRight = self.screenSize // 2 + self.uiHeaderFont.size(title)[0] // 2
            self.roomsRefreshButton.moveCenter((titleRight + self.roomsRefreshGap + self.roomsRefreshButton.rect.width // 2, 60))
            self.roomsRefreshButton.setEnabled(not self.wpStatus.roomsRefreshRequested)
            self.roomsRefreshButton.render(panel)
        self.roomsDisplay.render(panel)
        self.favsBackButton.render(panel)
        self.roomsDisplay.renderVolume(panel)

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
        self.updateIdle(deltaTime)
        if self.displayState == WpDisplayState.CLOCK:
            self.updateClock()
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
        elif self.displayState == WpDisplayState.LOG:
            self.logView.render(self.screen)
            self.favsBackButton.render(self.screen)
        elif self.displayState == WpDisplayState.CLOCK:
            self.clockDisplay.render(self.screen)
        self.renderClockFade(deltaTime)

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
        self.idleTime = 0.0

        if self.displayState == WpDisplayState.CLOCK:
            # a tap only wakes it: back to now playing (or the connecting screen, which keeps retrying)
            self.closeClock()
        elif self.displayState == WpDisplayState.QUIT_CONFIRM:
            self.handleTapConfirm(position)
        elif self.displayState == WpDisplayState.LOG:
            # the down arrow, or anywhere but the page arrows, goes back
            if not self.logView.checkPageTap(position):
                self.displayState = WpDisplayState.INFO
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
        if self.textBandTapped(position):
            self.textHidden = not self.textHidden
            return
        # while connecting there's nothing else to tap and no hint where the hold area is, so hold anywhere
        if self.quitHoldRect.collidepoint(position) or self.wpStatus.appState != WpAppState.CONNECTED:
            self.quitHoldElapsed = 0.0

    def handleRelease(self, position):
        self.quitHoldElapsed = None
        if self.displayState == WpDisplayState.VOLUME:
            self.displayState = WpDisplayState.INFO
        elif self.displayState == WpDisplayState.ROOMS:
            self.roomsDisplay.release()

    def handleMotion(self, position):
        if self.displayState == WpDisplayState.VOLUME:
            self.volumeDial.motion(position)
        elif self.displayState == WpDisplayState.ROOMS:
            self.roomsDisplay.motion(position)

    def handleTapFavorites(self, position):
        # button rects are in panel coordinates, which only match the screen once fully open
        if self.favsSliding():
            return

        if self.favsBackButton and self.favsBackButton.check_tap(position):
            self.closeFavorites()
        elif self.favsRefreshButton and self.favsRefreshButton.check_tap(position):
            self.wpStatus.requestFavsRefresh()
        elif self.favsClockButton.check_tap(position):
            self.openClock()
        elif self.favContentDisplay.checkPageTap(position):
            pass
        elif self.favContentDisplay.checkTileTap(position):
            self.closeFavorites()

    def handleTapRooms(self, position):
        if self.favsSliding():
            return
        if self.roomsDisplay.volumeOpen():
            # the release went missing (e.g. dropped touch event); a new touch closes the bar
            self.roomsDisplay.closeVolume()
            return
        if self.favsBackButton.check_tap(position):
            self.closeFavorites()
        elif self.roomsDisplay.checkPageTap(position):
            pass
        elif self.roomsDisplay.checkSetMainTap(position):
            pass
        # after Set main, which wins the corner where their tap areas meet
        elif self.roomsRefreshButton.check_tap(position):
            self.wpStatus.requestResync()
        elif self.roomsDisplay.checkVolumePress(position):
            pass
        else:
            self.roomsDisplay.checkRowTap(position)

    def handleTapConfirm(self, position):
        if position[1] >= self.resyncTop:
            self.displayState = WpDisplayState.INFO
            self.resyncDisplay()
        elif position[1] >= self.logTop:
            self.logView.reset()
            self.displayState = WpDisplayState.LOG
        elif position[1] > self.screenSize//2:
            self.displayState = WpDisplayState.INFO
        else:
            self.displayState = WpDisplayState.QUITTING

    # runs in the background: the mode switch blanks the panel for a moment, and the app keeps drawing meanwhile
    def resyncDisplay(self):
        if not sys.platform.startswith('linux'):
            self.wpStatus.log("Fix screen: only on the Pi", logging.INFO)
            return
        try:
            subprocess.Popen(['sh', os.path.abspath(self.resyncScript)], stdin=subprocess.DEVNULL)
            self.wpStatus.log(f"Fix screen: ran {self.resyncScript}", logging.INFO)
        except Exception as e:
            self.wpStatus.log(f"Fix screen failed: {e}", logging.ERROR)

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
                    # testing how the clock reads over different covers
                    elif event.key == pygame.K_RIGHT and self.displayState == WpDisplayState.CLOCK:
                        self.clockDisplay.skipArt()

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