from copy import deepcopy

from geometry import GSegment, GPoint
from geometry.utils import ang_diff
from gcline import GCLine, comment
from util import Saver, unprinted, Number
from logger import rprint, rich_log
from geometry.angle import Angle
import logging

class Step:
	def __init__(self, steps_obj, name='', debug=True):
		self.name       = name
		self.debug      = debug
		self.steps_obj  = steps_obj
		self.printer = steps_obj.printer

		#State
		self.gcsegs:list[GSegment] = []
		self.number = -1
		self.valid = True
		self.printer_anchor = None
		self.ring_initial_angle:Angle|None = None
		self.ring_angle:Angle|None = None
		self.ring_move:Angle|None = None
		self.fixing = False   #Does this step print over a thread to fix it in place?


	def __repr__(self):
		return(f'<Step {self.number}'
				+ (f' ({len(self.gcsegs)} segments)>:' if self.gcsegs else '>')
				+ f' [light_sea_green italic]{self.name}[/]>'
				+ ((f' from {self.ring_initial_angle:.2f}° → {self.ring_angle:.2f}°' + f'({self.ring_move:.2f}°) ')
						if self.ring_initial_angle and self.ring_angle and self.ring_move else '')
		)


	def gcode(self) -> list:
		"""Render the gcode involved in this Step, returning a list of GCLines:
			* Sort added gcode lines by line number. If there are breaks in line
				number, check whether the represented head position also has a break.
				If so, add gcode to move the head correctly.

		self.gcsegs is made of GSegment objects, each of which should have a .gc_line1
		and .gc_line2 member which are GCLines.
		"""
		if not self.gcsegs:
			return [] if self.ring_move is None or self.ring_move == 0.0 else self.printer.gcode_ring_move(self.ring_move,
				#Tell ring move to pause if the previous step was a thread-fixing step
				pause_after=False if self.number < 1 else self.steps_obj.steps[self.number-1].fixing)


		#Sort gcsegs by the first gcode line number in each
		self.gcsegs.sort(key=lambda s:s.gc_lines.first.lineno)

		#Set the anchor in the printer (again) so we can use it for thread location
		# detection if needed
		self.printer.anchor = self.printer_anchor

		gcode = []
		for seg in self.gcsegs:
			#In a > 2-line Segment, there is always one or more X/Y Move
			# lines, but only ever one Extrude line, which is always the last line.
			# Save and execute every line, as the XY move will put the head in the
			# right place for the extrude.
			if len(seg.gc_lines) > 2:
				gcode.extend(self.printer.execute_gcode(seg.gc_lines.data[:-1], fixing=self.fixing))
				extrude_line = seg.gc_lines.data[-1]

			#For 2-line Segments
			else:
				l1, extrude_line = seg.gc_lines.data

				#The first line should never execute an extrusion move, but we might need
				# to use its coordinates to position the print head in the right place.
				if l1.is_xymove() and self.printer.xy != l1.xy:
					if l1.is_xyextrude():
						l1 = l1.as_xymove(fake=True)
					gcode.extend(self.printer.execute_gcode(l1))

			assert(extrude_line.is_extrude())
			gcode.extend(self.printer.execute_gcode(extrude_line))

		return gcode


	def add(self, gcsegs:list[GSegment], fixing=False):
		"""Add the GSegments in `gcsegs` to the list of segments that should be
		printed in this step. Set `fixing` to True to add the `fixed` property to
		each of the passed lines."""
		rprint(f'Adding {len(unprinted(gcsegs))}/{len(gcsegs)} unprinted gcsegs to Step')
		if fixing: rprint(f"  -- This is a fixing step (#{self.number})!")
		for seg in unprinted(gcsegs):
			self.fixing = fixing
			self.gcsegs.append(seg)
			seg.printed = True


	def __enter__(self):
		if self.debug is False: rich_log.setLevel(logging.CRITICAL)
		self.ring_initial_angle = self.printer.ring.angle
		return self


	def __exit__(self, exc_type, value, traceback):
		if self.debug is False: rich_log.setLevel(logging.DEBUG)

		#Save state
		self.printer_anchor     = self.printer.anchor.copy()
		self.ring_angle         = self.printer.ring.angle
		self.ring_move          = ang_diff(self.ring_initial_angle, self.ring_angle)

		#Die if there's an exception
		if exc_type is not None:
			print(f'Exception on Step.__exit__: {exc_type}')
			return False

		#Tell parent Steps object we exited
		self.steps_obj.step_exited(self)
