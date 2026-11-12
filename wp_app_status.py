import logging
import threading
import time
from enum import Enum
from wp_app_state import WpAppState
from wp_fav_art import WPFavArtCache


class WPAppStatus:

    def __init__(self):
        self.status = "Uninitialized"
        self.appState = WpAppState.UNINITIALIZED
        self.lastLogMessage = ""
        self.latestTrackInfo = None
        self.buttonEventListeners : dict = {}
        self.sonosFavs = {}
        self.favsRefreshRequested = False
        self.favsFetching = False
        self.favArt = WPFavArtCache()
        self.serviceNames = {}          # {service id: name}, from the speakers; fetched once with the favorites
        self.shuffle = None             # main group's shuffle, from the speaker's events; None until one arrives

        # group volume of the main device; the volume dial asks, the Sonos volume worker does the network calls
        self.groupVolume = None
        self.volumeReadRequested = False
        self._volumeTarget = None
        self._volumeLock = threading.Lock()

        # Sonos commands run on their own thread; the display reads these to show the tap was seen
        self.commandsPending = 0      # queued or running
        self.startingFav = None       # (title, fav) while a favorite is being started
        self.commandFailure = None    # (message, time.monotonic()) of the last failed command
        self.cancelRequested = threading.Event()    # set by the Cancel button; the running favorite stops waiting
        self._commandLock = threading.Lock()

    def updateStatus(self, newStatus):
        self.status = newStatus
        logging.info(f'-------App status: {self.status}-------')

    def updateAppState(self, newState: WpAppState):
        self.appState = newState
        logging.info(f'---------APP STATE: {str(self.appState)}--------')

    def setTrackInfo(self, trackInfo):
        self.latestTrackInfo = trackInfo
        logging.info(f'Updated track info: {trackInfo}')

    def log(self, message, logLevel=logging.INFO, display=True):
        self.lastLogMessage = message
        logging.log(logLevel, message)
        # TODO: display log message in UI if display == True

    def logSilent(self, message, logLevel=logging.INFO):
        self.lastLogMessage = message
        logging.log(logLevel, message)

    def subscribeToButtonEvent(self, eventName, handler):
        if not eventName in self.buttonEventListeners:
            self.buttonEventListeners[eventName] = []
        self.buttonEventListeners[eventName].append(handler)

    def clearButtonEventSubs(self):
        self.buttonEventListeners.clear()
        
    def dispatchEvent(self, eventName, **kwargs):
        if eventName in self.buttonEventListeners:
            for listener in self.buttonEventListeners[eventName]:
                listener(**kwargs)

    # swap in a whole new dict: other threads iterate sonosFavs, so never mutate it in place
    def setFavs(self, newFavs : dict):
        self.sonosFavs = newFavs

    # the display can't wait on the network, so it asks and the Sonos thread does the fetch
    def requestFavsRefresh(self):
        self.favsRefreshRequested = True

    def requestVolume(self, volume):
        with self._volumeLock:
            self._volumeTarget = volume

    # hands the latest requested volume to the worker exactly once; anything requested before it is superseded
    def takeVolumeTarget(self):
        with self._volumeLock:
            volume = self._volumeTarget
            self._volumeTarget = None
            return volume

    def requestVolumeRead(self):
        self.volumeReadRequested = True

    def favsRefreshPending(self):
        return self.favsRefreshRequested or self.favsFetching

    def commandQueued(self, startingFav=None):
        with self._commandLock:
            self.commandsPending += 1
            if startingFav is not None:
                self.startingFav = startingFav
                self.commandFailure = None

    def commandFinished(self):
        with self._commandLock:
            self.commandsPending -= 1
            if self.commandsPending == 0:
                self.startingFav = None

    # the speaker carries on with whatever it was asked; the app just stops waiting and won't press play
    def requestCancel(self):
        self.cancelRequested.set()
        self.startingFav = None

    def commandFailed(self, message):
        self.commandFailure = (message, time.monotonic())

    def commandsBusy(self):
        return self.commandsPending > 0
