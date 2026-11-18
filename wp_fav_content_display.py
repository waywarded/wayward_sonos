import pygame
import math
import os
import random
from wp_app_status import WPAppStatus
from wp_display_button import WPDisplayButton
from wp_button_label import renderButtonLabel
from PIL import Image
from wp_soco import favServiceId, isLibraryFav, isRadioFav, LineInFav, ShuffleFav

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
        self.services = config.getSubkey('favorites', 'services', {})
        self.libraryIcon = config.getSubkey('favorites', 'library_icon', None)
        self.sonosPlaylistIcon = config.getSubkey('favorites', 'sonos_playlist_icon', None)
        self.unknownServiceIcon = config.getSubkey('favorites', 'unknown_service_icon', None)
        self.badgeSize = config.getSubkey('layout', 'favs_service_badge_size', 30)
        self.badgeColor = config.getSubkey('layout', 'favs_service_badge_color', [20, 20, 20])
        self.badgeFont = parent.getFontForElement('favs_service_badge')
        self.badges = {}        # badge key (service id, 'library' or None) -> surface or None, made once
        self.sortLast = config.getSubkey('favorites', 'sort_last', [])

        # first tile, when the room config names the speaker whose line-in to play
        self.lineInFav = None
        self.lineInImage = None
        lineInDevice = config.get('line_in_device')
        if lineInDevice:
            self.lineInFav = LineInFav(config.getSubkey('display', 'line_in_track_name', 'Line-In'), lineInDevice)
            imagePath = config.getSubkey('display', 'line_in_track_image', 'assets/lineIn01.png')
            if os.path.exists(imagePath):
                self.lineInImage = Image.open(imagePath).convert('RGB')

        # after the line-in tile: a random shuffle of each genre, then each artist, in the music library.
        # art comes from its folder in favorites.genre_image_dir / artist_image_dir (named after it unless
        # genre_folders / artist_folders say otherwise); one image picked at random each time the screen opens.
        # Without images a genre shows its initials and an artist one of its album covers
        self.shuffleFavs = []
        self.shuffleImages = {}     # {(kind, title): [images]}, scaled to the tile once so a folder of photos stays small
        for kind, default in (('genre', 'assets/genres'), ('artist', 'assets/artists')):
            imageDir = config.getSubkey('favorites', f'{kind}_image_dir', default)
            folders = config.getSubkey('favorites', f'{kind}_folders', {})
            for title in config.getSubkey('favorites', f'{kind}s', []):
                fav = ShuffleFav(title, kind)
                self.shuffleFavs.append(fav)
                self.shuffleImages[(kind, title)] = self.loadImages(os.path.join(imageDir, folders.get(title, title)))
        self.shuffleArt = {}        # {(kind, title): image} shown until the screen next opens; picked in pickShuffleArt
        self.fallbackArt = {}       # {favorite title: image} for favorites Sonos has no art for (favorites.fallback_art)
        for title, path in (config.getSubkey('favorites', 'fallback_art', {}) or {}).items():
            if os.path.exists(path):
                self.fallbackArt[title] = Image.open(path).convert('RGB').resize((self.tileSize, self.tileSize))

        hitPadding = config.getSubkey('layout', 'button_hit_padding', 20)
        self.prevPageButton = WPDisplayButton(
            config.getSubkey('layout', 'favs_prev_page_pos', [50, 320]),
            config.getSubkey('layout', 'favs_prev_page_size', [30, 30]),
            config.getSubkey('layout', 'favs_prev_page_asset', 'assets/PagePrevBtn.png'),
            hitPadding=hitPadding
        )
        self.nextPageButton = WPDisplayButton(
            config.getSubkey('layout', 'favs_next_page_pos', [650, 320]),
            config.getSubkey('layout', 'favs_next_page_size', [30, 30]),
            config.getSubkey('layout', 'favs_next_page_asset', 'assets/PageNextBtn.png'),
            hitPadding=hitPadding
        )

        self.page = 0
        self.favs = None        # the sonosFavs dict the tiles were built from
        self.artVersion = -1    # favArt.version the tiles were built with
        self.favList = []       # [(title, fav)] in Sonos order
        self.tiles = []         # [(button, fav)] for the current page
        self.pickShuffleArt()

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
        favs = list(self.favs.items())
        radio = [(title, fav) for title, fav in favs if isRadioFav(fav)]
        self.favList = self.sortByService([item for item in favs if item not in radio])
        # line-in, then radio stations, then the genre and artist shuffles, then the rest
        self.favList[0:0] = radio + [(fav.title, fav) for fav in self.shuffleFavs]
        if self.lineInFav is not None:
            self.favList.insert(0, (self.lineInFav.title, self.lineInFav))
        self.page = min(self.page, self.pageCount() - 1)
        self.setupDisplay()

    # what a favorite plays from: a service id, 'library' (SMB share) or None (saved Sonos playlists)
    def badgeKey(self, fav):
        if isinstance(fav, ShuffleFav):
            return 'library'
        serviceId = favServiceId(fav)
        if serviceId is not None:
            return serviceId
        return 'library' if isLibraryFav(fav) else None

    # services grouped by name, then the music library, then saved Sonos playlists, then the services in
    # favorites.sort_last (Apple Music: its playlists load slowly); Sonos order within a group
    def sortByService(self, favList):
        names = self.wpStatus.serviceNames
        def key(indexed):
            index, (title, fav) = indexed
            source = self.badgeKey(fav)
            if source in self.sortLast:
                return (3, names.get(source, f'service {source}'), index)
            if source is None:
                return (2, '', index)
            if source == 'library':
                return (1, '', index)
            return (0, names.get(source, f'service {source}'), index)
        return [item for index, item in sorted(enumerate(favList), key=key)]

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
            surface = self.makeTileSurface(title, self.tileImage(fav))
            if not isinstance(fav, LineInFav):
                self.drawServiceBadge(surface, self.badgeKey(fav))
            button = WPDisplayButton(pos, [self.tileSize, tileHeight], surface)
            self.tiles.append((button, fav))

        self.prevPageButton.setVisible(self.page > 0)
        self.nextPageButton.setVisible(self.page < self.pageCount() - 1)

    def tileImage(self, fav):
        if isinstance(fav, LineInFav):
            return self.lineInImage
        if isinstance(fav, ShuffleFav):
            image = self.shuffleArt.get((fav.kind, fav.title))
            if image is None and fav.kind == 'artist':
                image = self.wpStatus.favArt.images.get(self.wpStatus.artistArtUris.get(fav.title))
            return image
        return self.wpStatus.favArt.getImage(fav) or self.fallbackArt.get(fav.title)

    def loadImages(self, folder):
        if not os.path.isdir(folder):
            return []
        images = []
        for name in sorted(os.listdir(folder)):
            if name.lower().endswith(('.png', '.jpg', '.jpeg')):
                images.append(Image.open(os.path.join(folder, name)).convert('RGB').resize((self.tileSize, self.tileSize)))
        return images

    # called when the favorites screen opens, so a tile with several images shows a different one each time
    def pickShuffleArt(self):
        self.shuffleArt = {key: random.choice(images) for key, images in self.shuffleImages.items() if images}
        if self.favs is not None:
            self.setupDisplay()

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

    # bottom-right corner of the art square
    def drawServiceBadge(self, surface, key):
        badge = self.serviceBadge(key)
        if badge is not None:
            surface.blit(badge, badge.get_rect(bottomright=(self.tileSize - 4, self.tileSize - 4)))

    # key: a service id, 'library' or None (see badgeKey). A service gets its icon PNG if the file exists, else a
    # round badge with its short name; services without settings get the unknown icon. The library and saved
    # Sonos playlists get their icons if there are any.
    def serviceBadge(self, key):
        if key not in self.badges:
            self.badges[key] = self.makeBadge(key)
        return self.badges[key]

    def makeBadge(self, key):
        if key is None:
            return self.loadIcon(self.sonosPlaylistIcon)
        if key == 'library':
            return self.loadIcon(self.libraryIcon)
        settings = self.services.get(key, {})
        icon = self.loadIcon(settings.get('icon') if settings else self.unknownServiceIcon)
        if icon is not None:
            return icon
        name = self.wpStatus.serviceNames.get(key, '')
        short = settings.get('short') or ''.join(word[0] for word in name.split()[:2]).upper() or '?'
        badge = pygame.Surface((self.badgeSize, self.badgeSize), pygame.SRCALPHA)
        radius = self.badgeSize // 2
        pygame.draw.circle(badge, self.badgeColor, (radius, radius), radius)
        pygame.draw.circle(badge, (255, 255, 255), (radius, radius), radius, width=1)
        text = self.badgeFont.render(short, True, (255, 255, 255))
        badge.blit(text, text.get_rect(center=(radius, radius)))
        return badge

    def loadIcon(self, path):
        if not path or not os.path.exists(path):
            return None
        return pygame.transform.smoothscale(pygame.image.load(path).convert_alpha(), (self.badgeSize, self.badgeSize))

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
