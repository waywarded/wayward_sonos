import pygame

class WPDisplayButton:
    # init button with position, size, image asset and callback
    def __init__(self, pos, size, image):
        self.rect = pygame.Rect(pos[0],pos[1],size[0],size[1])
        # image is an asset path or an already-built surface (e.g. a favorites tile)
        img_data = pygame.image.load(image) if isinstance(image, str) else image
        self.button_surface = pygame.transform.scale(img_data, (size[0], size[1]))
        self.visible = True

    def setVisible(self, visible):
        self.visible = visible

    def render(self, screen):
        if self.visible:
            screen.blit(self.button_surface, self.rect)
        

    # hidden buttons can't be tapped
    def check_tap(self, position) -> bool:
        return self.visible and self.rect.collidepoint(position)

    