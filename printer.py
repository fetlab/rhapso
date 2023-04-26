from math import pi
from copy import copy, deepcopy
from collections import defaultdict
from typing import Collection, Callable
from itertools import groupby
from more_itertools import flatten
from fastcore.basics import first, listify
from Geometry3D import Line, Vector

from util import attrhelper, Number
from geometry import GPoint, GSegment, GHalfLine
from gcline import GCLine, GCLines
from gclayer import Layer
from ring import Ring
from bed import Bed
from logger import rprint
from geometry_helpers import visibility, too_close
from geometry.utils import angsort, ang_diff, eps
from steps import Steps


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

		#State
		self.head_loc   = GPoint(0, 0, z)
		self.anchor     = GPoint(self.bed.anchor[0], self.bed.anchor[1], 0)
		self.extruder_no    = GCLine(code='T0', comment='Switch to main extruder', fake=True)
		self.extrusion_mode = GCLine(code='M82',comment='Set absolute extrusion mode', fake=True)
		self.cold_extrusion = GCLine(code='M302', args={'P':0}, comment='Prevent cold extrusion', fake=True)

		#Properties for self.attr_changed()
		self._ring_angle = self.ring.angle
		self._x = 0
		self._y = 0
		self._z = 0
		self._e = 0

		#Functions for different Gcode commands
		self._code_actions: dict[str|None,Callable] = {}
		self.add_codes(None,              action=lambda gcline, **kwargs: [gcline])
		self.add_codes('G28',             action=self.gcfunc_auto_home)
		self.add_codes('G0', 'G1', 'G92', action=self.gcfunc_set_axis_value)
		self.add_codes('M82', 'M83',      action='extrusion_mode')
		self.add_codes('T0', 'T1',        action='extruder_no')
		self.add_codes('M302',            action='cold_extrusion')


	#Create attributes which call Printer.attr_changed on change
	x = property(**attrhelper('_x'))
	y = property(**attrhelper('_y'))
	z = property(**attrhelper('_z'))
	e = property(**attrhelper('_e'))
	ring_angle = property(**attrhelper('_ring_angle'))


	@property
	def xy(self): return self.head_loc.xy


	@property
	def xyz(self): return self.head_loc.xyz


	def __repr__(self):
		return f'Printer(⚓︎{self.anchor}, ∡ {self.ring.angle:.2f}°)'


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
				_x, _y, _z, _e: {self._x}, {self._y}, {self._z}, {self._e}
				anchor: {self.anchor}

				bed: {self.bed}
				ring: {self.ring}
					angle: {self.ring.angle}
					center: {self.ring.center}
			[yellow]—————[/]
		""")


	def attr_changed(self, attr, old_value, new_value):
		if attr[1] in 'xyz':
			self.head_loc['xyz'.index(attr[1])] = new_value


	#Functions to add extra lines of GCode. Each is passed the pre/postamble and
	# should return it, possibly modified.
	def gcode_file_preamble  (self, preamble:  list[GCLine]) -> list[GCLine]: return preamble
	def gcode_file_postamble (self, postamble: list[GCLine]) -> list[GCLine]: return postamble
	def gcode_layer_preamble (self, preamble:  list[GCLine], layer:Layer) -> list[GCLine]: return preamble
	def gcode_layer_postamble(self, postamble: list[GCLine], layer:Layer) -> list[GCLine]: return postamble


	def gcode_ring_move(self, move_amount) -> list[GCLine]:
		return self.ring.gcode_move(move_amount)


	def _execute_gcline(self, gcline:GCLine, **kwargs) -> list[GCLine]:
		return self._code_actions.get(gcline.code, self._code_actions[None])(gcline, **kwargs) or [gcline]


	# def execute_gcode(self, gcline:GCLine|list[GCLine]|GCLines) -> list[GCLine]:
	# 	"""Update the printer state according to the passed line of gcode. Return
	# 	the line of gcode for convenience. Assumes absolute coordinates."""
	# 	r: list[GCLine] = []
	# 	for l in listify(gcline):
	# 		r.extend(self._code_actions.get(l.code, self._code_actions[None])(l) or [l])
	# 	return r


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

			#M83: relative extrude mode
			elif self.extrusion_mode.code == 'M83':
				self.e += gcline.args['E']

			#A normal extruding line; we need to use the relative extrude value
			# since our lines get emitted out-of-order
			else:
				self.e += gcline.relative_extrude
				gcline = deepcopy(gcline)
				gcline.args['E'] = self.e
				return [gcline]


	def avoid_and_print(self, steps: Steps, avoid: Collection[GSegment]=None, extra_message='', avoid_by=1):
		"""Loop to print everything in avoid without thread intersections."""
		avoid = set(avoid or [])
		repeats = 0
		while avoid:
			repeats += 1
			if repeats > 5: raise ValueError("Too many repeats")
			with steps.new_step(f"Move thread to avoid {len(avoid)} segments" + extra_message) as s:
				s._debug = dict(avoid=avoid.copy(), anchor=self.anchor.copy(),
										ring_angle=self.ring.angle,
										ring_point=self.ring.point.copy())

				#First let's just try to drop everything the thread trajectory intersects
				thr = GSegment(self.anchor, self.ring.point, z=self.anchor.z)
				rprint(f"Thread trajectory: {thr}")

				isecs = thr.intersecting(avoid, ignore=self.anchor)
				isecs.update({seg for seg in avoid - isecs if
					too_close(thr, seg.start_point, by=avoid_by) or too_close(thr, seg.end_point, by=avoid_by)})

				s._debug['isecs'] = isecs

				#If we end up intersecting everything, we have to be more sophisticated
				if isecs == avoid: isecs = self.thread_avoid(avoid)

				rprint(f"{len(isecs)} intersections" + (f": {isecs}" if isecs else ""))

				avoid -= isecs

			if avoid:
				with steps.new_step(f"Print {len(avoid)} segments thread doesn't intersect" + extra_message) as s:
					s.add(avoid)
				if not isecs: break
			avoid = isecs


	def thread_avoid(self, avoid: Collection[GSegment], move_ring=True, avoid_by=1) -> set[GSegment]:
		"""Move the ring to try to make the thread's anchor->ring trajectory avoid
		the segments in `avoid` by at least `avoid_by`. Return any printed segments
		that could not be avoided."""
		assert(avoid)
		avoid = set(avoid)

		#Current thread->ring segment
		thr = GSegment(self.anchor, self.ring.point)

		rprint(f'Avoiding {len(avoid)} segments')

		#If there's only one segment in avoid, and the anchor point is either on it
		# or within `avoid_by` of it, move the thread to be perpindicular to it.
		if len(avoid) == 1:
			seg = first(avoid)
			if (self.anchor in seg or
					too_close(self.anchor, seg.start_point, avoid_by) or
					too_close(self.anchor, seg.end_point, avoid_by)):
				seg_vec = seg.line.dv
				ring_isecs = sorted(
					self.ring.intersection(
						Line(self.anchor, Vector(seg_vec[1], seg_vec[0], 0))),
					key=lambda isec: ang_diff(self.ring.point2angle(isec), self.ring.angle))

				if isec := first(ring_isecs):
					self.ring.angle = self.ring.point2angle(isec)

			return set()


		#Thread is already not intersecting segments in `avoid`, but we want to try
		# to move it so it's not very close to the ends of the segments either.
		if not (isecs := thr.intersecting(avoid)):
			rprint('No intersections, but we want to avoid segments by at least 1 mm')

			#All printed segment starts & ends, minus the thread's start/end
			endpoints  = set(flatten(avoid)) - set(thr[:])

			#We can't avoid points that are too close to the anchor - not physically possible
			avoidables = set(ep for ep in endpoints if self.anchor.distance(ep) > avoid_by)

			#Find out if any of the end points are closer than `avoid_by` to the
			# thread; if so, we'll have to do more processing
			if not any(too_close(thr, ep) for ep in avoidables):
				return set()

		else:
			rprint(f'    {len(isecs)} intersections')

		#Either the thread intersects printed segments, or it's too close to
		# printed segment endpoints, so we will try to move the thread.

		vis = visibility(self.anchor, avoid, avoid_by)
		vis_segs = defaultdict(set)
		for vp, segs in vis.items():
			vis_segs[vp].update(segs)

		rprint(f'    {len(vis)} potential visibility points')
		if len(vis) < 5:
			rprint(vis)

		#We only have 1 segment to avoid but can't avoid it. Let's pretend we did
		# and see what happens.
		if len(avoid) == 1 and len(vis_segs) == 1 and first(vis_segs) == first(avoid):
			rprint(f"Can't avoid only segment {first(avoid)}, giving up on trying")
			return set()

		#Get all of the visibility points with N intersections, where N is the
		# smallest number of intersections
		_, vis_points = next(groupby(vis, key=lambda k:len(vis[k])))

		#Then sort by distance from the thread
		vis_points = angsort(list(vis_points), ref=thr)

		#Now move the thread to the closest one
		self.thread_intersect(vis_points[0], set_new_anchor=False)

		#If the visibility point with the smallest number of intersections still
		# intersects the segments in `avoid`, it's probably too close to avoid.
		if vis[vis_points[0]] == avoid:
			rprint("Result of visibility:", vis[vis_points[0]], "is the same thing we tried to avoid:",
					avoid, indent=4)
			self._debug_quickplot_args = dict(gc_segs=avoid, anchor=self.anchor, thread_ring=thr)
			raise ValueError("thread_avoid() couldn't avoid; try running\n"
				"plot_helpers.quickplot(**threader.layer_steps[-1].printer._debug_quickplot_args);")

		#Return the set of segments that we intersected
		return vis[vis_points[0]]



	def thread_intersect(self, target:GPoint, anchor:GPoint|None=None, set_new_anchor=True, move_ring=True):
		"""Rotate the ring so that the thread starting at `anchor` intersects the
		`target`. By default sets the anchor to the intersection. Return the
		rotation value."""
		anchor = anchor or self.anchor
		ring_angle = self.ring.angle

		if target != anchor:
			if isecs := self.ring.intersection(GSegment(anchor, target)):
				ring_angle = self.ring.point2angle(isecs[-1])

				if move_ring:
					self.ring.angle = ring_angle
			else:
				if move_ring:
					raise ValueError(f"Didn't get an intersection between {anchor} → {target}")

		if set_new_anchor:
			rprint(f'thread_intersect set new anchor to {target}')
			self.anchor = target

		return self.ring.angle
