#Monkey-patch Geometry3D to remove its unify_types function, which appears to
# be unecessary and is extremely slow
import Geometry3D
Geometry3D.geometry.point.unify_types = lambda x: x
Geometry3D.utils.vector.unify_types   = lambda x: x


from copy import deepcopy
from geometry_helpers import GSegment
from fastcore.basics import filter_values, first
from gcline import GCLine, comment
from gcode_file import GcodeFile
from rich import print
from rich.pretty import pretty_repr
from itertools import pairwise
from geometry import GPoint, GPolyLine
from geometry.angle import Angle
from geometry_helpers import thread_layer_snap

from logger import rprint, restart_logging, reinit_logging, end_accordion_logging

from ender3 import Ender3
from steps import Steps
from util import unprinted

from Geometry3D import Vector
from geometry.angle import Angle
Vector.__repr__ = lambda self: "↗{:.2f}° ({:.2f}, {:.2f}, {:.2f})".format(
		Angle(radians=self.angle(self.x_unit_vector())), *self._v)

print('reload threader')
restart_logging()

#Epsilon for various things
thread_epsilon = 1   #Thread segments under this length (mm) get ingored/merged

"""
Usage notes:
	* The thread should be anchored on the bed such that it doesn't intersect the
		model on the way to its first model-anchor point.
"""

