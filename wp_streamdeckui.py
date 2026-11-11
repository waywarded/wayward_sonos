import threading
import time
import logging
import requests
from io import BytesIO

import StreamDeck
from StreamDeck.DeviceManager import DeviceManager
from StreamDeck.ImageHelpers import PILHelper
from PIL import Image
from wp_app_status import WPAppStatus, WpAppState
from wp_button_label import renderButtonLabel

class WPStreamDeckUI:

    def __init__(self, config, appStatus):
        self.config = config
        self.status : WPAppStatus = appStatus
        self.running = False
        self.deckDevice: StreamDeck | None = None
        self.commandButtons = {}
        self.contentButtons = {}
        self.prevPlayAsset = ''

    def connectAndMonitor(self):
        while self.running:
            if self.deckDevice is None or not self.deckDevice.connected():
                self.deckDevice = None
                self._tryConnect()
                time.sleep(5)
            else:
                self._updateTransportButtons()
                self._setupFavButtons()
            time.sleep(1)

    def _tryConnect(self):
        if not (self.deckDevice is None) and self.deckDevice.connected():
            return

        try:
            allDecks = DeviceManager().enumerate()
            if not allDecks:
                print('no streamdeck devices found')
                return
            self.deckDevice = allDecks[0]
            self.deckDevice.open()
            self.deckDevice.set_brightness(80)
            self.deckDevice.set_key_callback(self.onKey)
        except Exception as e:
            self.deckDevice = None
            logging.warning(f"failed to connect to streamdeck device: {e}")
            return
        self._setupTransportButtons()
        self._setupFavButtons()

    def _setupButton(self, buttonId, imagePath, command, params, isCommand = True):
        if self.deckDevice is None:
            return

        print(f'{imagePath}')
        img = Image.open(imagePath).convert('RGB')
        target_size = self.deckDevice.key_image_format()['size']
        logging.info(f'target_size: {target_size}')
        img = img.resize(target_size)

        # convert to deck format
        nativeImg = PILHelper.to_native_format(self.deckDevice, img)
        self.deckDevice.set_key_image(buttonId, nativeImg)

        if isCommand:
            self.commandButtons[buttonId] = {'command':command,'params':params}
        else:
            self.contentButtons[buttonId] = {'command':command,'params':params}


    def _setupButtonWithLabel(self, buttonId, image, label, command, params, isCommand):
        if self.deckDevice is None:
            return

        target_size = self.deckDevice.key_image_format()['size']

        img = renderButtonLabel(target_size, label, image)
        
        nativeImg = PILHelper.to_native_format(self.deckDevice, img)
        self.deckDevice.set_key_image(buttonId, nativeImg)

        if isCommand:
            self.commandButtons[buttonId] = {'command': command, 'params': params}
        else:
            self.contentButtons[buttonId] = {'command': command, 'params': params}


    def _setupTransportButtons(self):
        self.commandButtons.clear()

        asset = self.config.getSubkey('deck', 'vol_up_button_asset')
        self._setupButton(4, asset, 'vol_up', [])

        asset = self.config.getSubkey('deck', 'vol_down_button_asset')
        self._setupButton(0, asset, 'vol_down', [])

        asset = self.config.getSubkey('deck', 'play_button_asset')
        self._setupButton(2, asset, 'play', [])

        asset = self.config.getSubkey('deck', 'next_button_asset')
        self._setupButton(3, asset, 'next', [])

        asset = self.config.getSubkey('deck', 'prev_button_asset')
        self._setupButton(1, asset, 'prev', [])


    def _setupFavButtons(self):
        self.contentButtons.clear()
        if self.status is None:
            return

        buttonId = 5
        for fav in self.status.sonosFavs.keys():
            # img = self._get_image_from_fav(self.status.sonosFavs[fav])
            # TODO: cache images using the above so we don't fetch them every single time.
            img = None
            self._setupButtonWithLabel(buttonId, img, fav, 'play_fav', {'fav' : self.status.sonosFavs[fav]}, False)
            buttonId += 1

    

    def _get_image_from_fav(self, fav):
        url = getattr(fav, 'album_art_uri', None)
        if not url:
            return None
        try:
            response = requests.get(url, timeout=3)
            response.raise_for_status()
            img = Image.open(BytesIO(response.content)).convert('RGB')
            return img
        except Exception as e:
            logging.warning(f"Failed to fetch art for {fav.title}: {e}")
            return None        

    def _updateTransportButtons(self):
        if self.deckDevice is None:
            return

        playAsset = self.config.getSubkey('deck', 'play_button_asset')
        pauseAsset = self.config.getSubkey('deck', 'pause_button_asset')

        if self.status is None or self.status.appState != WpAppState.CONNECTED or self.status.latestTrackInfo is None:
            # not connected
            self.deckDevice.set_brightness(40)
            self._setupButton(2, playAsset, 'play', [])
            return

        self.deckDevice.set_brightness(80)
        trackInfo = self.status.latestTrackInfo
        if trackInfo.isPlaying():
            if self.prevPlayAsset != pauseAsset:
                self._setupButton(2, pauseAsset, 'pause', [])
                self.prevPlayAsset = pauseAsset
        else:
            if self.prevPlayAsset != playAsset:
                self._setupButton(2, playAsset, 'play', [])
                self.prevPlayAsset = playAsset

    def onKey(self, deck, key, state):
        logging.info(f'streamdeck key: {key}, {state}')
        if key in self.commandButtons:
            print(f'command: {self.commandButtons[key]}')
            if state != 0 and not self.status is None:
                self.status.dispatchEvent('transport',control = self.commandButtons[key].get('command',''))
        elif key in self.contentButtons:
            print(f'content: {self.contentButtons[key]}')
            if state != 0 and not self.status is None:
                self.status.dispatchEvent('content',control = self.contentButtons[key].get('command',''), params = self.contentButtons[key].get('params',{}))


    def start(self):
        self.status.updateStatus("Starting Streamdeck thread...")
        self.running = True
        t = threading.Thread(target=self.connectAndMonitor, daemon=True)
        t.start()

