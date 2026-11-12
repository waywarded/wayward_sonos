import soco
import logging
from wp_app_status import WPAppStatus, WpAppState
from wp_config import WPConfig
import threading
from dataclasses import dataclass
import time
import queue

from soco.core import DidlPlaylistContainer

# dev aid: stands in for a Sonos favorite (--fake_favs); no reference, so playing it does nothing
@dataclass
class FakeFav:
    title: str
    reference: object = None


@dataclass
class NowPlayingInfo:
    title: str = "Unknown Title"
    artist: str = "Unknown Artist"
    album: str = "Unknown Album"
    album_art_url: str = ""
    transport_state: str = "STOPPED"
    line_in: bool = False
    device_string :str = ""

    @classmethod
    def fromTrackInfo(cls, trackInfo, lineIn = False, transportState = 'STOPPED', deviceString = ""):
        return cls(
            title=trackInfo.get("title", "Unknown Title"),
            artist=trackInfo.get("artist", "Unknown Artist"),
            album=trackInfo.get("album", "Unknown Album"),
            album_art_url=trackInfo.get("album_art", ""),
            transport_state=transportState,
            line_in = lineIn,
            device_string=deviceString
        )

    def isPlaying(self):
        return self.transport_state == 'PLAYING'


class WPSoco:

    def __init__(self, config, appStatus, fakeFavCount=None):
        self.config = config
        self.fakeFavCount = fakeFavCount
        self.lastFavsFetchTime = 0
        self.status : WPAppStatus = appStatus
        self.mainDevice = None
        self.mainHouseholdDevices = []
        self.coordinator = None
        self.sub = None
        self.status.subscribeToButtonEvent('transport', self.handleTransportEvent)
        self.status.subscribeToButtonEvent('content', self.handleContentEvent)

    def discoverDevices(self):
        self.status.updateStatus("Sonos discovery...")
        self.status.updateAppState(WpAppState.CONNECTING)
        self.status.log("Discovering Sonos devices on the network...", logging.INFO)

        mainDeviceName = self.config.mainDeviceName()
        self.mainDevice = None
        self.mainHouseholdDevices = []
        self.status.log('start discovery...')
        devices = soco.discover(timeout=5)
        self.status.log('done with discovery...')
        if not devices:
            self.status.log("No Sonos devices found.", logging.WARNING)
            return

        self.status.logSilent(f"Devices: {[d.player_name for d in devices]}", logging.INFO)

        for device in devices:
            if device.player_name == mainDeviceName:
                self.mainDevice = device
                self.status.log(f"Found '{mainDeviceName}'", logging.INFO)
                self.status.updateStatus(f"Found '{mainDeviceName}'")
                return

        self.status.log(f"Device '{mainDeviceName}' not found.", logging.WARNING)

    def listHouseholdDevices(self):
        self.status.logSilent("-----Devices on main household-----")
        if self.mainHouseholdDevices is None or len(
                self.mainHouseholdDevices) < 1:
            self.status.log("No devices found in main group")
            return

        for device in self.mainHouseholdDevices:
            if device == self.mainDevice:
                self.status.log(f" - {device.player_name} (Main)")
            else:
                self.status.log(f" - {device.player_name}")

    def configureGroups(self):
        mainDeviceName = self.config.mainDeviceName()
        mainDevice = self.mainDevice
        mainHouseholdDevices = self.mainHouseholdDevices
        householdCount = len(mainHouseholdDevices)

        if mainDevice is None:
            self.status.log(
                f"Main device '{mainDeviceName}' not found in any household. Please check your configuration.",
                logging.ERROR)
            self.status.updateStatus("Main device not found...")
            return

        self.status.updateStatus(f"Configuring Groups ('{mainDeviceName}')...")

        return
        self.status.log(
            f"Unjoining main device '{mainDeviceName}' from any existing groups...",
            logging.INFO)

        mainDevice.unjoin(
        )  # Ensure the main device is not grouped with others

        for requiredDeviceName in self.config.getRequiredDevices():
            if requiredDeviceName == mainDeviceName:
                continue  # Skip the main device since it's already set up

            if requiredDeviceName not in [
                    device.player_name for device in mainHouseholdDevices
            ]:
                self.status.log(
                    f"Required device '{requiredDeviceName}' not found in the same household as the main device. Please check your configuration.",
                    logging.WARNING)
                continue

            requiredDevice = [
                device for device in mainHouseholdDevices
                if device.player_name == requiredDeviceName
            ][0]
            self.status.log(
                f"Adding required device '{requiredDeviceName}' to the group with main device '{mainDeviceName}'...",
                logging.INFO)
            requiredDevice.join(mainDevice)

    def fetchState(self):
        if self.mainDevice is None:
            self.status.log(
                "Cannot fetch state because main device is not set.",
                logging.ERROR)
            return

        coordinator = self.mainDevice.group.coordinator
        lineIn = False
        if coordinator and coordinator.is_playing_line_in:
            lineIn = True

        transportInfo = coordinator.get_current_transport_info()
        print(f'transport info:{transportInfo}')
        transportState = transportInfo['current_transport_state'] if transportInfo else 'STOPPED'

        # get all speakers attached to main device group
        deviceStr = ""
        devSet = set()
        for dev in self.mainDevice.group:
            devSet.add(dev.player_name)

        if len(devSet) > 1:
            deviceStr = f"{self.mainDevice.player_name} [+{str(len(devSet)-1)}]"
        else:
            deviceStr = self.mainDevice.player_name

        self.status.logSilent(f"current device group:{deviceStr}")

        try:
            currentVolume = self.mainCoordinator().volume
            currentTrack = self.mainCoordinator().get_current_track_info()
            self.status.logSilent(f"------")
            self.status.log(
                f"Fetched current state from main device '{self.mainDevice.player_name}': {str(currentTrack)}",
                logging.INFO)
            self.status.logSilent(f"------")
            self.status.log(
                f"Current state - Volume: {currentVolume}, Track: {currentTrack.get('title', 'Unknown')}",
                logging.INFO)
            self.status.setTrackInfo(
                NowPlayingInfo.fromTrackInfo(currentTrack,
                                             lineIn,
                                             transportState,
                                             deviceString=deviceStr))
            return True
        except Exception as e:
            self.status.log(f"Error fetching state: {e}", logging.ERROR)
            return False

    def fetchFavs(self):
        self.lastFavsFetchTime = time.time()
        # set fetching before clearing the request so the refresh button never flickers back on mid-fetch
        self.status.favsFetching = True
        self.status.favsRefreshRequested = False
        try:
            self._fetchFavs()
        finally:
            self.status.favsFetching = False

    def _fetchFavs(self):
        newFavs = {}
        if self.fakeFavCount is not None:
            for i in range(self.fakeFavCount):
                title = f"Fake Favorite {i+1}"
                newFavs[title] = FakeFav(title)
        else:
            sonos_favs = self.mainCoordinator().music_library.get_sonos_favorites()
            for fav in sonos_favs:
                print(f"title: {fav.title}")
                print(f"ref: {fav.reference}")
                print(f"resources: {fav.resources}")
                newFavs[fav.title] = fav
        # titles show right away; art fills in once downloaded
        self.status.setFavs(newFavs)
        if self.fakeFavCount is None:
            self.status.favArt.update(newFavs, self.mainCoordinator().music_library.build_album_art_full_uri)

    # favorites get edited from the phone app; refresh on request and on a slow timer
    def checkFavsRefresh(self, favsRefreshTime):
        if self.status.appState != WpAppState.CONNECTED:
            return
        if not self.status.favsRefreshRequested and time.time() - self.lastFavsFetchTime < favsRefreshTime:
            return
        try:
            self.fetchFavs()
        except Exception as e:
            self.status.log(f"Error fetching favorites: {e}", logging.ERROR)

    def fetchInitialState(self):
        if self.mainDevice is None:
            self.status.log(
                "Cannot fetch initial state because main device is not set.",
                logging.ERROR)
            self.status.updateStatus("Main device not found...")
            self.status.updateAppState(WpAppState.NO_CONNECTION)
            return

        self.fetchState()
        self.status.requestVolumeRead()
        try:
            self.fetchFavs()
        except Exception as e:
            self.status.log(f"Error fetching favorites: {e}", logging.ERROR)
        self.status.updateStatus(
            f"Attached to '{self.mainDevice.player_name}'")

    def tryConnect(self):
        try:
            if self.sub:
                try:
                    self.sub.unsubscribe()
                except:
                    pass
            self.sub = None

            self.status.updateStatus("Attempting Connection")
            self.status.updateAppState(WpAppState.CONNECTING)
            self.discoverDevices()
            self.configureGroups()
            self.fetchInitialState()

            if self.mainDevice is not None:
                self.status.log(
                    f"Subscribing to Sonos events for main device '{self.mainDevice.player_name}'...",
                    logging.INFO)
                print("get coordinator")
                self.coordinator = self.mainDevice.group.coordinator
                self.sub = self.coordinator.avTransport.subscribe()
                self.status.updateAppState(WpAppState.CONNECTED)
            else:
                self.sub = None
                self.status.updateAppState(WpAppState.NO_CONNECTION)
        except Exception as e:
            self.status.log(f'TRYCONNECT EXCEPTION: {e}')
            self.sub = None
            self.status.updateAppState(WpAppState.NO_CONNECTION)

    def checkConnection(self):
        # self.status.logSilent(f"Checking connection...")

        if self.mainDevice is None or self.mainCoordinator() is None:
            self.status.logSilent(f"No device - NO CONNECTION...")
            self.sub = None
            return False

        try:
            self.mainCoordinator().get_speaker_info(refresh=True, timeout=2.0)
        except Exception as e:
            self.status.logSilent(f"Connection check exception: {str(e)}")
            return False

        # self.status.log("OK.")
        return True

    def socoThread(self):
        self.tryConnect()

        reconnectTimeOut = self.config.getSubkey("connection",
                                                "reconnect_time", 10)
        reconnectTimer = 0
        doCheckConnection = False
        favsRefreshTime = self.config.getSubkey("connection", "favs_refresh_time", 600)

        while True:
            doCheckConnection = False

            if self.sub is None:
                time.sleep(reconnectTimeOut)
                self.tryConnect()
                continue

            if not self.sub is None:
                try:
                    event = self.sub.events.get(timeout=1)
                    if event:
                        self.status.log(f"Received Sonos event: {event}",
                                        logging.INFO)
                        if self.fetchState():
                            doCheckConnection = False
                except queue.Empty:
                    # Timeout or other exception, just continue to wait for events
                    doCheckConnection = False
                    pass
                except Exception as e:
                    self.status.log(
                        f"Exception (non-timeout) in event loop.  Checking connection"
                    )
                    doCheckConnection = True

            time.sleep(1)

            self.checkFavsRefresh(favsRefreshTime)

            # If we think we have a connection, let's ping and make sure it's still there
            if self.status.appState == WpAppState.CONNECTED and doCheckConnection:
                connected = self.checkConnection()
                if not connected:
                    self.status.updateAppState(WpAppState.NO_CONNECTION)

            # If we lost our connection, start or update restart timer
            if self.status.appState != WpAppState.CONNECTED:
                reconnectTimer += 2
                self.status.updateStatus(
                    f"Retry in {str(reconnectTimeOut - reconnectTimer)}")
                if reconnectTimer > reconnectTimeOut:
                    self.tryConnect()
                    reconnectTimer = 0


    def start(self):
        self.status.updateStatus("Starting Sonos discovery thread...")
        t = threading.Thread(target=self.socoThread, daemon=True)
        t.start()
        v = threading.Thread(target=self.volumeThread, daemon=True)
        v.start()

    # separate from socoThread, which can sit in an event wait or a favorites fetch for seconds;
    # the volume dial needs its changes sent within a fraction of a second
    def volumeThread(self):
        while True:
            self.checkVolume()
            time.sleep(0.05)

    def checkVolume(self):
        if self.status.appState != WpAppState.CONNECTED or self.mainDevice is None:
            self.status.takeVolumeTarget()  # drop it: don't apply a stale level after reconnecting
            return
        try:
            target = self.status.takeVolumeTarget()
            if target is not None:
                # not group.volume's setter: it re-snapshots on every call, and Sonos uses the snapshot to keep
                # speakers' relative levels through a change, so take it once per dial session (the read below)
                coordinator = self.mainDevice.group.coordinator
                coordinator.groupRenderingControl.SetGroupVolume(
                    [("InstanceID", 0), ("DesiredVolume", max(0, min(int(target), 100)))])
                self.status.groupVolume = target
            elif self.status.volumeReadRequested:
                self.status.volumeReadRequested = False
                self.status.groupVolume = self.mainDevice.group.volume   # also snapshots the group volume
        except Exception as e:
            self.status.log(f"Volume exception: {e}", logging.ERROR)

    def handleTransportEvent(self,**kwargs):
        print (f'transport event: {kwargs}')

        try:
            if self.status.appState == WpAppState.CONNECTED and not (self.sub is None) and not (self.mainDevice is None):
                control = kwargs.get('control','')
                started = time.monotonic()
                coordinator = self.timedCall('coordinator lookup', self.mainCoordinator)
                match control:
                    case 'play':
                        self.timedCall('play', coordinator.play)
                    case 'pause':
                        self.timedCall('pause', coordinator.pause)
                    case 'next':
                        self.timedCall('next', coordinator.next)
                    case 'prev':
                        self.timedCall('prev', coordinator.previous)
                    case 'vol_up':
                        self.timedCall('vol_up', lambda: coordinator.set_relative_volume(10))
                    case 'vol_down':
                        self.timedCall('vol_down', lambda: coordinator.set_relative_volume(-10))
                    case 'play_fav':
                        print(f'play fav:')
                self.logTiming(f'{control} total', started)
        except Exception as e:
            self.status.log(f"Exception sending command {e}")


    def handleContentEvent(self,**kwargs):
        print (f'content event: {kwargs}')

        try:
            if self.status.appState == WpAppState.CONNECTED and not (self.sub is None) and not (self.mainDevice is None):
                control = kwargs.get('control','')
                params = kwargs.get('params')
                match control:
                    case 'play_fav':
                        print(f'play fav:{params}')
                        if params and 'fav' in params:
                            fav = params['fav']

                            print(fav.__dict__)
                            if fav.reference:
                                print('fav_ref:')
                                print(fav.reference.__dict__)
                                started = time.monotonic()
                                coordinator = self.timedCall('coordinator lookup', self.mainCoordinator)
                                self.timedCall('clear_queue', coordinator.clear_queue)
                                self.timedCall('add_to_queue', lambda: coordinator.add_to_queue(fav.reference))
                                self.timedCall('play_from_queue', lambda: coordinator.play_from_queue(0))
                                time.sleep(.5)
                                self.timedCall('fetchState', self.fetchState)
                                self.logTiming(f'play_fav {fav.title} total', started)
        except Exception as e:
            self.status.log(f"Exception sending command {e}")


    # temporary: finding out which Sonos calls make taps slow on the Pi (grep "Sonos timing" in logs/app.log)
    def timedCall(self, label, call):
        started = time.monotonic()
        try:
            return call()
        finally:
            self.logTiming(label, started)

    def logTiming(self, label, started):
        self.status.logSilent(f"Sonos timing: {label} took {time.monotonic() - started:.2f}s ({threading.current_thread().name})")

    def mainCoordinator(self):
        print("get coordinator")
        if self.mainDevice is None:
            return None
        return self.mainDevice.group.coordinator