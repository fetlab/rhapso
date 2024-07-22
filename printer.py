from collections import defaultdict
from typing import Collection
from itertools import groupby
from more_itertools import flatten
from fastcore.basics import first
from Geometry3D import Vector
from rich.pretty import pretty_repr

from util import attrhelper
from geometry import GPoint, GSegment, GHalfLine
from logger import rprint
from geometry_helpers import visibility, too_close
from geometry.utils import angsort, ang_diff
from steps import Steps


class Printer:
	def __init__(self, initial_thread_path:GHalfLine):
		#The current path of the thread: the current thread anchor and the
		# direction of the thread.
		self._thread_path = initial_thread_path

		self.target:Vector|GPoint = None


	#Create attributes which call Printer.attr_changed on change
	x = property(**attrhelper('head_loc.x'))
	y = property(**attrhelper('head_loc.y'))
	z = property(**attrhelper('head_loc.z'))

	@property
	def anchor(self): return self.thread_path.point

	@property
	def xy(self): return self.x, self.y


	@property
	def xyz(self): return self.x, self.y, self.z


	def __repr__(self):
		return f'Printer(🧵={self.thread_path})'


	@property
	def thread_path(self): return self._thread_path


	@thread_path.setter
	def thread_path(self, new_path):
		#This bit just does debug printing
		if new_path.point != self.thread_path.point and new_path.angle != self.thread_path.angle:
			raise ValueError("Simultaneously setting both point and angle for thread not allowed")
		if new_path.point != self.thread_path.point:
			rprint(f'[green]****[/] Move thread at angle {self.thread_path.angle}°'
					f' from {self.thread_path.point} to {new_path.point}')
		if new_path.angle != self.thread_path.angle:
			rprint(f'[green]****[/] Rotate thread at point {self.thread_path.point}'
					f' from {self.thread_path.angle}° to {new_path.angle}°')

		#Assign even if they're the same, just in case the new one is a copy or
		# something
		self._thread_path = new_path


	def move_thread_to(self, new_anchor:GPoint):
		self.thread_path = GHalfLine(new_anchor, self.thread_path.vector)


	def rotate_thread_to(self, target:Vector|GPoint):
		self.target = target
		self.thread_path = GHalfLine(self.thread_path.point, target)


	def avoid_and_print(self, steps: Steps, avoid: Collection[GSegment]|None=None, extra_message='', avoid_by=1):
		"""Loop to print everything in `avoid` without thread intersections."""
		avoid = set(avoid or [])
		repeats = 0
		while avoid:
			repeats += 1
			rprint(f'Avoid and print {len(avoid)} segments, iteration {repeats}')
			if repeats > 5: raise ValueError("Too many repeats")
			with steps.new_step(f"Move thread to avoid printing over it with {len(avoid)} segments?" + extra_message) as s:
				if isecs := self.thread_avoid(avoid, avoid_by):
					rprint(f"{len(isecs)} thread/segment intersections")
				avoid -= isecs
			if s.thread_path == s.original_thread_path:
				rprint(f'No change in thread path in step {s}, marking it as not valid')
				s.valid = False

			if avoid:
				with steps.new_step(f"Print {len(avoid)} segments thread doesn't intersect" + extra_message) as s:
					s.add(avoid)
				if not isecs: break
			avoid = isecs
		rprint(f'Finished avoid and print')


	def thread_avoid(self, avoid: Collection[GSegment], avoid_by=1) -> set[GSegment]:
		"""Move thread_path to try to make the thread's trajectory avoid the
		segments in `avoid` by at least `avoid_by`. Return any printed segments
		that could not be avoided."""
		assert(avoid)
		avoid = set(avoid)

		rprint(f'Avoiding {len(avoid)} segments with thread {self.thread_path}')

		anchor = self.thread_path.point

		#If there's only one segment in avoid, and the anchor point is either on it
		# or within `avoid_by` of it, move the thread to be perpindicular to it.
		if len(avoid) == 1:
			seg = first(avoid)
			if (anchor in seg or
					too_close(anchor, seg.start_point, avoid_by) or
					too_close(anchor, seg.end_point,   avoid_by)):

				#Get the two perpendicular half-lines to the segment
				perp1 = GHalfLine(anchor, Vector(-seg.line.dv[1], seg.line.dv[0], 0))
				perp2 = GHalfLine(anchor, Vector(seg.line.dv[1], -seg.line.dv[0], 0))

				### BUG: for now, just pick the first one
				#Find the perpendicular path that requires the least movement from
				# the current path
				rprint(f'[yellow]WARNING:[/] anchor {anchor} is too close to or on top of only segment {seg}')
				self.thread_path = perp1# if abs(ang_diff(perp1.angle, self.thread_path.angle)) else perp2

				return set()

		if not (isecs := self.thread_path.intersecting(avoid)):
			#Thread is already not intersecting segments in `avoid`, but we want to try
			# to move it so it's not very close to the ends of the segments either.

			#If avoid_by isn't > 0, then we don't need to do anything else, so we're done.
			if avoid_by <= 0:
				return isecs

			rprint(f'No intersections, ensure thread avoids segments by at least {avoid_by} mm')

			#All printed segment starts & ends, minus the thread's start point
			endpoints  = set(flatten(avoid)) - {self.thread_path.point}

			#We can't avoid points that are too close to the anchor - not physically possible
			avoidables = set(ep for ep in endpoints if anchor.distance(ep) > avoid_by)

			#Find segments where one or more of the endpoints are too close to the
			# thread path and label them as intersecting (but not if that endpoint is
			# next to the anchor, as it's not physically possible to move the thread
			# to get far enough away.)
			isecs = {seg for seg in avoid
				if any(too_close(self.thread_path, ep, avoid_by)
								for ep in seg[:] if not too_close(anchor, ep, avoid_by))}

			#If none of the end points are closer than `avoid_by` to the
			# thread, return the empty set to indicate we didn't have a problem
			# avoiding any of them.
			#If the segments that are too close are only a subset of those we were
			# trying to avoid, return those.
			if not isecs or isecs != avoid:
				return isecs

			rprint(f'{len(isecs)} segments too close to thread path, same as we wanted to avoid')

		else:
			#Let's try to simply drop every segment the thread intersects or that comes
			# too close to the thread.
			rprint(f'    {len(isecs)} intersections')

			#Add to `isecs` every segment in `avoid` that is too close to the thread
			isecs.update({seg for seg in (avoid - isecs) if
				too_close(self.thread_path, seg.start_point, by=avoid_by) or
				too_close(self.thread_path, seg.end_point,   by=avoid_by)})

			#If there is anything left, return `isecs` so we can subtract from `avoid` in the caller
			if isecs != avoid:
				return isecs


		#If we got here, either the thread intersects printed segments, or it's too
		# close to printed segment endpoints, so we have to try to move the thread.
		rprint('Thread must be moved to avoid segments')

		vis = visibility(anchor, avoid, avoid_by)
		vis_segs = defaultdict(set)
		for vp, segs in vis.items():
			vis_segs[vp].update(segs)

		rprint(f'    {len(vis)} potential visibility points')
		if len(vis) < 5:
			rprint(pretty_repr(vis))

		#We only have 1 segment to avoid but can't avoid it. Let's pretend we did
		# and see what happens.
		if len(avoid) == 1 and len(vis_segs) == 1 and first(vis_segs) == first(avoid):
			rprint(f"Can't avoid only segment {first(avoid)}, giving up on trying")
			return set()

		#Get all of the visibility points with N intersections, where N is the
		# smallest number of intersections
		_, vis_points = next(groupby(vis, key=lambda k:len(vis[k])))

		#Then sort by distance from the thread
		vis_points = angsort(list(vis_points), ref=self.thread_path)

		old_thread = self.thread_path

		#Now move the thread to overlap the closest one
		self.rotate_thread_to(vis_points[0])

		#If the visibility point with the smallest number of intersections still
		# intersects the segments in `avoid`, it's probably too close to avoid.
		if vis[vis_points[0]] == avoid:
			rprint("Result of visibility:", vis[vis_points[0]], "is the same thing we tried to avoid:",
					avoid, indent=4)
			self._debug_quickplot_args = dict(gc_segs=avoid, anchor=anchor, thread_ring=self.thread_path)
			raise ValueError("thread_avoid() couldn't avoid; try running\n"
				"plot_helpers.quickplot(**threader.layer_steps[-1].printer._debug_quickplot_args);")

		#Return the set of segments that we intersected
		return vis[vis_points[0]]
