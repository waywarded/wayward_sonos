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
import signal

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
    parser.add_argument('-r','--round',action='store_true', help='dev aid: mask the window to the round display')

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
    wpDisplay = WPDisplay(wpConfig, wpStatus, fullScreen=args.fullscreen, roundMask=args.round)
    wpStatus.log("Display initialized.", logging.INFO)
    # dev aid: `kill -USR1 <pid>` saves a screenshot to logs/screen.png, same as the S key
    signal.signal(signal.SIGUSR1, lambda signum, frame: wpDisplay.requestScreenshot())

    # initialize soco thread.
    wpSoco = WPSoco(wpConfig, wpStatus)
    wpSoco.start()

    wpStreamdeck = WPStreamDeckUI(wpConfig, wpStatus)
    wpStreamdeck.start()

    # run UI loop
    wpDisplay.run()


if __name__ == "__main__":
    main()
