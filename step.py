from copy import deepcopy

from geometry import GSegment, GPoint, GHalfLine
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
		self.anchor:GPoint|None = None   #Does this step create a thread anchor?
		self.original_thread_path: GHalfLine = self.printer.thread_path.copy()
		self.thread_path: GHalfLine|None = None
		self.target:GPoint|None = None


	def __repr__(self):
		return(f'<Step {self.steps_obj.layer.layernum}.{self.number}'
				+ (f' ({len(self.gcsegs)} segments)>:' if self.gcsegs else '>')
				+ f' [light_sea_green italic]{self.name}[/]>'
		)


	def gcode(self, gcprinter) -> list:
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

				### TODO ###
				# Need to check to see if the thread move would cross the current head
				# position and do something if so.
				### END TODO ###

				return gcprinter.set_thread_path(self.thread_path, self.target)


		#If we got here, there are gcsegs, so the thread doesn't move, but the head does

		#Sort gcsegs by the first gcode line number in each
		gcsegs = self.gcsegs.sorted(key=lambda s:s.gc_lines.first.lineno)

		#Find missing segments: see if the start point of each GSegment is the same
		# as the end point of the preceeding one; if a segment is missing, create a
		# new segment and add it to new_gcsegs
		new_gcsegs = [gcsegs.pop(0)]
		while gcsegs:
			seg = gcsegs.pop(0)
			s, e = new_gcsegs[-1].end_point, seg.start_point
			if s != e:
				new_gcsegs.append(GSegment(s, e))
			new_gcsegs.append(seg)
		gcsegs = new_gcsegs

		#Now gcsegs is a list of GSegments that will be executed during this
		# Step - both extruding and non-extruding

		#Split any moves that cross the thread and apply parameters
		new_gcsegs = [gcsegs.pop(0)]
		while gcsegs:
			seg = gcsegs.pop(0)
			if isec := gcprinter.thread_path.intersection(seg):
				move_type = ('non_extruding' if not seg.is_extrude
											else
										 'anchor_fixing' if self.anchor else 'extruding')
				new_gcsegs.extend(gcprinter.split_head_move(seg, isec, move_type))
			else:
				new_gcsegs.append(seg)
		gcsegs = new_gcsegs

		#Now generate gcode and execute it
		gcode = []
		for seg in gcsegs:
			gcode.extend(seg.to_gclines())

		return gcode


	def add(self, gcsegs:list[GSegment], anchor:GPoint|None=None):
		"""Add the GSegments in `gcsegs` to the list of segments that should be
		printed in this step. Set `anchor` to the anchor point if this is an
		anchoring step."""
		rprint(f'Adding {len(unprinted(gcsegs))}/{len(gcsegs)} unprinted gcsegs to Step')
		if anchor: rprint(f"  -- This is a anchoring step (#{self.number})!")
		for seg in unprinted(gcsegs):
			self.anchor = anchor
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
