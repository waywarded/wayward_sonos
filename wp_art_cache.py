import hashlib
import logging
import os


# the most recent album art shown, kept on disk for the clock to cycle through. named by the image's own hash, so
# every track of an album (each with its own art URL) is one file
class WpArtCache:
    def __init__(self, folder, count=40):
        self.folder = folder
        self.count = count

    def save(self, data):
        if self.count <= 0 or not data:
            return
        try:
            os.makedirs(self.folder, exist_ok=True)
            ext = '.png' if data[:8] == b'\x89PNG\r\n\x1a\n' else '.jpg'
            path = os.path.join(self.folder, hashlib.sha1(data).hexdigest() + ext)
            if os.path.exists(path):
                os.utime(path)      # seen again: back to the front of the line
            else:
                with open(path, 'wb') as f:
                    f.write(data)
            self.prune()
        except OSError as e:
            logging.debug(f"Art cache: couldn't save: {e}")

    def prune(self):
        for path in self.paths()[self.count:]:
            try:
                os.remove(path)
            except OSError:
                pass

    # newest first
    def paths(self):
        try:
            names = [n for n in os.listdir(self.folder) if n.endswith(('.jpg', '.png'))]
        except OSError:
            return []
        paths = [os.path.join(self.folder, n) for n in names]
        return sorted(paths, key=lambda p: os.path.getmtime(p) if os.path.exists(p) else 0, reverse=True)
