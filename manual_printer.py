from gcode_printer import GCodePrinter
from geometry.angle import Angle
from gcline import GCLine

class ManualPrinter(GCodePrinter):

	def gcode_set_thread_path(self, thread_path, target) -> list[GCLine]:
		"""Return code to pause the print and display a message about where the
		thread should be moved to next."""
		return [
				GCLine(code='M117', args={None: f'Move thread to {thread_path.angle}'}),
				GCLine(code='M601', comment='Pause, wait for user to click buttton')
				]
