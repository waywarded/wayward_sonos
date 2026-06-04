import yaml
import logging

class WPConfig:
	def __init__(self, config_file):
		with open(config_file, 'r') as f:
			self.config = yaml.safe_load(f)

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

	def mainDeviceName(self):
		devices = self.config.get("target_devices", [])
		for d in devices:
			if d.get("main", False):
				return d["name"]
		return None
	
