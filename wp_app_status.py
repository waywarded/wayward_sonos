import logging
from enum import Enum
from wp_app_state import WpAppState

class WPAppStatus:
	def __init__(self):
		self.status = "Uninitialized"
		self.appState = WpAppState.UNINITIALIZED
		self.lastLogMessage = ""
		self.latestTrackInfo = None

	def updateStatus(self, newStatus):
		self.status = newStatus
		logging.info(f'-------App status: {self.status}-------')

	def updateAppState(self, newState : WpAppState):
		self.appState = newState
		logging.info(f'---------APP STATE: {str(self.appState)}--------')

	def setTrackInfo(self, trackInfo):
		self.latestTrackInfo = trackInfo
		logging.info(f'Updated track info: {trackInfo}')

	def log(self, message, logLevel=logging.INFO, display = True):
		self.lastLogMessage = message
		logging.log(logLevel, message)
		# TODO: display log message in UI if display == True
	
	def logSilent(self, message, logLevel=logging.INFO):
		self.lastLogMessage = message
		logging.log(logLevel, message)
