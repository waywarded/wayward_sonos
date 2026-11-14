import pygame
import math
import time
from wp_app_status import WPAppStatus
from wp_display_button import WPDisplayButton

# the rooms screen: one row per speaker, the main room marked, the rooms grouped with it filled in.
# tapping a room adds it to the main room's group or takes it out; the main room itself can't be tapped.
# Set main switches to picking a new main room: the next room tapped becomes it (Cancel to back out)
class WpRoomsDisplay:
    def __init__(self, config, wpStatus, parent):
        self.config = config
        self.wpStatus : WPAppStatus = wpStatus
        self.parent = parent

        self.rowSize = config.getSubkey('layout', 'rooms_row_size', [340, 54])
        self.rowGap = config.getSubkey('layout', 'rooms_row_gap', 10)
        self.rowsPerPage = config.getSubkey('layout', 'rooms_rows', 7)
        self.listCenterY = config.getSubkey('layout', 'rooms_list_center_y', 365)
        self.memberColor = config.getSubkey('layout', 'rooms_member_color', [40, 90, 140])
        self.otherColor = config.getSubkey('layout', 'rooms_other_color', [45, 45, 45])
        self.textColor = config.getSubkey('layout', 'rooms_text_color', [255, 255, 255])
        self.font = parent.getFontForElement('rooms_name')
        self.tagFont = parent.getFontForElement('rooms_tag')
        self.failColor = config.getSubkey('layout', 'command_feedback_fail_color', [230, 90, 70])
        self.failShowTime = config.getSubkey('layout', 'command_feedback_fail_time', 4.0)
        self.pendingAlpha = config.getSubkey('layout', 'rooms_pending_alpha', 110)
        self.failureY = config.getSubkey('layout', 'rooms_failure_y', 606)     # between the list and the down button

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

        self.pillFont = parent.getFontForElement('rooms_set_main')
        setMainCenter = config.getSubkey('layout', 'rooms_set_main_pos', [360, 103])
        setMainSize = config.getSubkey('layout', 'rooms_set_main_size', [150, 40])
        self.setMainButton = WPDisplayButton([0, 0], setMainSize, self.makePillSurface(setMainSize, "Set main"), hitPadding=8)
        self.cancelButton = WPDisplayButton([0, 0], setMainSize, self.makePillSurface(setMainSize, "Cancel"), hitPadding=8)
        self.setMainButton.moveCenter(setMainCenter)
        self.cancelButton.moveCenter(setMainCenter)

        self.choosingMain = False
        self.builtChoosing = False  # choosingMain the rows were built with
        self.page = 0
        self.rooms = None       # the wpStatus.rooms list the rows were built from
        self.rows = []          # [(button, name, inGroup)] for the current page
        self.pending = None     # wpStatus.roomPending the rows were built with

    def pageCount(self):
        return max(1, math.ceil(len(self.rooms or []) / self.rowsPerPage))

    # rebuild when the Sonos thread swaps in a new rooms list
    def checkRooms(self):
        if (self.rooms is self.wpStatus.rooms and self.pending == self.wpStatus.roomPending
                and self.builtChoosing == self.choosingMain):
            return
        self.rooms = self.wpStatus.rooms
        self.pending = self.wpStatus.roomPending
        self.builtChoosing = self.choosingMain
        self.page = min(self.page, self.pageCount() - 1)
        self.setupDisplay()

    def setupDisplay(self):
        self.rows = []
        width, height = self.rowSize
        first = self.page * self.rowsPerPage
        pageRooms = self.rooms[first:first + self.rowsPerPage]
        listHeight = len(pageRooms) * height + (len(pageRooms) - 1) * self.rowGap
        top = self.listCenterY - listHeight // 2
        left = self.parent.screenSize // 2 - width // 2
        for i, (name, inGroup) in enumerate(pageRooms):
            surface = self.makeRowSurface(name, inGroup, name == self.wpStatus.mainRoom)
            button = WPDisplayButton([left, top + i * (height + self.rowGap)], self.rowSize, surface)
            # dimmed while it's being added or removed; the main room isn't tappable
            button.setEnabled(name != self.pending and name != self.wpStatus.mainRoom)
            button.disabled_surface.set_alpha(255 if name == self.wpStatus.mainRoom else self.pendingAlpha)
            self.rows.append((button, name, inGroup))

        self.prevPageButton.setVisible(self.page > 0)
        self.nextPageButton.setVisible(self.page < self.pageCount() - 1)

    # a pill: filled for rooms playing with the main room, outlined for the rest; 'Main' or a tick on the right
    def makeRowSurface(self, name, inGroup, isMain):
        width, height = self.rowSize
        radius = height // 2
        surf = pygame.Surface((width, height), pygame.SRCALPHA)
        rect = surf.get_rect()
        if inGroup:
            pygame.draw.rect(surf, self.memberColor, rect, border_radius=radius)
        else:
            pygame.draw.rect(surf, self.otherColor, rect, border_radius=radius)
            pygame.draw.rect(surf, self.memberColor, rect, width=2, border_radius=radius)

        markX = width - radius
        if isMain:
            tag = self.tagFont.render("MAIN", True, self.textColor)
            markX = width - radius // 2 - tag.get_width() // 2 - 6
            surf.blit(tag, tag.get_rect(center=(markX, height // 2)))
        else:
            self.drawTick(surf, (markX, height // 2), inGroup)

        nameWidth = markX - radius - 30
        text = self.font.render(self.fitText(name, nameWidth), True, self.textColor)
        surf.blit(text, text.get_rect(midleft=(radius, height // 2)))
        return surf

    # an empty ring, or a white disc with a tick when the room is in the group
    def makePillSurface(self, size, label):
        surf = pygame.Surface(size, pygame.SRCALPHA)
        pygame.draw.rect(surf, (25, 25, 25), surf.get_rect(), border_radius=size[1] // 2)
        pygame.draw.rect(surf, self.textColor, surf.get_rect(), width=2, border_radius=size[1] // 2)
        text = self.pillFont.render(label, True, self.textColor)
        surf.blit(text, text.get_rect(center=(size[0] // 2, size[1] // 2)))
        return surf

    def title(self):
        return "Pick the main room" if self.choosingMain else "Rooms"

    # opening the screen always starts in the normal mode
    def reset(self):
        self.choosingMain = False

    def drawTick(self, surf, center, ticked):
        size = 13
        if not ticked:
            pygame.draw.circle(surf, self.textColor, center, size, width=2)
            return
        pygame.draw.circle(surf, self.textColor, center, size)
        x, y = center
        pygame.draw.lines(surf, self.memberColor, False, [(x - 6, y), (x - 2, y + 5), (x + 6, y - 5)], width=3)

    def fitText(self, text, width):
        if self.font.size(text)[0] <= width:
            return text
        while text and self.font.size(text + '...')[0] > width:
            text = text[:-1]
        return text.rstrip() + '...'

    def render(self, screen):
        self.checkRooms()
        if not self.rooms:
            self.parent._draw_centered_text("No rooms found", (255,255,255), shadow=True, font=self.parent.uiHeaderFont, surface=screen)
            return
        for button, name, inGroup in self.rows:
            button.render(screen)
        self.prevPageButton.render(screen)
        self.nextPageButton.render(screen)
        # no switching while a room is being changed (or a main room switch is under way)
        canPick = len(self.rooms) > 1 and self.wpStatus.roomPending is None
        self.setMainButton.setVisible(canPick and not self.choosingMain)
        self.cancelButton.setVisible(self.choosingMain)
        self.setMainButton.render(screen)
        self.cancelButton.render(screen)
        failure = self.wpStatus.roomFailure
        if failure is not None and time.monotonic() - failure[1] <= self.failShowTime:
            self.parent._draw_centered_text(failure[0], self.failColor, shadow=True, yPos=self.failureY, font=self.font, surface=screen)

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

    def checkSetMainTap(self, position) -> bool:
        if self.setMainButton.check_tap(position):
            self.choosingMain = True
            self.wpStatus.roomFailure = None
            return True
        if self.cancelButton.check_tap(position):
            self.choosingMain = False
            return True
        return False

    def checkRowTap(self, position) -> bool:
        for button, name, inGroup in self.rows:
            if button.check_tap(position):
                self.wpStatus.roomFailure = None
                if self.choosingMain:
                    self.choosingMain = False
                    self.wpStatus.requestMainRoom(name)
                else:
                    self.wpStatus.dispatchEvent('room', room=name, join=not inGroup)
                return True
        return False
