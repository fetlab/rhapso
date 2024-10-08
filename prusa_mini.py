from python_gcode.gcline import GCLine
from gcode_geom import GPolyLine, GPoint
from manual_printer import ManualPrinter

class PrusaMini(ManualPrinter):
	def gcode_pause_for_thread(self, thread_path:GPolyLine, target:GPoint) -> list[GCLine]:
		return [GCLine(l) for l in self.config['printer']['pause_commands']]
