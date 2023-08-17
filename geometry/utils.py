from __future__ import annotations
from math import pi, sin, cos, radians
from typing import Collection, List, TYPE_CHECKING
from more_itertools import first
from Geometry3D import Point, Segment, Line, Vector, Plane, HalfLine
from Geometry3D.utils import get_eps
from .gpoint import GPoint
from .angle import Angle, atan2, acos, asin

if TYPE_CHECKING:
	from .gsegment import GSegment
	from .ghalfline import GHalfLine

eps = get_eps()

def sign(n): return -1 if n < 0 else (1 if n > 0 else 0)


def eq2d(a, b):
	"""Test equality only on x and y."""
	if not (isinstance(a, b.__class__) or isinstance(b, a.__class__)): return False
	try: return eq2d(a[0], b[0])  #Covers Segment, Point, Vector
	except (IndexError, TypeError): return a == b


def min_max_xyz(objs:Collection):
	"""Given a list of Points or Segments, return
		(minx, miny, minz), (maxx, maxy, maxz)"""
	if isinstance(first(objs), Point):
		return min_max_xyz_points(objs)
	if isinstance(first(objs), Segment):
		return min_max_xyz_segs(objs)


def min_max_xyz_points(points:Collection[Point]):
	"""Return (minx, miny, minz), (maxx, maxy, maxz)"""
	x,y,z = list(zip(*[p[:] for p in points]))
	return (min(x), min(y), min(z)), (max(x), max(y), max(z))


def min_max_xyz_segs(segs:Collection[Segment]):
	"""Return (minx, miny, minz), (maxx, maxy, maxz)"""
	x,y,z = list(zip(*
				[((seg.start_point.x, seg.end_point.x),
					(seg.start_point.y, seg.end_point.y),
					(seg.start_point.z, seg.end_point.z)) for seg in segs]))
	return (min(x), min(y), min(z)), (max(x), max(y), max(z))


def atan2p(y, x) -> Angle:
	"""Return atan2(y,x), but ensure it's positive by adding 2pi if it's
	negative."""
	ang = atan2(y,x)
	return ang if ang > 0 else ang + 2*pi


def ccw(a:Point, b:Point, c:Point) -> Angle:
	"""Compare the angles of a and b with respect to c as a center point. If a is
	collinear to b, return 0; return negative if a is counter-clockwise from b,
	and positive if it is clockwise."""
	return atan2p(a.y-c.y, a.x-c.x) - atan2p(b.y-c.y, b.x-c.x)


def ccw_dist(p,a,c) -> Angle:
	"""Return CCW angular distance of point P from the line formed by a-c"""
	v = atan2(a.y-c.y,a.x-c.x)-atan2(p.y-c.y,p.x-c.x)
	return v if v > 0 else v + 2*pi


#Source: https://stackoverflow.com/a/28037434
def ang_diff(a:Angle, b:Angle) -> Angle:
	"""Return the shortest distance to go between angles a and b."""
	diff = (b - a + pi) % (2*pi) - pi
	return diff + 2*pi if diff < -pi else diff


def ang_dist(p,c,a) -> Angle:
	"""Return the angular distance of Point p with respect to the line formed by c->a"""
	return atan2(p.y-c.y, p.x-c.x) - atan2(a.y-c.y, a.x-c.x)


def angsort(points: Collection[Point], ref:Segment|HalfLine) -> List[Point]:
	"""Return points sorted with respect to their (absolute) angle to the
	reference segment."""
	s, e = ref[:] if isinstance(ref, Segment) else (ref.point, ref.point.moved(ref.vector))
	return sorted(points, key=lambda p: abs(ang_dist(p, s, e)))


def point_plane_comp(point:Point, plane:Plane):
	"""Return whether point is below (-1), on (0), or above (1) plane."""
	isec = Line(point, plane.n).intersection(plane)
	return sign(Vector(isec, point) * plane.n)


