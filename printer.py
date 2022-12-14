from copy import copy, deepcopy
from typing import Collection, Callable
from itertools import groupby
from more_itertools import flatten
from fastcore.basics import listify

from util import attrhelper, Number
from geometry import GPoint, GSegment, GHalfLine
from gcline import GCLine, GCLines
from ring import Ring
from bed import Bed
from logger import rprint
from geometry_helpers import visibility, too_close
from geometry.utils import angsort
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
		self.add_codes(None,              action=lambda gcline: [gcline])
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


	def gcode_ring_move(self, move_amount) -> list[GCLine]:
		return self.ring.gcode_move(move_amount)


	def _execute_gcline(self, gcline:GCLine) -> list[GCLine]:
		return self._code_actions.get(gcline.code, self._code_actions[None])(gcline) or [gcline]


	# def execute_gcode(self, gcline:GCLine|list[GCLine]|GCLines) -> list[GCLine]:
	# 	"""Update the printer state according to the passed line of gcode. Return
	# 	the line of gcode for convenience. Assumes absolute coordinates."""
	# 	r: list[GCLine] = []
	# 	for l in listify(gcline):
	# 		r.extend(self._code_actions.get(l.code, self._code_actions[None])(l) or [l])
	# 	return r


	def execute_gcode(self, gcline:GCLine|list[GCLine]) -> list[GCLine]:
		return sum(map(self._execute_gcline, listify(gcline)), [])


	#G28
	def gcfunc_auto_home(self, gcline: GCLine):
		self.x, self.y, self.z = 0, 0, 0


	#G0, G1, G92
	def gcfunc_set_axis_value(self, gcline: GCLine):
		#Keep track of current ring angle
		if self.extruder_no.code == 'T1':
			if gcline.code in ('G0', 'G1'):
				if dist := gcline.meta.get('ring_move_deg', None):
					self.ring_angle += dist
			return

		#Extruder is T0; track head location
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
				isecs = self.thread_avoid(avoid)
				rprint(f"{len(isecs)} intersections" + (f": {isecs}" if isecs else ""))
				if len(isecs) == 0:
					rprint("No intersections, don't need to move thread")
					s.valid = False
				if len(avoid) == 1: rprint('Was avoiding:', avoid, indent=2)
				avoid -= isecs
			if avoid:
				with steps.new_step(f"Print {len(avoid)} segments thread doesn't intersect" + extra_message) as s:
					s.add(avoid)
				if not isecs: break
			avoid = isecs


	def thread_avoid(self, avoid: Collection[GSegment], move_ring=True, avoid_by=1) -> set[GSegment]:
		assert(avoid)
		avoid = set(avoid)

		thr = GSegment(self.anchor, self.ring.point)
		anchor = thr.start_point

		#If no thread-avoid intersections and the thread is not too close to any
		# avoid segment endpoints, we don't need to move ring, and are done
		if(not thr.intersecting(avoid)
			 and not any(too_close(thr, ep) for ep in (set(flatten(avoid)) - set(thr[:])))):
			return set()

		vis, ipts = visibility(anchor, avoid, avoid_by)

		#Get all of the visibility points with N intersections, where N is the
		# smallest number of intersections
		_, vis_points = next(groupby(vis, key=lambda k:len(vis[k])))

		#Then sort by distance from the thread
		vis_points = angsort(list(vis_points), ref=thr)

		#Now move the thread to the closest one
		self.thread_intersect(vis_points[0], set_new_anchor=False)

		if vis[vis_points[0]] == avoid:
			rprint("Result of visibility:", vis[vis_points[0]], "is the same thing we tried to avoid:",
					avoid, indent=4)
			rprint(f"intersections {anchor}→{vis_points[0]}:",
					ipts[vis_points[0]], indent=4)
			raise ValueError("oh noes")

		#Return the set of segments that we intersected
		return vis[vis_points[0]]



	def thread_intersect(self, target:GPoint, anchor:GPoint|None=None, set_new_anchor=True, move_ring=True):
		"""Rotate the ring so that the thread starting at `anchor` intersects the
		`target`. By default sets the anchor to the intersection. Return the
		rotation value."""
		anchor = (anchor or self.anchor).as2d()
		target = target.as2d()
		if target != anchor:
			if isecs := self.ring.intersection(GHalfLine(anchor, target)):
				ring_angle = self.ring.point2angle(isecs[-1])

				if move_ring and self.ring.angle != ring_angle:
					self.ring.angle = ring_angle

		else:
			#rprint('thread_intersect with target == anchor, doing nothing')
			ring_angle = self.ring.angle

		if set_new_anchor:
			rprint(f'thread_intersect set new anchor to {target}')
			self.anchor = target

		return ring_angle
