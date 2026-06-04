import soco
import logging
from wp_app_status import WPAppStatus
from wp_config import WPConfig
import threading
from dataclasses import dataclass
import time

@dataclass
class NowPlayingInfo:
	title: str = "Unknown Title"
	artist: str = "Unknown Artist"
	album: str = "Unknown Album"
	album_art_url: str = ""
	transport_state: str = "STOPPED"
	line_in: bool = False
	@classmethod
	def fromTrackInfo(cls, trackInfo, lineIn = False, transportState = 'STOPPED'):
		return cls(
			title=trackInfo.get("title", "Unknown Title"),
			artist=trackInfo.get("artist", "Unknown Artist"),
			album=trackInfo.get("album", "Unknown Album"),
			album_art_url=trackInfo.get("album_art", ""),
			transport_state=transportState,
			line_in = lineIn
		)
	
	def isPlaying(self):
		return self.transport_state == 'PLAYING'

class WPSoco:
	def __init__(self, config, appStatus):
		self.config = config
		self.status = appStatus
		self.mainDevice = None
		self.mainHouseholdDevices = []

	def discoverDevices(self):
		self.status.updateStatus("Sonos discovery...")
		self.status.log("Discovering Sonos households and devices on the network...",logging.INFO)

		# Find households on the network
		ids = soco.discovery.scan_network_get_household_ids()
		self.status.logSilent(str(ids), logging.INFO)


		# Discover Sonos devices on the network
		mainHouseholdDevices = []
		mainDeviceName = self.config.mainDeviceName()
		mainDevice = None
		deviceCount = 0
		for household in ids:
			self.status.updateStatus(f"Discovering devices on {household}...")
			devices = soco.discover(timeout=10, household_id=household)

			if not devices:
				self.status.log(f"No Sonos devices found in household {household}.", logging.WARNING)
				print("No Sonos devices found.")
			else:
				# Print the names of the discovered devices
				self.status.log(f"Discovered {len(devices)} Sonos devices in household {household}.", logging.INFO)
				self.status.logSilent(f"Devices: {[device.player_name for device in devices]}", logging.INFO)

				if mainDeviceName in [device.player_name for device in devices]:
					mainDevice = [device for device in devices if device.player_name == mainDeviceName][0]
					self.status.log(f"Main device '{mainDeviceName}' found: {mainDevice.player_name} in household {household}", logging.INFO)
					self.mainHouseholdDevices = devices
					deviceCount = deviceCount + 1
					break  # Stop searching after finding the main device
		
		
		self.mainDevice = mainDevice
		self.status.updateStatus(f"Sonos discovery complete ({str(deviceCount)} devices, {str(len(self.mainHouseholdDevices))} households).")
	
	def listHouseholdDevices(self):
		self.status.logSilent("-----Devices on main household-----")
		if self.mainHouseholdDevices is None or len(self.mainHouseholdDevices)<1:
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
			self.status.log(f"Main device '{mainDeviceName}' not found in any household. Please check your configuration.", logging.ERROR)
			self.status.updateStatus("Main device not found...")
			return

		self.status.updateStatus(f"Configuring Groups ('{mainDeviceName}')...")
		self.status.log(f"Unjoining main device '{mainDeviceName}' from any existing groups...", logging.INFO)

		return

		mainDevice.unjoin()  # Ensure the main device is not grouped with others

		for requiredDeviceName in self.config.getRequiredDevices():
			if requiredDeviceName == mainDeviceName:
				continue  # Skip the main device since it's already set up

			if requiredDeviceName not in [device.player_name for device in mainHouseholdDevices]:
				self.status.log(f"Required device '{requiredDeviceName}' not found in the same household as the main device. Please check your configuration.", logging.WARNING)
				continue
			
			requiredDevice = [device for device in mainHouseholdDevices if device.player_name == requiredDeviceName][0]
			self.status.log(f"Adding required device '{requiredDeviceName}' to the group with main device '{mainDeviceName}'...", logging.INFO)
			requiredDevice.join(mainDevice)



	def fetchState(self):
		if self.mainDevice is None:
			self.status.log("Cannot fetch state because main device is not set.", logging.ERROR)
			return
		
		coordinator = self.mainDevice.group.coordinator
		lineIn = False
		if coordinator and coordinator.is_playing_line_in:
			lineIn = True

		transportInfo = self.mainDevice.get_current_transport_info()
		transportState = transportInfo['current_transport_state'] if transportInfo else 'STOPPED'

		try:
			currentVolume = self.mainDevice.volume
			currentTrack = self.mainDevice.get_current_track_info()
			self.status.logSilent(f"------")
			self.status.log(f"Fetched current state from main device '{self.mainDevice.player_name}': {str(currentTrack)}", logging.INFO)
			self.status.logSilent(f"------")
			self.status.log(f"Current state - Volume: {currentVolume}, Track: {currentTrack.get('title', 'Unknown')}", logging.INFO)
			self.status.setTrackInfo(NowPlayingInfo.fromTrackInfo(currentTrack,lineIn,transportState))
		except Exception as e:
			self.status.log(f"Error fetching state: {e}", logging.ERROR)

	def fetchInitialState(self):
		if self.mainDevice is None:
			self.status.log("Cannot fetch initial state because main device is not set.", logging.ERROR)
			self.status.updateStatus("Main device not found...")
			return

		self.fetchState()
		self.status.updateStatus(f"Attached to '{self.mainDevice.player_name}'")

	def socoThread(self):
		self.discoverDevices()
		self.configureGroups()
		self.fetchInitialState()

		if self.mainDevice is not None:
			self.status.log(f"Subscribing to Sonos events for main device '{self.mainDevice.player_name}'...", logging.INFO)
			coordinator = self.mainDevice.group.coordinator
			sub = coordinator.avTransport.subscribe()

		while True:
			try:
				event = sub.events.get(timeout=1)
				if event:
					self.status.log(f"Received Sonos event: {event}", logging.INFO)
					self.fetchState()
			except Exception as e:
				# Timeout or other exception, just continue to wait for events
				pass
			time.sleep(1)

	def start(self):
		self.status.updateStatus("Starting Sonos discovery thread...")
		t = threading.Thread(target=self.socoThread, daemon=True)
		t.start()