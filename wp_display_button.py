import pygame

class WPDisplayButton:
    # init button with position, size, image asset and callback.
    # hitPadding grows the tap area around the art so small buttons are easy to hit on the touchscreen.
    def __init__(self, pos, size, image, hitPadding=0):
        self.rect = pygame.Rect(pos[0],pos[1],size[0],size[1])
        self.hitRect = self.rect.inflate(2 * hitPadding, 2 * hitPadding)
        # image is an asset path or an already-built surface (e.g. a favorites tile)
        img_data = pygame.image.load(image) if isinstance(image, str) else image
        self.button_surface = pygame.transform.scale(img_data, (size[0], size[1]))
        self.disabled_surface = self.button_surface.copy()
        self.disabled_surface.set_alpha(80)
        self.visible = True
        self.enabled = True
        self.backdrop = None        # a dark disc drawn centred under the button

    # a see-through dark disc behind the button, so it shows up on any album art
    def setBackdrop(self, padding, alpha):
        radius = max(self.rect.width, self.rect.height) // 2 + padding
        surf = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
        pygame.draw.circle(surf, (0, 0, 0, alpha), (radius, radius), radius)
        self.backdrop = surf

    # for buttons placed by their centre (the rooms screen's Set main)
    def moveCenter(self, center):
        padding = (self.hitRect.width - self.rect.width) // 2
        self.rect.center = (round(center[0]), round(center[1]))
        self.hitRect = self.rect.inflate(2 * padding, 2 * padding)

    def setVisible(self, visible):
        self.visible = visible

    def setEnabled(self, enabled):
        self.enabled = enabled

    def render(self, screen):
        if self.visible:
            if self.backdrop:
                screen.blit(self.backdrop, self.backdrop.get_rect(center=self.rect.center))
            screen.blit(self.button_surface if self.enabled else self.disabled_surface, self.rect)
        

    # hidden or disabled buttons can't be tapped
    def check_tap(self, position) -> bool:
        return self.visible and self.enabled and self.hitRect.collidepoint(position)

    