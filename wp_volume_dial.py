import pygame
import math
from wp_app_status import WPAppStatus

# While the volume button is held, the whole round screen is a dial.
# Relative: turning clockwise from where the finger is raises the volume, counter-clockwise lowers it,
# so pressing never jumps the level.
class WpVolumeDial:
    def __init__(self, config, wpStatus, parent):
        self.config = config
        self.wpStatus : WPAppStatus = wpStatus
        self.parent = parent

        size = parent.screenSize
        self.center = (size // 2, size // 2)
        self.degreesForFullRange = config.getSubkey('layout', 'volume_dial_degrees', 270)
        self.deadZone = config.getSubkey('layout', 'volume_dial_dead_zone', 60)

        self.radius = config.getSubkey('layout', 'volume_dial_radius', 320)
        self.arcWidth = config.getSubkey('layout', 'volume_dial_width', 28)
        self.trackColor = config.getSubkey('layout', 'volume_dial_track_color', [70, 70, 70])
        self.levelColor = config.getSubkey('layout', 'volume_dial_level_color', [255, 255, 255])
        self.textColor = config.getSubkey('layout', 'volume_dial_text_color', [255, 255, 255])
        self.numberFont = parent.getFontForElement('volume_dial')
        self.labelFont = parent.getFontForElement('volume_dial_label')

        dimAlpha = config.getSubkey('layout', 'volume_dial_dim_alpha', 190)
        self.dimSurface = pygame.Surface((size, size), pygame.SRCALPHA)
        self.dimSurface.fill((0, 0, 0, dimAlpha))

        # the gauge runs clockwise from 7:30 to 4:30, like a stereo knob (screen angles: 0 = 3 o'clock, 90 = 6 o'clock)
        self.gaugeStart = 135
        self.gaugeSweep = 270

        self.volume = None          # float while the dial is up; None until Sonos has told us the level
        self.moved = False
        self.lastAngle = None
        self.lastRequested = None

    def begin(self, position):
        # fresh reading in case the volume was changed from the phone; shown until the finger moves
        self.wpStatus.requestVolumeRead()
        groupVolume = self.wpStatus.groupVolume
        self.volume = None if groupVolume is None else float(groupVolume)
        self.moved = False
        self.lastRequested = None
        self.lastAngle = self.angleOf(position) if not self.inDeadZone(position) else None

    def inDeadZone(self, position):
        return math.dist(position, self.center) < self.deadZone

    def angleOf(self, position):
        return math.degrees(math.atan2(position[1] - self.center[1], position[0] - self.center[0]))

    def motion(self, position):
        # near the center a small move swings the angle wildly, so ignore it and re-anchor when the finger leaves
        if self.inDeadZone(position):
            self.lastAngle = None
            return

        angle = self.angleOf(position)
        if self.lastAngle is None:
            self.lastAngle = angle
            return

        delta = (angle - self.lastAngle + 180) % 360 - 180   # shortest way round, so crossing 9 o'clock doesn't jump
        self.lastAngle = angle
        if self.volume is None:
            return

        # clamping the float (not just the sent value) means reversing at 0 or 100 responds immediately
        self.volume = max(0.0, min(100.0, self.volume + delta * 100.0 / self.degreesForFullRange))
        self.moved = True
        level = round(self.volume)
        if level != self.lastRequested:
            self.wpStatus.requestVolume(level)
            self.lastRequested = level

    def update(self, deltaTime):
        if not self.moved and self.wpStatus.groupVolume is not None:
            self.volume = float(self.wpStatus.groupVolume)

    def arcPoints(self, startDeg, sweepDeg, radius):
        steps = max(2, int(abs(sweepDeg) / 2))
        points = []
        for i in range(steps + 1):
            a = math.radians(startDeg + sweepDeg * i / steps)
            points.append((self.center[0] + radius * math.cos(a), self.center[1] + radius * math.sin(a)))
        return points

    # a thick arc as one polygon with round ends; pygame.draw.arc leaves gaps at this width
    def drawArc(self, screen, color, startDeg, sweepDeg):
        if sweepDeg <= 0:
            return
        outer = self.arcPoints(startDeg, sweepDeg, self.radius + self.arcWidth / 2)
        inner = self.arcPoints(startDeg, sweepDeg, self.radius - self.arcWidth / 2)
        pygame.draw.polygon(screen, color, outer + inner[::-1])
        for end in (self.arcPoints(startDeg, 0, self.radius)[0], self.arcPoints(startDeg + sweepDeg, 0, self.radius)[0]):
            pygame.draw.circle(screen, color, end, self.arcWidth / 2)

    def render(self, screen):
        screen.blit(self.dimSurface, (0, 0))

        self.drawArc(screen, self.trackColor, self.gaugeStart, self.gaugeSweep)
        if self.volume is not None:
            self.drawArc(screen, self.levelColor, self.gaugeStart, self.gaugeSweep * self.volume / 100.0)

        number = '--' if self.volume is None else str(round(self.volume))
        text = self.numberFont.render(number, True, self.textColor)
        screen.blit(text, text.get_rect(center=self.center))
        label = self.labelFont.render('Volume', True, self.textColor)
        screen.blit(label, label.get_rect(center=(self.center[0], self.center[1] - self.numberFont.get_height() // 2 - 10)))

        trackInfo = self.wpStatus.latestTrackInfo
        if trackInfo is not None and trackInfo.device_string:
            device = self.labelFont.render(trackInfo.device_string, True, self.textColor)
            screen.blit(device, device.get_rect(center=(self.center[0], self.center[1] + self.numberFont.get_height() // 2 + 10)))