def point_line_comp(point:Point, line:Segment|Line):
	"""Return whether point is on one side (1) or the other (-1) or on (0) the
	line. Ignores the z coordinate."""
	a = line.start_point
	b = line.end_point
	return sign((b.x - a.x) * (point.y - a.y) - (b.y - a.y) * (point.x - a.x))


#Source: https://math.stackexchange.com/questions/543496/
def tangent_points(center:Point, radius, p:Point):
	"""Given a circle at center with radius, return the points on the circle that
	form tanget lines with point p."""
	from .gpoint import GPoint

	dx, dy = p.x-center.x, p.y-center.y
	dxr, dyr = -dy, dx
	d = (dx**2 + dy**2)**.5
	if d < radius:
		raise ValueError(f'Point {p} is closer to center {center} than radius {radius}')

	rho = radius/d
	ad = rho**2
	bd = rho*(1-rho**2)**.5
	return (
		GPoint(center.x + ad*dx + bd*dxr, center.y + ad*dy + bd*dyr, center.z),
		GPoint(center.x + ad*dx - bd*dxr, center.y + ad*dy - bd*dyr, center.z))


def distance_linelike_point(linelike, point):
	_valid_linelike_types = (HalfLine, Segment)

	if isinstance(linelike, Point) and isinstance(point, _valid_linelike_types):
		return distance_linelike_point(point, linelike)
	if not (isinstance(linelike, _valid_linelike_types) and isinstance(point, Point)):
		return linelike.distance(point)

	vec = linelike.vector if isinstance(linelike, HalfLine) else linelike.line.dv

	aux_plane = Plane(point, vec)
	foot = aux_plane.intersection(linelike)
	return None if foot is None else point.distance(foot)


def angle2point(angle:Angle, center:Point, radius) -> GPoint:
	return GPoint(cos(angle) * radius + center.x,
							  sin(angle) * radius + center.y,
							  center.z)


#Source: https://stackoverflow.com/a/59582674/49663
def circle_intersection(center:GPoint, radius, seg:GSegment|GHalfLine|Line) -> list[GPoint]:
		from .gsegment import GSegment
		from .ghalfline import GHalfLine
		"""Return the intersection points between a segment, HalfLine, or Line, and
		the ring, or an empty list if there are none. If the segment is tangent to
		the ring, return a list with one point. Return the list sorted by distance
		to the second point in the segment."""
		if   isinstance(seg, GSegment):  p1, p2 = seg[:]
		elif isinstance(seg, GHalfLine): p1, p2 = seg.point, seg.point + seg.vector
		elif isinstance(seg, Line):      p1, p2 = GPoint(*seg.sv), GPoint(*(seg.sv + seg.dv))
		else: raise ValueError(f"Can't intersect with {type(seg)}")

		#Shift the points by the ring center and extract x and y
		x1, y1, _ = (p1 - center)[:]
		x2, y2, _ = (p2 - center)[:]

		dx, dy, _    = (p2 - p1)[:]
		dr           = (dx**2 + dy**2)**.5
		big_d        = x1*y2 - x2*y1
		discriminant = radius**2 * dr**2 - big_d**2

		#No intersection between segment and circle
		if discriminant < 0: return []

		#Find intersections and shift them back by the ring center
		intersections = [GPoint(
			( big_d * dy + sign * (-1 if dy < 0 else 1) * dx * discriminant**.5) / dr**2,
			(-big_d * dx + sign * abs(dy) * discriminant**.5) / dr**2, 0).moved(Vector(*center))
									 for sign in ((1,-1) if dy < 0 else (-1, 1))]

		if not isinstance(seg, Line):
			hl = (GHalfLine(*seg) if isinstance(seg, GSegment) else seg).as2d()
			intersections = [p for p in intersections if p in hl]

		if len(intersections) == 2 and abs(discriminant) <= get_eps(): return [intersections[0]]

		return sorted(intersections, key=p2.distance)
