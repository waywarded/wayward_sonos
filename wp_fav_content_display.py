import pygame
from wp_app_status import WpAppStatus,WpAppState

class WpFavContentDisplay:
    def __init__(self, config, wpStatus):
        self.config = config
        self.wpStatus = wpStatus

    # build a grid of wp_display_buttons from the favorite content in wpStatus.sonosFavs dict
    def setupDisplay(self):
        self.displayButtons = []

    