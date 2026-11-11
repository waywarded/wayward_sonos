import pygame
import math
from wp_app_status import WPAppStatus
from wp_display_button import WPDisplayButton

class WpFavContentDisplay:
    def __init__(self, config, wpStatus, parent):
        self.config = config
        self.wpStatus : WPAppStatus = wpStatus
        self.parent = parent

        self.columns = config.getSubkey('layout', 'favs_grid_columns', 3)
        self.rows = config.getSubkey('layout', 'favs_grid_rows', 3)
        self.tileSize = config.getSubkey('layout', 'favs_tile_size', 140)
        self.tileGap = config.getSubkey('layout', 'favs_tile_gap', 15)
        self.gridCenterY = config.getSubkey('layout', 'favs_grid_center_y', parent.screenSize//2)
        self.tileColor = config.getSubkey('layout', 'favs_tile_color', [50, 70, 50])
        self.tileFont = parent.getFontForElement('favs_tile')

        self.prevPageButton = WPDisplayButton(
            config.getSubkey('layout', 'favs_prev_page_pos', [50, 320]),
            config.getSubkey('layout', 'favs_prev_page_size', [30, 30]),
            config.getSubkey('layout', 'favs_prev_page_asset', 'assets/PrevTrackBtn.png')
        )
        self.nextPageButton = WPDisplayButton(
            config.getSubkey('layout', 'favs_next_page_pos', [650, 320]),
            config.getSubkey('layout', 'favs_next_page_size', [30, 30]),
            config.getSubkey('layout', 'favs_next_page_asset', 'assets/NextTrackBtn.png')
        )

        self.page = 0
        self.favs = None        # the sonosFavs dict the tiles were built from
        self.favList = []       # [(title, fav)] in Sonos order
        self.tiles = []         # [(button, fav)] for the current page

    def perPage(self):
        return self.columns * self.rows

    def pageCount(self):
        return max(1, math.ceil(len(self.favList) / self.perPage()))

    # rebuild when the Sonos thread swaps in a new favorites dict, or the page changes
    def checkFavs(self):
        if self.favs is self.wpStatus.sonosFavs:
            return
        self.favs = self.wpStatus.sonosFavs
        self.favList = list(self.favs.items())
        self.page = min(self.page, self.pageCount() - 1)
        self.setupDisplay()

    # build a grid of wp_display_buttons for the current page
    def setupDisplay(self):
        self.tiles = []
        screenSize = self.parent.screenSize
        gridWidth = self.columns * self.tileSize + (self.columns - 1) * self.tileGap
        gridHeight = self.rows * self.tileSize + (self.rows - 1) * self.tileGap
        left = screenSize//2 - gridWidth//2
        top = self.gridCenterY - gridHeight//2

        first = self.page * self.perPage()
        for i, (title, fav) in enumerate(self.favList[first:first + self.perPage()]):
            col = i % self.columns
            row = i // self.columns
            pos = [left + col * (self.tileSize + self.tileGap), top + row * (self.tileSize + self.tileGap)]
            button = WPDisplayButton(pos, [self.tileSize, self.tileSize], self.makeTileSurface(first + i + 1))
            self.tiles.append((button, fav))

        self.prevPageButton.setVisible(self.page > 0)
        self.nextPageButton.setVisible(self.page < self.pageCount() - 1)

    # plain numbered tile until the label step
    def makeTileSurface(self, number):
        surf = pygame.Surface((self.tileSize, self.tileSize))
        surf.fill(self.tileColor)
        text = self.tileFont.render(str(number), True, (255, 255, 255))
        surf.blit(text, text.get_rect(center=(self.tileSize//2, self.tileSize//2)))
        return surf

    def render(self, screen):
        self.checkFavs()
        if not self.favList:
            self.parent._draw_centered_text("No favorites", (255,255,255), shadow=True, font=self.parent.uiHeaderFont)
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
