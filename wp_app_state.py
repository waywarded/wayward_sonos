
from enum import Enum

class WpAppState(Enum):
	UNINITIALIZED = "Uninitialized"
	LOADING = "Loading"
	CONNECTING = "Connecting"
	NO_CONNECTION = "No Connection"
	CONNECTED = "Connected"
