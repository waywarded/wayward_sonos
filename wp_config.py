import os
import json
import yaml
import logging

# choices made on the screen that should survive a restart (the main room), per room config
STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'room_state.json')

class WPConfig:
	def __init__(self, config_file, display_config_file):
		self.configName = os.path.basename(config_file)
		with open(config_file, 'r') as f:
			self.config = yaml.safe_load(f)
		
		with open(display_config_file, 'r') as f:
			displayconfig = yaml.safe_load(f)
		
		self.config.update(displayconfig)

	def getRequiredDevices(self):
		devices = self.config.get("target_devices", [])
		required_devices = [d["name"] for d in devices if d.get("required", False)]
		return required_devices

	def get(self, key, default=None):
		return self.config.get(key, default)
	
	def getSubkey(self, section, key, default=None):
		if (section not in self.config) or (not isinstance(self.config[section],dict)):
			return default
		
		return self.config[section].get(key,default)

	def savedState(self, key, default=None):
		try:
			with open(STATE_FILE) as f:
				return json.load(f).get(self.configName, {}).get(key, default)
		except (OSError, ValueError):
			return default

	def saveState(self, key, value):
		try:
			with open(STATE_FILE) as f:
				state = json.load(f)
		except (OSError, ValueError):
			state = {}
		state.setdefault(self.configName, {})[key] = value
		with open(STATE_FILE, 'w') as f:
			json.dump(state, f, indent=2)

	# the main room picked on the screen, else the config's `main: true`
	def mainRoomName(self):
		return self.savedState('main_room') or self.mainDeviceName()

	def mainDeviceName(self):
		devices = self.config.get("target_devices", [])
		for d in devices:
			if d.get("main", False):
				return d["name"]
		return None
	
