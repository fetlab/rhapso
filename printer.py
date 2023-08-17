from math import pi
from copy import copy, deepcopy
from collections import defaultdict
from typing import Collection, Callable
from itertools import groupby
from more_itertools import flatten
from fastcore.basics import first, listify
from Geometry3D import Line, Vector
from rich.pretty import pretty_repr

from util import attrhelper, Number
from geometry import GPoint, GSegment, GHalfLine
from gcline import GCLine, GCLines
from gclayer import Layer
from ring import Ring
from bed import Bed
from logger import rprint
from geometry_helpers import visibility, too_close
from geometry.utils import angsort, ang_diff, ang_dist, eps
from steps import Steps
from geometry.angle import Angle


class Printer:
	"""Maintains the state of the printer/ring system. Holds references to the
	Ring and Bed objects. Subclass this object to handle situations where the
	coordinate systems need transformations.
	"""
	style = {
		'thread': {'mode':'lines', 'line': dict(color='white', width=1, dash='dot')},
		'anchor': {'mode':'markers', 'marker': dict(color='red', symbol='x', size=4)},
	}


	def __init__(self, bed:Bed, ring:Ring, z:Number=0):
		self.bed  = bed
		self.ring = ring

		#The current path of the thread: the current thread anchor and the
		# direction of the thread.
		self._thread_path = GHalfLine(self.bed.anchor, self.ring.point)

		#State: absolute extrusion amount, print head location, anchor location
		# (initially the bed's anchor)
		self.e          = 0
		self.head_loc   = GPoint(0, 0, z)

		#Functions for different Gcode commands
		self._code_actions: dict[str|None,Callable] = {}
		self.add_codes(None,              action=lambda gcline, **kwargs: [gcline])
		self.add_codes('G28',             action=self.gcfunc_auto_home)
		self.add_codes('G0', 'G1', 'G92', action=self.gcfunc_set_axis_value)

		self.debug_info = {}


	#Create attributes which call Printer.attr_changed on change
	x = property(**attrhelper('head_loc.x'))
	y = property(**attrhelper('head_loc.y'))
	z = property(**attrhelper('head_loc.z'))

	@property
	def anchor(self): return self.thread_path.point

	@property
	def xy(self): return self.x, self.y


	@property
	def xyz(self): return self.x, self.y, self.z


	def __repr__(self):
		return f'Printer(🧵={self.thread_path})'


	@property
	def thread_path(self): return self._thread_path


	@thread_path.setter
	def thread_path(self, new_path):
		if new_path != self.thread_path:
			rprint(f'[green]****[/] Move thread from {self.thread_path} ({self.thread_path.angle()}°)\n'
						 f'                   to {new_path} ({new_path.angle()}°)')
		#Assign even if they're the same, just in case the new one is a copy or
		# something
		self._thread_path = new_path


	def move_thread_to(self, new_anchor:GPoint):
		self.thread_path = GHalfLine(new_anchor, self.thread_path.vector)


	def rotate_thread_to(self, target:Vector|GPoint):
		self.thread_path = GHalfLine(self.thread_path.point, target)


	def add_codes(self, *codes, action:str|Callable):
		"""Add the given action for each code in `codes`. `action` can be a string,
		in which case the line of gcode will be saved as an attribute with that
		name on this object, or it can be a function, in which case that function
		will be called with the line of gcode as a parameter."""
		for code in codes:
			if isinstance(action, str):
				self._code_actions[code] = lambda v: setattr(self, action, v)
			elif callable(action):
				self._code_actions[code] = action
			else: raise ValueError(f'Need function or string for `action`, not {type(action)}')


	def summarize(self):
		import textwrap
		return textwrap.dedent(f"""\
			[yellow]—————[/]
			{self}:
				x, y, z, e: {self.x}, {self.y}, {self.z}, {self.e}
				anchor: {self.anchor}

				bed: {self.bed}
				ring: {self.ring}
					angle: {self.ring.angle}
					center: {self.ring.center}
			[yellow]—————[/]
		""")


	#Functions to add extra lines of GCode. Each is passed the pre/postamble and
	# should return it, possibly modified.
	def gcode_file_preamble  (self, preamble:  list[GCLine]) -> list[GCLine]: return preamble
	def gcode_file_postamble (self, postamble: list[GCLine]) -> list[GCLine]: return postamble
	def gcode_layer_preamble (self, preamble:  list[GCLine], layer:Layer) -> list[GCLine]: return preamble
	def gcode_layer_postamble(self, postamble: list[GCLine], layer:Layer) -> list[GCLine]: return postamble


	def gcode_ring_move(self, move_amount:Angle, relative=True) -> list[GCLine]:
		"""Default ring movement command. Must be implemented in subclasses."""
		raise NotImplementedError("Subclass must implement gcode_ring_move")


	def _execute_gcline(self, gcline:GCLine, **kwargs) -> list[GCLine]:
		return self._code_actions.get(gcline.code, self._code_actions[None])(gcline, **kwargs) or [gcline]


	def execute_gcode(self, gcline:GCLine|list[GCLine], **kwargs) -> list[GCLine]:
		return sum([self._execute_gcline(l, **kwargs) for l in listify(gcline)], [])


	#G28
	def gcfunc_auto_home(self, gcline: GCLine, **kwargs):
		self.x, self.y, self.z = 0, 0, 0


	#G0, G1, G92
	def gcfunc_set_axis_value(self, gcline: GCLine, **kwargs):
		#Track head location
		if gcline.x: self.x = gcline.x
		if gcline.y: self.y = gcline.y
		if gcline.z: self.z = gcline.z

		if 'E' in gcline.args:
			#G92: software set value
			if gcline.code == 'G92':
				self.e = gcline.args['E']

			#A normal extruding line; we need to use the relative extrude value
			# since our lines get emitted out-of-order
			else:
				self.e += gcline.relative_extrude
				return [gcline.copy(args={'E': self.e})]


	def avoid_and_print(self, steps: Steps, avoid: Collection[GSegment]=None, extra_message='', avoid_by=1):
		"""Loop to print everything in `avoid` without thread intersections."""
		avoid = set(avoid or [])
		repeats = 0
		while avoid:
			repeats += 1
			rprint(f'Avoid and print {len(avoid)} segments, iteration {repeats}')
			if repeats > 5: raise ValueError("Too many repeats")
			with steps.new_step(f"Prevent {len(avoid)} segments from printing over thread path" + extra_message) as s:
				if isecs := self.thread_avoid(avoid):
					rprint(f"{len(isecs)} thread/segment intersections")
				else:
					s.valid = False
				avoid -= isecs

			if avoid:
				with steps.new_step(f"Print {len(avoid)} segments thread doesn't intersect" + extra_message) as s:
					s.add(avoid)
				if not isecs: break
			avoid = isecs
		rprint(f'Finished avoid and print')


	def thread_avoid(self, avoid: Collection[GSegment], avoid_by=1) -> set[GSegment]:
		"""Move the ring to try to make the thread's anchor->ring trajectory avoid
		the segments in `avoid` by at least `avoid_by`. Return any printed segments
		that could not be avoided."""
		assert(avoid)
		avoid = set(avoid)

		rprint(f'Avoiding {len(avoid)} segments with thread {self.thread_path}')

		anchor = self.thread_path.point

		#If there's only one segment in avoid, and the anchor point is either on it
		# or within `avoid_by` of it, move the thread to be perpindicular to it.
		if len(avoid) == 1:
			seg = first(avoid)
			if (anchor in seg or
					too_close(anchor, seg.start_point, avoid_by) or
					too_close(anchor, seg.end_point,   avoid_by)):

				#Get the two perpendicular half-lines to the segment
				perp1 = GHalfLine(anchor, Vector(-seg.line.dv[1], seg.line.dv[0], 0))
				perp2 = GHalfLine(anchor, Vector(seg.line.dv[1], -seg.line.dv[0], 0))

				#Find the perpendicular path that requires the least movement from
				# the current path
				self.thread_path = perp1 if self.thread_path.angle(perp1) <= Angle(degrees=90) else perp2

				return set()

		if not (isecs := self.thread_path.intersecting(avoid)):
			#Thread is already not intersecting segments in `avoid`, but we want to try
			# to move it so it's not very close to the ends of the segments either.

			rprint(f'No intersections, ensure thread avoids segments by at least {avoid_by} mm')

			self.debug_info['avoid'] = avoid

			#All printed segment starts & ends, minus the thread's start point
			endpoints  = set(flatten(avoid)) - {self.thread_path.point}

			#We can't avoid points that are too close to the anchor - not physically possible
			avoidables = set(ep for ep in endpoints if anchor.distance(ep) > avoid_by)

			#Find segments where one or more of the endpoints are too close to the
			# thread path and label them as intersecting (but not if that endpoint is
			# next to the anchor, as it's not physically possible to move the thread
			# to get far enough away.)
			isecs = {seg for seg in avoid
				if any(too_close(self.thread_path, ep, avoid_by)
								for ep in seg[:] if not too_close(anchor, ep, avoid_by))}

			#If none of the end points are closer than `avoid_by` to the
			# thread, return the empty set to indicate we didn't have a problem
			# avoiding any of them.
			#If the segments that are too close are only a subset of those we were
			# trying to avoid, return those.
			if not isecs or isecs != avoid:
				return isecs

			rprint(f'{len(isecs)} segments too close to thread path, same as we wanted to avoid')

		else:
			#Let's try to simply drop every segment the thread intersects or that comes
			# too close to the thread.
			rprint(f'    {len(isecs)} intersections')

			#Add to `isecs` every segment in `avoid` that is too close to the thread
			isecs.update({seg for seg in (avoid - isecs) if
				too_close(self.thread_path, seg.start_point, by=avoid_by) or
				too_close(self.thread_path, seg.end_point,   by=avoid_by)})

			#If there is anything left, return `isecs` so we can subtract from `avoid` in the caller
			if isecs != avoid:
				return isecs


		#If we got here, either the thread intersects printed segments, or it's too
		# close to printed segment endpoints, so we have to try to move the thread.
		rprint('Thread must be moved to avoid segments')

		vis = visibility(anchor, avoid, avoid_by)
		vis_segs = defaultdict(set)
		for vp, segs in vis.items():
			vis_segs[vp].update(segs)

		rprint(f'    {len(vis)} potential visibility points')
		if len(vis) < 5:
			rprint(pretty_repr(vis))

		#We only have 1 segment to avoid but can't avoid it. Let's pretend we did
		# and see what happens.
		if len(avoid) == 1 and len(vis_segs) == 1 and first(vis_segs) == first(avoid):
			rprint(f"Can't avoid only segment {first(avoid)}, giving up on trying")
			return set()

		#Get all of the visibility points with N intersections, where N is the
		# smallest number of intersections
		_, vis_points = next(groupby(vis, key=lambda k:len(vis[k])))

		#Then sort by distance from the thread
		vis_points = angsort(list(vis_points), ref=self.thread_path)

		old_thread = self.thread_path

		#Now move the thread to overlap the closest one
		self.rotate_thread_to(vis_points[0])

		#If the visibility point with the smallest number of intersections still
		# intersects the segments in `avoid`, it's probably too close to avoid.
		if vis[vis_points[0]] == avoid:
			rprint("Result of visibility:", vis[vis_points[0]], "is the same thing we tried to avoid:",
					avoid, indent=4)
			self._debug_quickplot_args = dict(gc_segs=avoid, anchor=anchor, thread_ring=self.thread_path)
			raise ValueError("thread_avoid() couldn't avoid; try running\n"
				"plot_helpers.quickplot(**threader.layer_steps[-1].printer._debug_quickplot_args);")

		#Return the set of segments that we intersected
		return vis[vis_points[0]]