class Threader:
	def __init__(self, gcode_file:GcodeFile):
		self.gcode_file  = gcode_file
		self.printer     = Ender3()
		self.layer_steps: list[Steps] = []
		self.acclog      = reinit_logging()
		self._cached_gcode: list[GCLine] = []


	def save(self, filename, lineno_in_comment=False):
		if len(self.layer_steps) != len(self.gcode_file.layers):
			print(f'[red]WARNING: only {len(self.layer_steps)}/{len(self.gcode_file.layers)}'
				 ' layers were routed - output file will be incomplete!')
		with open(filename, 'w') as f:
			f.write('\n'.join([l.construct(lineno_in_comment=lineno_in_comment) for l in self.gcode()]))


	def gcode(self) -> list[GCLine]:
		"""Return the gcode for all layers."""
		if self._cached_gcode:
			return self._cached_gcode
		r = self.printer.execute_gcode(
				self.printer.gcode_file_preamble(list(self.gcode_file.preamble_layer.lines)))
		for steps_obj in self.layer_steps:
			r.append(comment(f'==== Start layer {steps_obj.layer.layernum} ===='))
			r.extend(steps_obj.gcode())
			r.append(comment(f'====== End layer {steps_obj.layer.layernum} ===='))
		r.extend(self.printer.execute_gcode(
				self.printer.gcode_file_postamble(list(self.gcode_file.postamble_layer.lines))))
		self._cached_gcode = r
		return r


	def route_model(self, thread_list: list[GPoint], start_layer=None, end_layer=None):
		if self.layer_steps: raise ValueError("This Threader has been used already")
		self.acclog = reinit_logging(self.acclog)
		self.acclog.show()
		if thread_list[0] != self.printer.bed.anchor:
			thread_list.insert(0, self.printer.bed.anchor)
		thread = GPolyLine(thread_list)
		rprint('Initial thread:', thread.points)
		thread_layer_snap(thread, self.gcode_file.layers[start_layer:end_layer])
		rprint('\nSnapped anchors to layers; anchors now:', thread.points)
		rprint(self.printer)
		for layer in self.gcode_file.layers[start_layer:end_layer]:
			try:
				self._route_layer(thread, layer)
			except:
				self.acclog.unfold()
				end_accordion_logging()
				raise

		end_accordion_logging()


	def route_layer(self, thread_list: GPolyLine, layer):
		"""Goal: produce a sequence of "steps" that route the thread through one
		layer. A "step" is a set of operations that diverge from the original
		gcode; for example, printing all of the non-thread-intersecting segments
		would be one "step".
		"""
		self.acclog = reinit_logging(self.acclog)
		self.acclog.show()
		try:
			self._route_layer(thread_list, layer)
		finally:
			self.acclog.unfold()
			end_accordion_logging()


	def _route_layer(self, thread: GPolyLine, layer):
		self.layer_steps.append(Steps(layer=layer, printer=self.printer))
		steps = self.layer_steps[-1]

		#Get just the thread anchors/segments to work with in this layer
		anchors = [anchor for anchor in thread.points if anchor.z == layer.z]

		if len(anchors) == 0:
			rprint(f'No anchors for layer {layer.layernum} - {layer.z} mm')
			#We want to avoid the computational cost of making geometry from the
			# entire layer if we're not doing anything with it, so we'll just make a
			# rectangle of segments based on the layer extents and avoid that. Might
			# not work if the extents are too big.
			(min_x, min_y), (max_x, max_y) = layer.extents()
			ext_rect = [GSegment(a, b) for a,b in (
				((min_x, min_y, layer.z), (min_x, max_y, layer.z)),
				((min_x, max_y, layer.z), (max_x, max_y, layer.z)),
				((max_x, max_y, layer.z), (max_x, min_y, layer.z)),
				((max_x, min_y, layer.z), (min_x, min_y, layer.z)))]
			with steps.new_step('Move thread to avoid layer extents', debug=False) as s:
				s.valid = bool(self.printer.thread_avoid(ext_rect))
			#Set the Layer's postamble to the entire set of gcode lines so that we
			# correctly generate the output gcode with Steps.gcode()
			layer.postamble = layer.lines
			return

		#If we got here, the first thread anchor is inside this layer, so we need
		# to do the actual work
		self.acclog.add_fold(f'Layer {layer.layernum} - {layer.z} mm', keep_closed=True)

		rprint(f'Route thread through {len(anchors)} anchor points in layer:\n {layer}',
				[f'\t{i}. {anchor}' for i, anchor in enumerate(anchors)])

		#Snap anchors to printed geometry
		anchors = layer.geometry_snap(thread)

		#Check for printed segments that have more than one thread anchor in them
		multi_anchor = filter_values(
			{seg: seg.intersecting(anchors) for seg in layer.geometry.segments},
			lambda anchors: len(anchors) > 1)
		if multi_anchor:
			rprint('[red]WARNING:[/] some segments contain more than one anchor:', pretty_repr(multi_anchor))
			for seg, anchors in multi_anchor.items():
				splits = seg.split([(GSegment(a1,a2)*.5).end_point for a1,a2 in pairwise(anchors)])
				seg_idx = layer.geometry.segments.index(seg)
				layer.geometry.segments[seg_idx:seg_idx+1] = splits
				rprint(f'Split {seg} into', splits, indent=2)
		else:
			anchor_segs = {anchor: anchor.intersecting(layer.geometry.segments) for anchor in anchors}
			rprint('Anchors fixed by segments:', pretty_repr(anchor_segs))

		rprint('Thread now:', pretty_repr(thread.points))
		rprint('Anchors now:', pretty_repr(anchors))

		#Set the printer thread path's z to this layer's z
		self.printer.move_thread_to(self.printer.thread_path.point.copy(z=layer.z))

		#Get segments of thread to work with, set to layer's z
		layerthread = [seg.copy(z=layer.z) for seg in thread.segments if seg.end_point.z == layer.z]
		rprint('Thread in layer:', pretty_repr(layerthread))

		#Done preprocessing thread; now we can start figuring out what to print and how
		rprint(f'[yellow]————[/] Start [yellow]————[/]\n{self.printer.summarize()}', div=True)

		#Find and print geometry that will not be intersected by any thread segments
		to_print = unprinted(layer.non_intersecting(layerthread) if thread else layer.geometry.segments)
		self.printer.avoid_and_print(steps, to_print)

		if not unprinted(layer.geometry.segments):
			rprint(f'Nothing left to print, so not processing {len(layerthread)} thread segments:', layerthread)
		else:
			rprint(f"[red]———[/] Now process {len(layerthread)} thread segments [red]———[/]")

			#At this point we've printed everything that does not intersect the
			# thread path. Now we need to work with the individual thread segments
			# one by one, where each segment is already anchored at its start
			# point:
			# 1. Move the ring so the thread crosses the next anchor point
			# 2. Print gcode segments that intersect this part of the thread, but
			#    that don't intersect:
			#    - the anchor->ring trajectory
			#    - the future thread path
			#    except where those intersections are only at the anchor point iself.

			for i,thread_seg in enumerate(layerthread):
				rprint(f'[yellow]————[/] Thread {i}: {thread_seg} [yellow]————[/]')

				next_anchor = thread_seg.end_point

				with steps.new_step(f'Move thread to overlap next anchor at {next_anchor} '
														f'from {self.printer.thread_path.point}') as s:
					self.printer.rotate_thread_to(next_anchor)

				#Find and print the segment that fixes the thread at the anchor point
				anchorsegs = [seg for seg in unprinted(layer.geometry.segments) if next_anchor in seg]
				if not anchorsegs: raise ValueError(f'No unprinted segments overlap anchor {next_anchor}')
				with steps.new_step(f'Print {len(anchorsegs)} segment{"s" if len(anchorsegs) > 1 else ""} to fix anchor') as s:
					s.add(anchorsegs, fixing=True)
					#Update the printer state with the new anchor (maintaining the same thread direction)
					self.printer.move_thread_to(next_anchor)

				#Get unprinted segments that overlap the current thread segment. We
				# want to print these to fix the thread in place.
				to_print = unprinted(layer.intersecting(thread_seg))
				rprint(f'{len(to_print)} unprinted segments intersecting this thread segment')

				#Find gcode segments that intersect future thread segments; we don't
				# want to print these yet, so remove them
				avoid = unprinted(layer.intersecting(layerthread[i+1:]))
				rprint(f'{len(avoid)} unprinted segments intersecting future thread segments')
				to_print -= avoid

				if to_print:
					self.printer.avoid_and_print(steps, to_print)
					to_print = set()


			# --- Print what's left
			remaining = {s for s in layer.geometry.segments if not s.printed}
			if not remaining == to_print:
				rprint('[red]Odd:\n  remaining - to_print:', remaining - to_print, indent=4)
				rprint('  to_print - remaining:', to_print - remaining, indent=4)
			if remaining:
				self.printer.avoid_and_print(steps, remaining, '(remaining)')

		rprint('[yellow]Done routing this layer[/];',
				len([s for s in layer.geometry.segments if not s.printed]),
				'gcode lines left')
		rprint(f'Printer state: {self.printer}')
