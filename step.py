from copy import deepcopy

from geometry import GSegment, GPoint, GHalfLine
from geometry.utils import ang_diff
from gcline import GCLine, comment
from gcode_printer import GCodePrinter
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
		self.anchoring = False   #Does this step create a thread anchor?
		self.original_thread_path: GHalfLine = self.printer.thread_path.copy()
		self.thread_path: GHalfLine|None = None
		self.target:GPoint|None = None


	def __repr__(self):
		return(f'<Step {self.steps_obj.layer.layernum}.{self.number}'
				+ (f' ({len(self.gcsegs)} segments)>:' if self.gcsegs else '>')
				+ f' [light_sea_green italic]{self.name}[/]>'
		)


	def gcode(self, gcprinter:GCodePrinter) -> list:
		"""Render the gcode involved in this Step, returning a list of GCLines.
			There are two possibilities:
				1. Thread movement: the angle of the thread has changed. We need to
						find out how to move the ring to achieve this angle change, taking into
						account the bed position. This is partially taken care of in the
						Printer (sub-)class.
				2. Printing: we print some stuff. To do so, we sort `add()`-ed gcode
					lines by line number. If there are breaks in line number, check whether
					the represented head position also has a break. If so, add gcode to
					move the head correctly.

		self.gcsegs is made of GSegment objects, each of which should have a .gc_line1
		and .gc_line2 member which are GCLines.
		"""
		if self.thread_path is None:
			raise ValueError('Attempt to call gcode() before Step context has exited')

		if self.original_thread_path != self.thread_path:
			rprint([f'[yellow]————[/]\nStep {self}:\n\t' +
					 self.original_thread_path.repr_diff(self.thread_path)])

		#If there are no gcsegs, it must be a thread move.
		if not self.gcsegs:
			if self.thread_path == self.original_thread_path:
				rprint('No thread movement and no gcsegs')
				return []

			#If the angle changed, the ring should move to reflect that
			else:
				if self.target is None:
					raise ValueError('No gcsegs and no target')
				return gcprinter.set_thread_path(self.thread_path, self.target)


		#Sort gcsegs by the first gcode line number in each
		self.gcsegs.sort(key=lambda s:s.gc_lines.first.lineno)

		gcode = []
		for seg in self.gcsegs:
			#In a GSegment with more than two gc_lines, there is always one or more
			# X/Y Move lines, but only ever one Extrude line, which is always the
			# last line. Execute every line, as the XY move will put the head in the
			# right place for the extrude.
			if len(seg.gc_lines) > 2:
				gcode.extend(gcprinter.execute_gcode(seg.gc_lines.data[:-1]))
				extrude_line = seg.gc_lines.data[-1]

			#For GSegments with exactly two gc_lines
			else:
				l1, extrude_line = seg.gc_lines.data

				#The first line should never execute an extrusion move, but we might need
				# to use its coordinates to position the print head in the right place.
				if l1.is_xymove and gcprinter.xy != l1.xy:
					if l1.is_xyextrude:
						l1 = l1.as_xymove(fake=True)
					gcode.extend(gcprinter.execute_gcode(l1))

			assert(extrude_line.is_extrude)
			gcode.extend(gcprinter.execute_gcode(extrude_line, anchoring=self.anchoring))

		return gcode


	def add(self, gcsegs:list[GSegment], anchoring=False):
		"""Add the GSegments in `gcsegs` to the list of segments that should be
		printed in this step. Set `anchoring` to True to add the `fixed` property to
		each of the passed lines."""
		rprint(f'Adding {len(unprinted(gcsegs))}/{len(gcsegs)} unprinted gcsegs to Step')
		if anchoring: rprint(f"  -- This is a anchoring step (#{self.number})!")
		for seg in unprinted(gcsegs):
			self.anchoring = anchoring
			self.gcsegs.append(seg)
			seg.printed = True


	def __enter__(self):
		if self.debug is False: rich_log.setLevel(logging.CRITICAL)
		return self


	def __exit__(self, exc_type, value, traceback):
		if self.debug is False: rich_log.setLevel(logging.DEBUG)

		#Save state
		self.thread_path = self.printer.thread_path.copy()
		if self.printer.target is not None:
			self.target = self.printer.target.copy()

		#Die if there's an exception
		if exc_type is not None:
			print(f'Exception on Step.__exit__: {exc_type}')
			return False

		#Tell parent Steps object we exited
		self.steps_obj.step_exited(self)
