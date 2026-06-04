import logging

class WPAppStatus:
	def __init__(self):
		self.status = "Uninitialized"
		self.lastLogMessage = ""
		self.latestTrackInfo = None

	def updateStatus(self, newStatus):
		self.status = newStatus
		logging.info(f'-------App status: {self.status}-------')

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
