"""
"""
from __future__      import annotations
from copy            import copy
from math            import radians
from typing          import Collection
from more_itertools  import flatten
from rich            import print
from fastcore.basics import first
# from Geometry3D      import Polygon

from geometry       import GPoint, GSegment, GHalfLine
from geometry.angle import Angle, atan2, asin, acos
from geometry.utils import ang_diff, circle_intersection, sign
from geometry_helpers import traj_isec
from bed            import Bed
from gcode_printer  import GCodePrinter
from gcline         import GCLine, comments, comment
from logger         import rprint
from util           import Saver, Number
from config         import load_config, get_general_config, get_bed_config, BedConfig


class Manualprinter(GCodePrinter):
	def __init__(self, config, initial_thread_path:GHalfLine, *args, **kwargs):
		self.config = config
		self.general_config = get_general_config(config)
		print(f"Loaded general config: {self.general_config}")
		# We don't load a ring config for the manual printer
		self.bed_config  = get_bed_config(config)
		print(f"Loaded bed: {self.bed_config}")

		#Move the zero points so the bed zero is actually 0,0
		self.bed_config['anchor']  -= self.bed_config['zero']
		self.bed_config['zero']    -= self.bed_config['zero']
		print(f"Bed now: {self.bed_config}")

		self._bed_config  = copy(self.bed_config)
		self.bed = Bed(anchor=self.bed_config['anchor'], size=self.bed_config['size'])
		super().__init__()

		self.next_thread_path = initial_thread_path

		self.add_codes('M109', action=self.gfunc_printer_ready)

		#The current path of the thread: the current thread anchor and the
		# direction of the thread.
		self.thread_path: GHalfLine = None

		self.add_codes('G28', action=lambda gcline, **kwargs: [
			GCLine('G28 X Y Z ; Home only X, Y, and Z axes, but avoid trying to home A')])


	def __repr__(self):
		return f'Manual Printer (🧵={self.thread_path}, x={self.x}, y={self.y}, z={self.z})'


	@property
	def info(self): return f'🧵{self.thread_path}'


	def set_thread_path(self, thread_path:GHalfLine, target:GPoint) -> list[GCLine]:
		"""We have no ring to move - but we do need to tell the user to move the thread"""
		gcode:list[GCLine] = []
		target_angle = thread_path.angle
		gcode.extend([
			GCLine('M300', args={'S':40, 'P':10} , comment="Notification chirp"),
			GCLine(f'M117 Move to angle {target_angle}'),
			GCLine('M601', comment="Pausing for manual thread angle"),
			self.curr_gcline.copy(comment='Return after park')
		])
		return gcode

	def gfunc_printer_ready(self, gcline: GCLine, **kwargs) -> list[GCLine]:
		"""At least with the current version of Cura, M109 is the last command
		before the printer starts actually doing things."""

		self.thread_path = self.next_thread_path

		return [
			gcline,
			GCLine(comment='--- Printer state ---'),
			GCLine(comment=repr(self.bed)),
			GCLine(comment=f'Print head: {self.head_loc}'),
		]


	def gcfunc_move_axis(self, gcline: GCLine, **kwargs) -> list[GCLine]:
		"""Process gcode lines with instruction G0, G1. Move the ring such
		that the angle of `self.thread_path` stays constant with any Y movement."""

		gclines:list[GCLine] = []

		#Keep a copy of the head location since super() will change it.
		prev_loc = self.head_loc.copy()
		self.prev_loc = prev_loc
		self.prev_set_by = self.head_set_by

		#Run the passed gcode line `gcline` through the parent class's
		# gfunc_set_axis_value() function. This might return multiple lines, so we
		# need to process each of the returned list values.
		super_gclines = super().gcfunc_move_axis(gcline, **kwargs) or [gcline]

		for gcline in super_gclines:
			if not gcline.is_xymove:
				gclines.append(gcline)
				continue

		return gclines
