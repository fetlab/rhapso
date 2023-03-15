from typing import Collection, Set
from fastcore.basics import listify
from Geometry3D import Vector, HalfLine, Point, Segment, Plane
from .gpoint import GPoint
from .utils import distance_linelike_point
from .gcast import gcast

class GHalfLine(HalfLine):
	def __init__(self, a, b=None):
		if isinstance(a, HalfLine):
			a, b = a.parametric()
		else:
			a = GPoint(a) if isinstance(a, (tuple, list, set, Point)) else a
			b = GPoint(b) if isinstance(b, (tuple, list, set, Point)) else b
		super().__init__(a, b)

	_intersection = HalfLine.intersection
	intersection  = gcast(HalfLine.intersection)


	def as2d(self):
		return self.__class__(GPoint.as2d(self.point), Vector(self.vector[0], self.vector[1], 0))


	def intersecting(self, check:Collection[Segment]) -> Set[Segment]:
		"""Return Segments in check which this HalfLine intersects with,
		ignoring intersections with the start point of this HalfLine."""
		return {gcast(seg) for seg in listify(check) if self._intersection(seg) not in [None, self.point]}


	def intersections(self, check:Collection[Segment]) -> Set[Segment]:
		"""Return all intersection points of this GHalfLine with the Segments in
		`check`, where the intersection is not the start point of this HalfLine."""
		return {gcast(seg) for seg in filter(lambda i: i not in [None, self.point],
											[self._intersection(seg) for seg in listify(check)])}


	def __repr__(self):
		return "H({}, {})".format(self.point, self.vector)


	def distance(self, other):
		return distance_linelike_point(self, other)


	def moved(self, vec):
		point = self.point if isinstance(self.point, GPoint) else GPoint(self.point)
		return self.__class__(point.moved(vec), self.vector)


	def parallels2d(self, distance=1, inc_self=False):
		"""Return two GHalfLines parallel to this one, offset by `distance` to either
		side. Include this halfline if in_self is True."""
		v = self.vector.normalized()
		mv1 = Vector(v[1], -v[0], v[2]) * distance
		mv2 = Vector(-v[1], v[0], v[2]) * distance
		return [self.moved(mv1), self.moved(mv2)] + ([self] if inc_self else [])

