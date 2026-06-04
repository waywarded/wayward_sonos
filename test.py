import soco

def main():
	# Discover Sonos devices on the network
	devices = soco.discover()
	
	if not devices:
		print("No Sonos devices found.")
		return
	
	# Print the names of the discovered devices
	print("Discovered Sonos devices:")
	for device in devices:
		print(f"- {device.player_name}")