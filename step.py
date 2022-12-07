from copy import deepcopy

from geometry import GSegment, GPoint
from geometry.utils import ang_diff
from gcline import GCLine
from util import Saver, unprinted, Number
from logger import rprint, rich_log
import logging

class Step:
	def __init__(self, steps_obj, name='', debug=True):
		self.name       = name
		self.debug      = debug
		self.steps_obj  = steps_obj
		self.printer = steps_obj.printer
		self.gcsegs:list[GSegment] = []
		self.number     = -1
		self.valid      = True
		self.printer_anchor = None
		self.ring_initial_angle = None
		self.ring_angle = None
		self.ring_move = 0


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

		gcode = []

		if not self.gcsegs:
			if self.ring_move:
				#Variables to be restored, in the order they should be restored: we
				# "execute" each line of ring-movement gcode to update the machine
				# state, but want to reset the extruder to the current state after the
				# ring moves.
				save_vars = 'extruder_no', 'extrusion_mode', 'cold_extrusion'

				newlines:list[GCLine] = []
				with Saver(self.printer, save_vars) as saver:
					for rline in self.printer.ring.gcode_move(self.ring_move):
						newlines.extend(self.printer.execute_gcode(rline))

				#Restore extruder state if it was changed
				for var in saver.changed:
					self.printer.execute_gcode(saver.saved[var])
					newlines.append(saver.saved[var])

				gcode.extend(newlines)

			return gcode

		#Sort gcsegs by the first gcode line number in each
		self.gcsegs.sort(key=lambda s:s.gc_lines.first.lineno)

		for seg in self.gcsegs:

			#In a > 2-line Segment, there is always one or more X/Y Move
			# lines, but only ever one Extrude line, which is always the last line.
			# Save and execute every line, as the XY move will put the head in the
			# right place for the extrude.
			if len(seg.gc_lines) > 2:
				for line in seg.gc_lines.data[:-1]:
					gcode.extend(self.printer.execute_gcode(line))
				extrude_line = seg.gc_lines.data[-1]

			#For 2-line Segments
			else:
				l1, extrude_line = seg.gc_lines.data

				#The first line should never execute an extrusion move, but we might need
				# to use its coordinates to position the print head in the right place.
				if l1.is_xymove() and self.printer.xy != l1.xy:
					if l1.is_xyextrude():
						l1 = l1.as_xymove(fake=True)
					move_lines = self.printer.execute_gcode(l1)
					gcode.extend(move_lines)

			assert(extrude_line.is_extrude())
			gcode.extend(self.printer.execute_gcode(extrude_line))

		return gcode


	def add(self, gcsegs:list[GSegment]):
		rprint(f'Adding {len(unprinted(gcsegs))}/{len(gcsegs)} unprinted gcsegs to Step')
		for seg in unprinted(gcsegs):
			self.gcsegs.append(seg)
			seg.printed = True


	def __enter__(self):
		if self.debug is False: rich_log.setLevel(logging.CRITICAL)
		return self


	def __exit__(self, exc_type, value, traceback):
		if self.debug is False: rich_log.setLevel(logging.DEBUG)
		self.printer_anchor = self.printer.anchor.copy()
		self.ring_angle = self.printer.ring.angle
		self.ring_initial_angle = self.printer.ring.initial_angle
		self.ring_move = ang_diff(self.printer.ring.initial_angle, self.printer.ring.angle)
		#Die if there's an exception
		if exc_type is not None:
			print(f'Exception on Step.__exit__: {exc_type}')
			return False
		#Tell parent Steps object we exited
		self.steps_obj.step_exited(self)
