import soco
import yaml
from wp_config import WPConfig
from wp_app_status import WPAppStatus, WpAppState
from wp_streamdeckui import WPStreamDeckUI
from wp_display import WPDisplay
from wp_soco import WPSoco
import logging
import argparse
import os

from soco.discovery import scan_network

os.makedirs('logs', exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    handlers=[
        logging.FileHandler('logs/app.log'),
        logging.StreamHandler()  # still prints to terminal when launched via SSH
    ]
)

def main():
    logging.basicConfig(level=logging.INFO)
    wpStatus = WPAppStatus()

    # parse args
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', default='config.yaml', help='path to config file')
    parser.add_argument('--display_config', default='display_config.yaml', help="path to display configuration")
    parser.add_argument('-f','--fullscreen',action='store_true')

    args = parser.parse_args()
    configPath = args.config
    displayConfigPath = args.display_config
    # Load config
    wpStatus.updateStatus(f"Initializing from {configPath} and {displayConfigPath}")
    wpStatus.updateAppState(WpAppState.LOADING)
    wpConfig = WPConfig(configPath, displayConfigPath)
    wpStatus.log("Configuration loaded.", logging.INFO)
    wpStatus.logSilent("Required Devices: " + str(wpConfig.getRequiredDevices()), logging.INFO)

    # Initialize display
    wpDisplay = WPDisplay(wpConfig, wpStatus, fullScreen=args.fullscreen)
    wpStatus.log("Display initialized.", logging.INFO)

    # initialize soco thread.
    wpSoco = WPSoco(wpConfig, wpStatus)
    wpSoco.start()

    wpStreamdeck = WPStreamDeckUI(wpConfig, wpStatus)
    wpStreamdeck.start()

    # run UI loop
    wpDisplay.run()


if __name__ == "__main__":
    main()
