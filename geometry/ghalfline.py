from typing import Collection, Set
from math import sin, cos
from fastcore.basics import listify, ifnone
from Geometry3D import Line, Vector, HalfLine, Point, Segment, Plane, angle
from Geometry3D.utils import get_eps
from .gpoint import GPoint
from .utils import distance_linelike_point
from .gcast import gcast
from .angle import Angle, atan2

_eps = get_eps()

class GHalfLine(HalfLine):
	def __init__(self, a:Point|HalfLine, b:Point|Vector|Angle|None=None):
		if isinstance(a, HalfLine):
			a, b = a.parametric()
		else:
			a = GPoint(a) if isinstance(a, (tuple, list, set, Point)) else a
			b = GPoint(b) if isinstance(b, (tuple, list, set, Point)) else b

		if not isinstance(a, Point):
			raise ValueError(f'First argument to GHalfLine must be Point or HalfLine, not {type(a)}')

		if isinstance(b, Point):
			if a == b: raise ValueError("Cannot initialize a HalfLine with two identical Points")
			b = Vector(a, b)
		elif isinstance(b, Angle):
			b = Vector(cos(b), sin(b), 0)
		elif isinstance(b, Vector):
			if b.length() < _eps: raise ValueError("Cannot initialize a HalfLine with the length of Vector is 0")
		else:
			raise ValueError(f'Second argument to GHalfLine must be Point, Vector, or Angle, not {type(b)}')

		self.line   = Line(a, b)
		self.point  = a
		self.vector = b

	_intersection = HalfLine.intersection
	intersection  = gcast(HalfLine.intersection)


	def as2d(self):
		return self.__class__(GPoint.as2d(self.point), Vector(self.vector[0], self.vector[1], 0))


	def intersecting(self, check:Collection[Segment]) -> Set[Segment]:
		"""Return Segments in check which this HalfLine intersects with,
		ignoring intersections with the start point of this HalfLine."""
		return {seg for seg in listify(check) if self._intersection(seg) not in [None, self.point]}


	def intersections(self, check:Collection[Segment]) -> Set[Segment]:
		"""Return all intersection points of this GHalfLine with the Segments in
		`check`, where the intersection is not the start point of this HalfLine."""
		return {seg for seg in filter(lambda i: i not in [None, self.point],
											[self._intersection(seg) for seg in listify(check)])}


	def __repr__(self):
		return "H({}, {})".format(self.point, self.vector)


	def distance(self, other):
		return distance_linelike_point(self, other)


	def copy(self, *, point:Point|None=None, vec:Vector|None=None):
		p, v = self.parametric()
		return self.__class__(ifnone(point, p), ifnone(vec, v))


	def moved(self, *args, **kwargs):
		"""Move the half line's origin point without changing its angle."""
		return self.__class__(self.point.moved(*args, **kwargs), self.vector)


	def rotated(self, by_angle:Angle):
		"""Return a copy of the half line, rotated by `by_angle` about its origin
		point."""
		return self.__class__(self.point, self.angle + by_angle)


	def parallels2d(self, distance=1, inc_self=False):
		"""Return two GHalfLines parallel to this one, offset by `distance` to either
		side. Include this halfline if in_self is True."""
		v = self.vector.normalized()
		mv1 = Vector(v[1], -v[0], v[2]) * distance
		mv2 = Vector(-v[1], v[0], v[2]) * distance
		return [self.moved(mv1), self.moved(mv2)] + ([self] if inc_self else [])


	@property
	def angle(self) -> Angle:
		return atan2(self.vector[1], self.vector[0])



	def repr_diff(self, b:'GHalfLine', newline=False):
		"""Return a printable string showing the differences between the two, only
		in 2D."""
		a = self
		if a == b: return ''
		if a.point.as2d() != b.point.as2d():
			if a.angle != b.angle:
				p1 = 'Move and rotate'
				p2 = f'{a.angle:>6.2f}°/{a.point}'
				p3 = f'{b.angle:>6.2f}°/{b.point}'
			else:
				p1 = 'Move'
				p2 = f'{a.point}'
				p3 = f'{b.point} ({b.angle:>6.2f})°'
		else:
			p1 = 'Rotate'
			p2 = f'{a.angle:>6.2f}°'
			p3 = f'{b.angle:>6.2f}° ({b.point})'
		if newline:
			return f'{p1} {p2} →\n{" "*len(p1)} {p3}'
		else:
			return f'{p1} {p2} → {p3}'
