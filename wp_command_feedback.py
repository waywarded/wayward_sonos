import pygame
import math
import time
from wp_app_status import WPAppStatus
from wp_display_button import WPDisplayButton

# Dims the whole screen while a tapped favorite is being started (it can take a while), with Cancel, or briefly
# when it failed. Uses the same tile as the favorites grid, so you see what you tapped. While it's up it takes
# every tap, so nothing underneath can be pressed.
class WpCommandFeedback:
    def __init__(self, config, wpStatus, parent):
        self.config = config
        self.wpStatus : WPAppStatus = wpStatus
        self.parent = parent

        size = parent.screenSize
        self.center = (size // 2, config.getSubkey('layout', 'album_art_y', size // 2))
        dimAlpha = config.getSubkey('layout', 'command_feedback_dim_alpha', 220)
        self.dimSurface = pygame.Surface((size, size), pygame.SRCALPHA)
        self.dimSurface.fill((0, 0, 0, dimAlpha))

        self.spinnerRadius = config.getSubkey('layout', 'command_feedback_spinner_radius', 105)
        self.spinnerDots = 12
        self.spinnerSpeed = 1.0     # turns per second
        self.textColor = config.getSubkey('layout', 'command_feedback_text_color', [255, 255, 255])
        self.failColor = config.getSubkey('layout', 'command_feedback_fail_color', [230, 90, 70])
        self.failShowTime = config.getSubkey('layout', 'command_feedback_fail_time', 4.0)
        self.font = parent.uiHeaderFont

        self.cancelButton = WPDisplayButton(
            config.getSubkey('layout', 'command_feedback_cancel_pos', [280, 555]),
            config.getSubkey('layout', 'command_feedback_cancel_size', [160, 50]),
            self.makeCancelSurface(config.getSubkey('layout', 'command_feedback_cancel_size', [160, 50])),
            hitPadding=config.getSubkey('layout', 'button_hit_padding', 20)
        )

        self.spin = 0.0
        self.tileFav = None         # the fav the tile surface was made for
        self.tileArtVersion = -1
        self.tile = None

    def tileFor(self, title, fav):
        # rebuild when the fav changes or its art arrives
        if fav is not self.tileFav or self.tileArtVersion != self.wpStatus.favArt.version:
            self.tileFav = fav
            self.tileArtVersion = self.wpStatus.favArt.version
            self.tile = self.parent.favContentDisplay.makeTileSurface(title, self.wpStatus.favArt.getImage(fav))
        return self.tile

    def makeCancelSurface(self, size):
        surf = pygame.Surface(size, pygame.SRCALPHA)
        # solid fill so the dimmed text underneath doesn't show through
        pygame.draw.rect(surf, (25, 25, 25), surf.get_rect(), border_radius=size[1] // 2)
        pygame.draw.rect(surf, (255, 255, 255), surf.get_rect(), width=2, border_radius=size[1] // 2)
        text = self.font.render("Cancel", True, self.textColor)
        surf.blit(text, text.get_rect(center=(size[0] // 2, size[1] // 2)))
        return surf

    def active(self):
        return self.wpStatus.startingFav is not None or self.showingFailure()

    # taps never reach the screen underneath while this is up
    def handleTap(self, position):
        if self.wpStatus.startingFav is not None:
            if self.cancelButton.check_tap(position):
                self.wpStatus.requestCancel()
        else:
            self.wpStatus.commandFailure = None     # any tap dismisses the failure

    def showingFailure(self):
        failure = self.wpStatus.commandFailure
        return failure is not None and time.monotonic() - failure[1] <= self.failShowTime

    def update(self, deltaTime):
        self.spin = (self.spin + deltaTime * self.spinnerSpeed) % 1.0

    def render(self, screen):
        starting = self.wpStatus.startingFav
        failed = starting is None and self.showingFailure()
        if starting is None and not failed:
            return

        screen.blit(self.dimSurface, (0, 0))

        if starting:
            title, fav = starting
            self.renderTile(screen, self.tileFor(title, fav))
            self.renderSpinner(screen)
            self.renderText(screen, "Starting...", self.textColor)
            self.cancelButton.render(screen)
        else:
            # the tile already names the favorite, so the message can stay short
            if self.tile is not None:
                self.renderTile(screen, self.tile)
            self.renderText(screen, "Couldn't play", self.failColor)

    def renderTile(self, screen, tile):
        # art and name together, centred in the ring
        screen.blit(tile, tile.get_rect(center=self.center))

    def renderSpinner(self, screen):
        # dots fade behind the leading one as it goes round clockwise
        for i in range(self.spinnerDots):
            a = 2 * math.pi * (i / self.spinnerDots + self.spin)
            fade = (i + 1) / self.spinnerDots
            color = [int(c * fade) for c in self.textColor]
            pos = (self.center[0] + self.spinnerRadius * math.cos(a), self.center[1] + self.spinnerRadius * math.sin(a))
            pygame.draw.circle(screen, color, pos, 3 + 3 * fade)

    def renderText(self, screen, text, color):
        y = self.center[1] + self.spinnerRadius + 35
        self.parent._draw_centered_text(text, color, shadow=True, yPos=y, font=self.font, surface=screen)
