import soco
import yaml
from wp_config import WPConfig
from wp_app_status import WPAppStatus
from wp_display import WPDisplay
from wp_soco import WPSoco
import logging

from soco.discovery import scan_network

def main():
	logging.basicConfig(level=logging.INFO)
	wpStatus = WPAppStatus()

	# Load config
	wpStatus.updateStatus("Initializing...")
	wpConfig = WPConfig("config.yaml")
	wpStatus.log("Configuration loaded.", logging.INFO)
	wpStatus.logSilent("Required Devices: " + str(wpConfig.getRequiredDevices()), logging.INFO)

	# Initialize display
	wpDisplay = WPDisplay(wpConfig, wpStatus)
	wpStatus.log("Display initialized.", logging.INFO)

	# initialize soco thread.
	wpSoco = WPSoco(wpConfig, wpStatus)
	wpSoco.start()

	# run UI loop
	wpDisplay.run()


if __name__ == "__main__":
	main()