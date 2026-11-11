import logging
import requests
from io import BytesIO
from PIL import Image

# Favorite art shared by the Stream Deck keys and the on-screen favorites tiles.
# Keyed by the favorite's album_art_uri as Sonos reports it: an unchanged favorite never downloads
# again, and art for removed favorites is dropped so memory stays flat while the app runs for weeks.
class WPFavArtCache:
    def __init__(self):
        self.images = {}    # album_art_uri -> PIL image
        self.version = 0    # bumped when images change, so displays know to redraw

    # never blocks; None until the art has been downloaded
    def getImage(self, fav):
        url = getattr(fav, 'album_art_uri', None)
        if not url:
            return None
        return self.images.get(url)

    # runs on the Sonos thread after each favorites fetch.
    # buildFullUri turns relative /getaa?... links into http://<speaker>:1400/getaa?...
    def update(self, favs : dict, buildFullUri):
        newImages = {}
        changed = False
        for title, fav in favs.items():
            url = getattr(fav, 'album_art_uri', None)
            if not url:
                continue
            if url in self.images:
                newImages[url] = self.images[url]
                continue
            img = self.fetchImage(buildFullUri(url), title)
            if img is not None:
                newImages[url] = img
                changed = True

        if changed or len(newImages) != len(self.images):
            # swap in a whole new dict: other threads read images, so never mutate it in place
            self.images = newImages
            self.version += 1

    # moved from WPStreamDeckUI._get_image_from_fav
    def fetchImage(self, url, title):
        try:
            response = requests.get(url, timeout=3)
            response.raise_for_status()
            img = Image.open(BytesIO(response.content)).convert('RGB')
            return img
        except Exception as e:
            logging.warning(f"Failed to fetch art for {title}: {e}")
            return None
