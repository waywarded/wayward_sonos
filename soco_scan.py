from soco.discovery import scan_network
from wp_soco import WPSoco
import logging
from wp_app_status import WPAppStatus
from wp_config import WPConfig

def main():
	logging.basicConfig(level=logging.INFO)
	wpStatus = WPAppStatus()

	# Load config
	wpStatus.updateStatus("Initializing...")
	wpConfig = WPConfig("config.yaml")
	wpStatus.log("Configuration loaded.", logging.INFO)
	wpStatus.logSilent("Required Devices: " + str(wpConfig.getRequiredDevices()), logging.INFO)

	# initialize soco thread.
	wpSoco = WPSoco(wpConfig, wpStatus)
	wpSoco.discoverDevices()
	wpSoco.listHouseholdDevices()


if __name__ == "__main__":
	main()