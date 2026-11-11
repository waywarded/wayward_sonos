import pygame
import math
from wp_app_status import WPAppStatus
from wp_display_button import WPDisplayButton
from wp_button_label import renderButtonLabel

class WpFavContentDisplay:
    def __init__(self, config, wpStatus, parent):
        self.config = config
        self.wpStatus : WPAppStatus = wpStatus
        self.parent = parent

        self.columns = config.getSubkey('layout', 'favs_grid_columns', 3)
        self.rows = config.getSubkey('layout', 'favs_grid_rows', 3)
        self.tileSize = config.getSubkey('layout', 'favs_tile_size', 120)
        self.tileGap = config.getSubkey('layout', 'favs_tile_gap', 15)
        self.gridCenterY = config.getSubkey('layout', 'favs_grid_center_y', parent.screenSize//2)
        self.tileColor = config.getSubkey('layout', 'favs_tile_color', [50, 70, 50])
        self.initialsFontSizes = config.getSubkey('layout', 'favs_initials_font_sizes', [44])
        self.initialsFontAsset = config.getSubkey('layout', 'favs_initials_font_asset', 'assets/PublicSans-Bold.ttf')
        self.labelHeight = config.getSubkey('layout', 'favs_label_height', 24)
        self.labelFont = parent.getFontForElement('favs_label')
        self.labelColor = config.getSubkey('layout', 'favs_label_color', [255, 255, 255])

        hitPadding = config.getSubkey('layout', 'button_hit_padding', 20)
        self.prevPageButton = WPDisplayButton(
            config.getSubkey('layout', 'favs_prev_page_pos', [50, 320]),
            config.getSubkey('layout', 'favs_prev_page_size', [30, 30]),
            config.getSubkey('layout', 'favs_prev_page_asset', 'assets/PrevTrackBtn.png'),
            hitPadding=hitPadding
        )
        self.nextPageButton = WPDisplayButton(
            config.getSubkey('layout', 'favs_next_page_pos', [650, 320]),
            config.getSubkey('layout', 'favs_next_page_size', [30, 30]),
            config.getSubkey('layout', 'favs_next_page_asset', 'assets/NextTrackBtn.png'),
            hitPadding=hitPadding
        )

        self.page = 0
        self.favs = None        # the sonosFavs dict the tiles were built from
        self.artVersion = -1    # favArt.version the tiles were built with
        self.favList = []       # [(title, fav)] in Sonos order
        self.tiles = []         # [(button, fav)] for the current page

    def perPage(self):
        return self.columns * self.rows

    def pageCount(self):
        return max(1, math.ceil(len(self.favList) / self.perPage()))

    # rebuild when the Sonos thread swaps in a new favorites dict or new art, or the page changes
    def checkFavs(self):
        if self.favs is self.wpStatus.sonosFavs and self.artVersion == self.wpStatus.favArt.version:
            return
        self.favs = self.wpStatus.sonosFavs
        self.artVersion = self.wpStatus.favArt.version
        self.favList = list(self.favs.items())
        self.page = min(self.page, self.pageCount() - 1)
        self.setupDisplay()

    # build a grid of wp_display_buttons for the current page
    def setupDisplay(self):
        self.tiles = []
        screenSize = self.parent.screenSize
        # each tile is the art square with its name underneath
        tileHeight = self.tileSize + self.labelHeight
        gridWidth = self.columns * self.tileSize + (self.columns - 1) * self.tileGap
        gridHeight = self.rows * tileHeight + (self.rows - 1) * self.tileGap
        left = screenSize//2 - gridWidth//2
        top = self.gridCenterY - gridHeight//2

        first = self.page * self.perPage()
        for i, (title, fav) in enumerate(self.favList[first:first + self.perPage()]):
            col = i % self.columns
            row = i // self.columns
            pos = [left + col * (self.tileSize + self.tileGap), top + row * (tileHeight + self.tileGap)]
            button = WPDisplayButton(pos, [self.tileSize, tileHeight], self.makeTileSurface(title, self.wpStatus.favArt.getImage(fav)))
            self.tiles.append((button, fav))

        self.prevPageButton.setVisible(self.page > 0)
        self.nextPageButton.setVisible(self.page < self.pageCount() - 1)

    # art square (or initials until the art arrives) with the name underneath; the whole tile is tappable
    def makeTileSurface(self, title, image=None):
        size = (self.tileSize, self.tileSize)
        if image is None:
            art = renderButtonLabel(size, self.initials(title), fontSizes=self.initialsFontSizes, bgColor=tuple(self.tileColor),
                                    fontPath=self.initialsFontAsset)
        else:
            art = image.resize(size)

        surf = pygame.Surface((self.tileSize, self.tileSize + self.labelHeight), pygame.SRCALPHA)
        surf.blit(pygame.image.frombytes(art.tobytes(), size, 'RGB'), (0, 0))
        text = self.labelFont.render(self.fitLabel(title), True, self.labelColor)
        surf.blit(text, text.get_rect(center=(self.tileSize//2, self.tileSize + self.labelHeight//2)))
        return surf

    # first two letters or digits, so "µ-Ziq Radio" gives "µZ"
    def initials(self, title):
        letters = [c for c in title if c.isalnum()]
        return ''.join(letters[:2]) if letters else '?'

    def fitLabel(self, title):
        if self.labelFont.size(title)[0] <= self.tileSize:
            return title
        text = title
        while text and self.labelFont.size(text + '...')[0] > self.tileSize:
            text = text[:-1]
        return text.rstrip() + '...'

    def render(self, screen):
        self.checkFavs()
        if not self.favList:
            self.parent._draw_centered_text("No favorites", (255,255,255), shadow=True, font=self.parent.uiHeaderFont, surface=screen)
            return

        for button, fav in self.tiles:
            button.render(screen)
        self.prevPageButton.render(screen)
        self.nextPageButton.render(screen)

    def checkPageTap(self, position) -> bool:
        if self.prevPageButton.check_tap(position):
            self.page -= 1
            self.setupDisplay()
            return True
        if self.nextPageButton.check_tap(position):
            self.page += 1
            self.setupDisplay()
            return True
        return False

    # plays the tapped favorite; returns True so the display can go back to now playing
    def checkTileTap(self, position) -> bool:
        for button, fav in self.tiles:
            if button.check_tap(position):
                self.wpStatus.dispatchEvent('content', control='play_fav', params={'fav': fav})
                return True
        return False
