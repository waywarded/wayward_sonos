import soco
import logging
from wp_app_status import WPAppStatus, WpAppState
from wp_config import WPConfig
import threading
from dataclasses import dataclass
import time
import queue

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

    def __init__(self, config, appStatus):
        self.config = config
        self.status : WPAppStatus = appStatus
        self.mainDevice = None
        self.mainHouseholdDevices = []
        self.coordinator = None
        self.sub = None
        self.status.subscribeToButtonEvent('transport', self.handleTransportEvent)

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

        transportInfo = self.mainDevice.get_current_transport_info()
        transportState = transportInfo[
            'current_transport_state'] if transportInfo else 'STOPPED'

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
            currentVolume = self.mainDevice.volume
            currentTrack = self.mainDevice.get_current_track_info()
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

    def fetchInitialState(self):
        if self.mainDevice is None:
            self.status.log(
                "Cannot fetch initial state because main device is not set.",
                logging.ERROR)
            self.status.updateStatus("Main device not found...")
            self.status.updateAppState(WpAppState.NO_CONNECTION)
            return

        self.fetchState()
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

        if self.mainDevice is None or self.coordinator is None:
            self.status.logSilent(f"No device - NO CONNECTION...")
            self.sub = None
            return False

        try:
            self.mainDevice.get_speaker_info(refresh=True, timeout=2.0)
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

    def handleTransportEvent(self,**kwargs):
        print (f'transport event: {kwargs}')

        try:
            if self.status.appState == WpAppState.CONNECTED and not (self.sub is None) and not (self.mainDevice is None):
                control = kwargs.get('control','')
                match control:
                    case 'play':
                        self.mainDevice.play()
                    case 'pause':
                        self.mainDevice.pause()
                    case 'next':
                        self.mainDevice.next()
                    case 'prev':
                        self.mainDevice.previous()
                    case 'vol_up':
                        self.mainDevice.set_relative_volume(10)
                    case 'vol_down':
                        self.mainDevice.set_relative_volume(-10)
        except Exception as e:
            self.status.log(f"Exception sending command {e}")