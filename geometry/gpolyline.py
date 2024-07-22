from typing import Collection
from itertools import pairwise
from more_itertools import flatten
from fastcore.basics import first
from Geometry3D import Vector
from util import Number
from functools import partial
from .gpoint   import GPoint
from .gsegment import GSegment

class GPolyLine:
	def __init__(self, points: list[GPoint]|list[tuple[Number,Number,Number]], monotonic_z=True):
		"""Set `ensure_increasing` to True to raise an error when points in
		`points` are not monotonically increasing in the z axis."""
		self.monotonic_z = monotonic_z
		self.points = points


	def __repr__(self): return ' → '.join(map(repr, self.points))
	def __len__(self):  return len(self.segments)


	@property
	def points(self):
		return [self.segments[0].start_point] + [seg.end_point for seg in self.segments]


	@points.setter
	def points(self, points: list[GPoint]|list[tuple[Number,Number,Number]]):
		points = [p if isinstance(p, GPoint) else GPoint(*p) for p in points]
		if self.monotonic_z and not all((b.z - a.z >= 0 for a,b in pairwise(points))):
			raise ValueError("Two points in passed sequence decrease in z!")
		self.segments = [GSegment(a, b) for a,b in pairwise(points)]


	def index(self, seg:GSegment) -> int:
		try:
			return self.segments.index(seg)
		except ValueError:
			raise ValueError(f"Passed segment {seg} is not part of this GPolyLine:\n{self.segments}")


	def findseg(self, start:GPoint=None, end:GPoint=None) -> GSegment:
		"""Return the first matching segment."""
		if start is None and end is None or start is not None and end is not None:
			raise ValueError("Provide exactly one of start/end")
		return first(self.segments,
			lambda seg: seg.start_point == start if start is not None else seg.end_point == end)


	def insert(self, where:int, point:GPoint):
		"""Insert the passed point into the polyline."""
		points = self.points
		points.insert(where, point)
		self.points = points


	def remove(self, point):
		"""Remove the passed point from the polyline."""
		points = self.points
		points.remove(point)
		self.points = points


	def split(self, seg:GSegment, locations:GPoint|Collection[GPoint]) -> list[GSegment]:
		"""Split the given segment of this GPolyLine into pieces at the provided
		`locations`. Return the new segments."""
		i = self.index(seg)
		new_segs = seg.split(locations)
		self.segments = self.segments[:i] + new_segs + self.segments[i+1:]
		return new_segs


	def move(self, what:GPoint, to:GPoint|None=None, **kwargs) -> GPoint:
		"""Move the passed point. Modifies this GPolyLine by creating a
		copy of the point, which is subsequently returned."""
		if self.segments[0].start_point == what:
			s,e = self.segments[0][:]
			if to is not None:
				self.segments[0] = GSegment(s.copy(start_point=to))
			else:
				self.segments[0] = GSegment(s.moved(**kwargs), e)
			return self.segments[0].start_point

		for i,seg in enumerate(self.segments):
			if seg.end_point == what: break
		if seg.end_point != what:
			raise ValueError(f"Passed point {what} is not part of this GPolyLine:\n{self}")

		s,e = seg[:]
		np = to if to is not None else e.moved(**kwargs)
		self.segments[i] = GSegment(s, np)
		if i < len(self.segments) - 1:
			ee = self.segments[i+1].end_point
			self.segments[i+1] = GSegment(np, ee)
		return np
