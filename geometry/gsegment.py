from __future__ import annotations
from copy import copy
from typing import Collection, Sequence
from Geometry3D import Vector, Segment, Point, Line, angle
from fastcore.basics import listify
from .gpoint import GPoint
from .gcast import gcast
from .utils import distance_linelike_point
from .angle import Angle, atan2
from util import Number, deep_update

def list2gsegments(points:Collection):
	return [GSegment(s, e) for s,e in points]



class GSegment(Segment):
	def __init__(self, start:Sequence[Number]|GPoint,
							end:Sequence[Number]|GPoint, z=None, extrude_amount=None, **kwargs):
		"""Create a GSegment. `kwargs` will be available as `.info`"""
		point1 = start.copy(z=z) if isinstance(start, GPoint) else GPoint(*start, z=z)
		point2 =   end.copy(z=z) if isinstance(  end, GPoint) else GPoint(  *end, z=z)

		if point1 == point2:
			raise ValueError("Cannot initialize a Segment with two identical Points\n"
					f"Init args: {start=}, {end=}, {z=}")

		self.line = Line(point1, point2)
		self.start_point = point1
		self.end_point   = point2

		self.extrude_amount = extrude_amount
		self.printed = False
		self.info = kwargs


	def to_gclines(self):
		"""Return a GCLine representing a move to the end point of this segment.
		`self.info` will be passed as kwargs to GCLine()."""
		from gcline import GCLine
		code = 'G1' if self.is_extrude else 'G0'
		args = {'X':self.end_point.x, 'Y':self.end_point.y, 'Z':self.end_point.z}
		return list(self.info.get('prev_lines', [])) + [
				GCLine(code=code,
							 args=deep_update(args, self.info.get('line_args', {}),
												 {'E': self.extrude_amount} if self.is_extrude else {}),
				**self.info.get('line_params', {}))]


	@property
	def is_extrude(self) -> bool:
		return bool(self.extrude_amount)


	def __repr__(self):
		#if not(self.gc_line1 and self.gc_line2):
			# return "<{}←→{} ({:.2f} mm)>".format(self.start_point, self.end_point,
			# 		self.length)
		return "<{}[{:>2}] {}←→{} ({:.2f} mm)>".format(
				'S' if self.printed else 's',
				len(self.info.get('prev_lines', [])),
				self.start_point,
				self.end_point,
				self.length)


	#We define __eq__ so have to inherit __hash__:
	# https://docs.python.org/3/reference/datamodel.html#object.__hash__
	__hash__ = Segment.__hash__

	intersection = gcast(Segment.intersection)


	def __eq__(self, other):
		return False if not isinstance(other, Segment) else super().__eq__(other)

	@property
	def length(self): return super().length()


	def intersecting(self, check, ignore:Point | Collection[Point]=()) -> set[Segment]:
		"""Return objects in check that this GSegment intersects with, optionally
		ignoring intersections with Points in ignore."""
		ignore = [None] + listify(ignore)
		return {o for o in listify(check) if
				self != o and
				(isinstance(o, Point) and o not in ignore and o in self) or
				(self.intersection(o) not in ignore)}


	def intersection2d(self, other):
		return self.as2d().intersection(other.as2d())


	def as2d(self):
		if self.start_point.z == 0 and self.end_point.z == 0:
			return self
		return GSegment(self.start_point.as2d(), self.end_point.as2d())


	def set_z(self, z):
		"""Set both endpoints of this Segment to a new z."""
		return self.copy(z=z)


	def copy(self, start_point=None, end_point=None, z=None, **kwargs):
		seg = GSegment(
			start_point or self.start_point,
			end_point   or self.end_point,
			z=z, **self.info)

		return seg


	def moved(self, vec=None, x=None, y=None, z=None):
		"""Return a copy of this GSegment moved by vector vec or coordinates."""
		sp = self.start_point if isinstance(self.start_point, GPoint) else GPoint(self.start_point)
		ep = self.end_point   if isinstance(self.end_point,   GPoint) else GPoint(self.end_point)
		return self.copy(sp.moved(vec, x, y, z), ep.moved(vec, x, y, z))


	def parallels2d(self, distance=1, inc_self=False):
		"""Return two GSegments parallel to this one, offset by `distance` to either
		side. Include this segment if in_self is True."""
		v = self.line.dv.normalized()
		mv1 = Vector(v[1], -v[0], v[2]) * distance
		mv2 = Vector(-v[1], v[0], v[2]) * distance
		return [self.moved(mv1), self.moved(mv2)] + ([self] if inc_self else [])


	#Support +/- with a GPoint by treating the point as a vector
	def __add__(self, other:GPoint): return self.moved(Vector(*other))
	def __sub__(self, other:GPoint): return self.moved(Vector(*-other))


	def __mul__(self, other):
		"""Lengthen the segment, preserving its start point."""
		if not isinstance(other, (int, float)):
			return self * other
		return self.copy(end_point=self.end_point.moved(
			self.line.dv.normalized() * self.length * (other-1)))


	def point_at_dist(self, dist:int|float, from_end=False) -> GPoint:
		"""Return the point that is `dist` from this GSegment's start point (end
		point) in the direction of the GSegment. Note that the returned point might
		not be on the GSegment!"""
		if from_end:
			return self.end_point - self.line.dv.normalized() * dist
		else:
			return self.start_point + self.line.dv.normalized() * dist


	def split_at(self, split_loc:GPoint):
		"""Return a set of two GSegments resulting from splitting this one into two
		pieces at `location`."""
		from gcline import GCLines

		if split_loc not in self:
			raise ValueError(f"Requested split location {split_loc} isn't on {self}")

		#Create the new segment pieces; drop any extra gcode from the second since
		# it should stay attached to the first
		seg1 = self.copy(end_point   = split_loc)
		seg2 = self.copy(start_point = split_loc)
		seg2.info.pop('prev_lines', None)

		seg1_frac = seg1.length / self.length
		seg2_frac = 1 - seg1_frac

		seg2_lineno = seg2.info.get('line_params', {}).get('lineno')
		if seg2_lineno is not None:
			seg2.info['line_params']['lineno'] += seg2_frac

		#If this is an extruding segment, we need to split the extrusion amount
		# proportionally by length
		if self.is_extrude:
			seg1.extrude_amount *= seg1_frac
			seg2.extrude_amount *= seg2_frac

		return [seg1, seg2]


	def split(self, locations:GPoint|Collection[GPoint]) -> list[GSegment]:
		"""Split this GSegment into multiple pieces at the given `locations`."""
		locations = listify(locations)
		splits    = []
		to_split  = self

		for loc in sorted(locations, key=self.start_point.distance):
			seg1, seg2 = to_split.split_at(loc)
			splits.append(seg1)
			to_split = seg2
		splits.append(seg2)

		return splits


	def distance(self, other):
		if isinstance(other, GPoint):
			return other.distance(self.closest(other))
		return distance_linelike_point(self, other)


	#Source: https://math.stackexchange.com/a/3128850/205121
	def closest(self, other:GPoint) -> GPoint:
		"""Return the point on this GSegment that is closest to the given point."""
		#Convert points to vectors for easy math
		seg_start = Vector(self.start_point.x, self.start_point.y, 0)
		seg_end   = Vector(self.end_point.x,   self.end_point.y,   0)
		p         = Vector(other.x,            other.y,            0)

		v = seg_end - seg_start
		u = seg_start - p

		vu = v[0]*u[0] + v[1]*u[1]
		vv = v * v

		t = -vu / vv

		if 0 < t < 1: return GPoint(*(self.line.dv * t + self.start_point))
		elif t <= 0:  return self.start_point
		else:         return self.end_point


	def angle(self) -> Angle:
		"""Return the angle between this segment and the X axis."""
		return atan2(self.end_point.y - self.start_point.y, self.end_point.x - self.start_point.x)
