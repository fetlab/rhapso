from Geometry3D import Vector, Line, get_eps
from gcline import GCLines
from dataclasses import make_dataclass
from typing import List, Dict, Collection, Set
from collections import defaultdict
from more_itertools import flatten

from geometry import GPoint, GSegment, GHalfLine
from geometry.utils import tangent_points, eps, sign
from geometry.gcast import gcastr


Geometry = make_dataclass('Geometry', ['segments', 'planes', 'outline'])
Planes   = make_dataclass('Planes',   ['top', 'bottom'])


def visibility(origin:GPoint, query:Collection[GSegment], avoid_by=1) -> Dict[GPoint, Set]:
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
		hl = GHalfLine(origin, tp)
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


#Source: https://web.archive.org/web/20171110082203/http://www.geomalgorithms.com/a07-_distance.html
def cpa_time(seg1:GSegment, seg2:GSegment):
	"""Determine the "time" at which the closest point of approach occurs between
	the two segments."""
	v1 = Vector(*seg1)
	v2 = Vector(*seg2)
	dv = v1 - v2
	dv2 = dv * dv

	if dv2 < get_eps(): return 0

	w0 = Vector(seg2.start_point, seg1.start_point)
	return -(w0 * dv) / dv2


#Source: https://web.archive.org/web/20171110082203/http://www.geomalgorithms.com/a07-_distance.html
def cpa(seg1:GSegment, seg2:GSegment):
	"""Return the closest points of approach on the two segments."""
	c = cpa_time(seg1, seg2)
	return (seg1.start_point + c * Vector(*seg1),
					seg2.start_point + c * Vector(*seg2))


"""We want to determine if, for a particular printed segment, the print head
will intersect the line between the anchor and the ring. So, given the
trajectory of the head in X, we want to find the trajectory of the point that
is the intersection of the thread and the X axis, and then compare those
trajectories to see if there is an intersection. If there is, then we need to
move the thread so that it doesn't intersect any more.

To get the trajectory of the intersecting point, we want to move the anchor by
the negative of the printed segment's starting Y coordinate, to simulate the
bed moving to place this point under the X axis. Then we can check the thread
intersection with the X axis. We do the same for the printed segment's ending Y
coordinate. Then we have the trajectory between the two intersecting X points
which we can use cpa() to compare.

There can be a degenerate condition where the Y coordinates of the thread
carrier, the thread anchor, and the start and end of a printed segment are all
the same. In this case the function will return a GSegment rather than a
GPoint.
"""
def traj_isec(seg:GSegment, thread:GSegment) -> None|GPoint|GSegment:
	tx1 = Line.x_axis().intersection(
		GSegment(
			thread.start_point.moved(y=-seg.start_point.y),
			thread.end_point,
			z=0))
	if not tx1: return None

	tx2 = Line.x_axis().intersection(
		GSegment(
			thread.start_point.moved(y=-seg.end_point.y),
			thread.end_point,
			z=0))
	if not tx2: return None

	if tx1 == tx2:
		return gcastr(tx1) if (seg.start_point.x <= tx1.x <= seg.end_point.x or
													 seg.start_point.x >= tx1.x >= seg.end_point.x) else None

	thr_traj  = GSegment(tx1, tx2)

	#The trajectory of the head on the x axis. Assign tiny values to y to easily
	# account for vertical segments.
	head_traj = GSegment((seg.start_point.x, -.001, 0), (seg.end_point.x, .001, 0))

	appr1, appr2 = cpa(thr_traj, head_traj)
	return gcastr(appr1) if appr1 == appr2 else None
