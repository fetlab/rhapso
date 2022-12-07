from copy import copy, deepcopy
from typing import Collection, Set
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
		self._x, self._y, self._z, self._e = 0, 0, z, 0
		self.bed = bed
		self.ring = ring

		self.anchor = GPoint(self.bed.anchor[0], self.bed.anchor[1], 0)

		#Default states
		self.extruder_no    = GCLine(code='T0',  args={}, comment='Switch to main extruder', fake=True)
		self.extrusion_mode = GCLine(code='M82', args={}, comment='Set absolute extrusion mode', fake=True)
		self.cold_extrusion = GCLine(code='M302', args={'P':0}, comment='Prevent cold extrusion', fake=True)

		#Debug
		self._executing_line:GCLine|None = None

	#Create attributes which call Printer.attr_changed on change
	x = property(**attrhelper('_x'))
	y = property(**attrhelper('_y'))
	z = property(**attrhelper('_z'))
	e = property(**attrhelper('_e'))

	@property
	def xy(self): return self.x, self.y


	def __repr__(self):
		return f'Printer(⚓︎{self.anchor}, ∡ {self.ring._angle:.2f}°)'


	def summarize(self):
		import textwrap
		return textwrap.dedent(f"""\
			[yellow]—————[/]
			{self}:
				_x, _y, _z, _e: {self._x}, {self._y}, {self._z}, {self._e}
				anchor: {self.anchor}

				bed: {self.bed}
				ring: {self.ring}
					_angle: {self.ring._angle}
					center: {self.ring.center}
			[yellow]—————[/]
		""")


	def attr_changed(self, attr, old_value, new_value):
		return
		if old_value != new_value and attr[1] == 'e':
			if self._executing_line and (self._executing_line.lineno < 40 or
																4486 < self._executing_line.lineno < 4725 ):
				print(f'{self._executing_line}:\n\tprinter.{attr[1:]} {old_value} -> {new_value}')


	def execute_gcode(self, gcline:GCLine|list[GCLine]|GCLines) -> list[GCLine]:
		"""Update the printer state according to the passed line of gcode. Return
		the line of gcode for convenience. Assumes absolute coordinates."""
		r = []
		for l in listify(gcline):
			r.extend(self.execute_gcode_line(l))
		return r


	def execute_gcode_line(self, gcline:GCLine) -> list[GCLine]:
		self._executing_line = gcline

		match gcline.code:
			#Comment-only line
			case None: return [gcline]

			#M82: absolute; M83: relative
			case 'M82' | 'M83': self.extrusion_mode = gcline

			#Extruder change
			case 'T0' | 'T1': self.extruder_no = gcline

			#Enable/disable cold extrusion
			case 'M302': self.cold_extrusion = gcline

			#Auto home
			case 'G28':
				self.x = 0
				self.y = 0
				self.z = 0

			#G0, G1: move; G92: set axis value
			case 'G0' | 'G1' | 'G92' if self.extruder_no.code == 'T0':
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
					########### TODO: it looks like there is a parsing or something bug
					# that makes the lines E-6.5 / E0 turn into E-6.5 / E6.5 -> see
					# input/output gcode line 36
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


	def thread_avoid(self, avoid: Collection[GSegment], move_ring=True, avoid_by=1) -> Set[GSegment]:
		if not avoid: raise ValueError("Need some Segments in avoid")
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



	def thread_intersect(self, target, anchor=None, set_new_anchor=True, move_ring=True):
		"""Rotate the ring so that the thread starting at anchor intersects the
		target Point. By default sets the anchor to the intersection. Return the
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
