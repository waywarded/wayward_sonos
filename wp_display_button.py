import pygame

class WPDisplayButton:
    # init button with position, size, image asset and callback
    def __init__(self, pos, size, image):
        self.rect = pygame.Rect(pos[0],pos[1],size[0],size[1])
        img_data = pygame.image.load(image)
        self.button_surface = pygame.transform.scale(img_data, (size[0], size[1]))

    def render(self, screen):
        screen.blit(self.button_surface, self.rect)
        

    def check_tap(self, position) -> bool:
        return self.rect.collidepoint(position)

    