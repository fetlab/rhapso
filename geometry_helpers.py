#from Geometry3D import Vector, Point, Segment, Line, Plane
from gcline import GCLines
from dataclasses import make_dataclass
from typing import List, Dict, Collection, Set
from collections import defaultdict
from more_itertools import flatten

from geometry.gpoint import GPoint
from geometry.gsegment import GSegment
from geometry.ghalfline import GHalfLine, GHalfLine as HalfLine
from geometry.utils import tangent_points, eps


Geometry = make_dataclass('Geometry', ['segments', 'planes', 'outline'])
Planes   = make_dataclass('Planes',   ['top', 'bottom'])


def visibility4(origin:GPoint, query:Collection[GSegment], avoid_by=1) -> Dict[GPoint, Set]:
	"""Calculate visibility for `origin` with respect to `query`, attempting to
	ensure `avoid_by` mm of avoidance. For every potential visibility point,
	return the segments intersected by a ray from `origin` to that point:

		{visible_point: {segments intersected}, ...}

	This returned dict is sorted by the number of intersected segments.
	"""
	endpoints = set(flatten(query)) - {origin}
	tanpoints = set(flatten(
			tangent_points(p, avoid_by, origin) for p in endpoints if
			origin.distance(p) > avoid_by))
	isecs:Dict[GPoint, Set] = {}
	isec_points:Dict[GPoint, Set] = {}

	for tp in tanpoints:
		hl = HalfLine(origin, tp)
		isecs[tp] = set()
		isec_points[tp] = set()
		for seg in query:
			isec = False
			isec_points[tp] = hl.intersecting(seg)
			if isec_points[tp]:
				isec = True
			if not isec:
				if seg.start_point != origin:
					d = hl.distance(seg.start_point)
					if d is not None and (d - avoid_by <= -eps):
						isec = True
						isec_points[tp] = (f'dist from {hl} to start {seg.start_point} = {d} < {avoid_by}', hl, seg)
			if not isec:
				d = hl.distance(seg.end_point)
				if d is not None and (d - avoid_by <= -eps):
					isec = True
					isec_points[tp] = (f'dist from {hl} to end {seg.end_point} = {d} < {avoid_by}',
												hl, seg)

			if isec:
				isecs[tp].add(seg)

	return dict(sorted(isecs.items(), key=lambda x:len(x[1]))), isec_points


def too_close(a, b, by=1):
	"""Return True if the distance between `a` and `b` is <= `by` (taking into
	account imprecision via `eps`)."""
	d = a.distance(b)
	return False if d is None else d - by <= -eps


#Combine subsequent segments on the same line
def seg_combine(segs):
	if not segs: return []
	r = [segs[0]]
	for seg in segs[1:]:
		if seg.line == r[-1].line:
			# print(f'Combine {r[-1]}, {seg}', end='')
			if seg.end_point == r[-1].start_point:
				r[-1] = GSegment(seg.start_point, r[-1].end_point)
			elif r[-1].end_point == seg.start_point:
				r[-1] = GSegment(r[-1].start_point, seg.end_point)
			else:
				s1 = GSegment(  seg.start_point, r[-1].end_point)
				s2 = GSegment(r[-1].start_point,   seg.end_point)
				r[-1] = max(s1, s2, key=lambda s: s.length())
			# print(f' -> {r[-1]}')
		else:
			# print(f"Don't combine {r[-1]}, {seg}")
			r.append(seg)
	return r


def gcode2segments(lines:GCLines, z, keep_moves_with_extrusions=True):
	"""Turn GCLines into GSegments. Keep in mind that the first line denotes the start
	point only, and the second line denotes the action (e.g. extrude) *and* the end
	point. Mark extrusion GSegments. Return preamble, segments, postamble.

	Set keep_moves_with_extrusions to False to make pairs of non-extruding
	movements into independent GSegments; otherwise, sequences of non-extrusion
	moves preceding an extrusion move will be grouped into the extrusion move.
	"""
	lines    = lines.copy()
	last     = None
	extra    = GCLines()
	preamble = GCLines()
	segments = []

	#Put all beginning non-extrusion lines into preamble
	while lines and not lines.first.is_xyextrude():
		preamble.append(lines.popidx(0))

	#Put back lines from the end until we get an xymove
	putback = []
	while preamble and not preamble.last.is_xymove():
		putback.append(preamble.popidx(-1))
	if preamble.last.is_xymove(): putback.append(preamble.popidx(-1))
	if putback: lines = list(reversed(putback)) + lines

	#Put the first xymove as the "last" item
	last = lines.popidx(0)

	if keep_moves_with_extrusions:
		for line in lines:
			if line.is_xyextrude():
				line.segment = GSegment(last, line, z=z, gc_lines=extra, is_extrude=line.is_xyextrude())
				segments.append(line.segment)
				last = line
				extra = GCLines()
			elif line.is_xymove():
				if not last.is_xyextrude():
					extra.append(last)
				last = line
			else:
				extra.append(line)
		if not last.is_xyextrude() and last not in extra:
			extra.append(last)
			extra.sort()

	else:
		#Now take pairs of xymove lines, accumulating intervening non-move lines in
		# extra
		for line in lines:
			if line.is_xymove():
				line.segment = GSegment(last, line, z=z, gc_lines=extra, is_extrude=line.is_xyextrude())
				segments.append(line.segment)
				last  = line
				extra = GCLines()
			else: #non-move line following a move line
				extra.append(line)

	return preamble, segments, extra


# # ------- Monkey patching for improved Geometry3D objects ------

# # --- Point
# @patch
# def __repr__(self:GPoint):
# 	return "!{{{:>6.2f}, {:>6.2f}, {:>6.2f}}}".format(self.x, self.y, self.z)
# @patch
# def as2d(self:GPoint):
# 	return Point(self.x, self.y, 0)
# @patch
# def xyz(self:GPoint):
# 	return self.x, self.y, self.z
# @patch
# def xy(self:GPoint):
# 	return self.x, self.y
# Point.inside = GPoint.inside


# # --- Segment
# @patch
# def __repr__(self:GSegment):
# 	return "<{}←→{}>".format(self.start_point, self.end_point)
# @patch
# def as2d(self:GSegment):
# 	return GSegment(self.start_point.as2d(), self.end_point.as2d())
# @patch
# def xyz(self:GSegment):
# 	x, y, z = tuple(zip(self.start_point.xyz(), self.end_point.xyz()))
# 	return dict(x=x, y=y, z=z)
# @patch
# def xy(self:GSegment):
# 	x, y = tuple(zip(self.start_point.xy(), self.end_point.xy()))
# 	return dict(x=x, y=y)


# # --- Vector
# @patch
# def __repr__(self:Vector):
# 	return "V({:.2f}, {:.2f}, {:.2f})".format(*self._v)


# # --- Plane
# @patch
# def pointcmp(self:Plane, point:GPoint):
# 	"""Return whether point is below (-1), on (0), or above (1) plane."""
# 	isec = Line(point, self.n).intersection(self)
# 	return sign(Vector(isec, point) * self.n)
