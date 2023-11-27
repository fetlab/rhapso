from __future__ import annotations
from Geometry3D import Vector, Plane, Line, get_eps
from gcline import GCLines
from gclayer import Layer
from dataclasses import make_dataclass
from typing import List, Dict, Collection, Set
from collections import defaultdict
from more_itertools import flatten

from util import Number
from geometry import GPoint, GSegment, GHalfLine, GPolyLine
from geometry.utils import tangent_points, eps, sign, point_plane_comp
from geometry.gcast import gcastr

from util import GCodeException

from typing import TYPE_CHECKING
if TYPE_CHECKING: from tlayer import TLayer

Geometry = make_dataclass('Geometry', ['segments', 'planes', 'outline'])
Planes   = make_dataclass('Planes',   ['top', 'bottom'])


def thread_z_snap(thread:GPolyLine, layer_z_heights:list[Number]) -> GPolyLine:
	"""Snap the thread vertices to the given layer heights. Split the thread if
	it passes through multiple layers. Return a modified copy."""
	#Make a copy so we don't modify the original
	thread = GPolyLine(thread.points)
	zs = layer_z_heights

	#First, snap each point in the thread to the closest layer z; skip the
	# first point as it should be the bed anchor
	for p in thread.points[1:]:
		thread.move(p, z=min(zs, key=lambda m:abs(m-p.z))-p.z)

	#Now, for any thread segment which doesn't start and end on the same layer,
	# split it; skip the first segment since it's the bed anchor as start point
	for seg in thread.segments[1:]:
		mps = zs.index(seg.start_point.z)
		mpe = zs.index(seg.end_point.z)
		if mps > mpe: mps, mpe = mpe, mps

		#For each layer height from the start point to the end point...
		for z in zs[mps:mpe+1]:
			#If the start or end point is in that layer, we're good
			if seg.start_point.z == z or seg.end_point.z == z:
				continue
			#Otherwise, the thread passes through that layer so we need to split it
			_, seg = thread.split(seg, seg.intersection(Plane(GPoint(0, 0, z), Vector.z_unit_vector())))

	return thread


def thread_snap(thread:GPolyLine, layers) -> GPolyLine:
	"""Return a copy of `thread` snapped to the z-heights and geometry in
	`layers`."""
	t = thread_z_snap(GPolyLine(thread.points), [layer.z for layer in layers])
	for layer in layers:
		layer.geometry_snap(t)
	return t


def visibility(origin:GPoint, query:Collection[GSegment], avoid_by=1) -> dict[GPoint, set]:
	"""Calculate visibility for `origin` with respect to `query`, attempting to
	ensure `avoid_by` mm of avoidance. Visibility points are the
	tangent points of a line from `origin` on a circle of radius `avoid_by`
	around each endpoint of the segments in `query`. The function returns a
	dict:

		{visible_point: {segments intersected}, ...}

	"""
	#All of the endpoints of the segments in query, except for origin
	endpoints = set(flatten(query)) - {origin}

	#All of the endpoints that are at least avoid_by mm away from origin
	farpoints = {p for p in endpoints if origin.distance(p) > avoid_by}

	#If farpoints is empty, then all of the endpoints are too close to origin
	if not farpoints: return {origin: set(query)}

	#For each point not within avoid_by mm of origin, find the tangent points of
	# a line from origin to a circle of size avoid_by around that point
	tanpoints = set(flatten(tangent_points(p, avoid_by, origin) for p in farpoints))

	intersecting_segments: Dict[GPoint, Set] = {}

	#For each tangent point, find the segments in query that intersect a half-line
	# from origin to that tangent point
	for tp in tanpoints:
		hl = GHalfLine(origin, tp)
		intersecting_segments[tp] = set()

		for seg in query:
			#Does a half-line from the origin to the tangent point intersect this segment?
			if hl.intersecting(seg):
				intersecting_segments[tp].add(seg)
			else:
				if seg.start_point != origin and too_close(hl, seg.start_point, avoid_by):
					intersecting_segments[tp].add(seg)
				elif too_close(hl, seg.end_point, avoid_by):
					intersecting_segments[tp].add(seg)

	#Sort the intersected segments by the number of segments they intersect
	return dict(sorted(intersecting_segments.items(), key=lambda x:len(x[1])))


def too_close(a, b, by=1) -> bool:
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



def gcode2segments(gclines:GCLines, z):
	from gcode_printer import GCodePrinter
	printer = GCodePrinter()

	gclines = gclines.copy()
	preamble = GCLines()
	extra = GCLines()
	segments:list[GSegment] = []

	#Extra variables to keep for this line
	keepvars = ('lineno', 'comment')

	#Put all beginning non-movement lines into preamble
	while gclines and not gclines.first.is_xymove:
		preamble.append(gclines.popidx(0))

	for line in gclines:
		printer.execute_gcode(line)
		if line.is_xymove:
			if printer.prev_loc is not None:
				segments.append(
					GSegment(printer.prev_loc, printer.head_loc, z=z,
						extrude=line.args.get('E'),
						prev_lines=extra,
						line_params={k:v for k,v in vars(line).items() if k in keepvars},
						line_args={k:v for k,v in line.args.items() if k not in 'XYZE'}))
				extra = GCLines()
		else:
			extra.append(line)

	return preamble, segments, extra


def _gcode2segments(lines:GCLines, z, keep_moves_with_extrusions=True):
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
	while lines and not lines.first.is_xyextrude:
		preamble.append(lines.popidx(0))

	#Put back lines from the end until we get an xymove
	putback = []
	while preamble and not preamble.last.is_xymove:
		putback.append(preamble.popidx(-1))
	if preamble.last.is_xymove: putback.append(preamble.popidx(-1))
	if putback: lines = list(reversed(putback)) + lines

	#Put the first xymove as the "last" item
	last = lines.popidx(0)

	if keep_moves_with_extrusions:
		for line in lines:
			if line.is_xyextrude:
				line.segment = GSegment(last, line, z=z, gc_lines=extra, is_extrude=line.is_xyextrude)
				segments.append(line.segment)
				last = line
				extra = GCLines()
			elif line.is_xymove:
				if not last.is_xyextrude:
					extra.append(last)
				last = line
			else:
				extra.append(line)
		if not last.is_xyextrude and last not in extra:
			extra.append(last)
			extra.sort()

	else:
		#Now take pairs of xymove lines, accumulating intervening non-move lines in
		# extra
		for line in lines:
			if line.is_xymove:
				line.segment = GSegment(last, line, z=z, gc_lines=extra, is_extrude=line.is_xyextrude)
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
