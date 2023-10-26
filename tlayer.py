import logging
import plotly.graph_objects as go
from Geometry3D import Plane, distance, Vector
from geometry import GPoint, GSegment, GPolyLine
from geometry_helpers import Geometry, Planes, seg_combine, gcode2segments
from typing import List, Set, Dict
from cura4layer import Cura4Layer
from fastcore.basics import listify
from util import deep_update

log = logging.getLogger('threader')

class TLayer(Cura4Layer):
	style: dict[str, dict] = {
		'move':    {'line': {'color':'yellow', 'width':1}, 'opacity':.5},
		'extrude': {'line': {'color':'green',  'width':1}, 'opacity':.5},
		'3d':      {'line': {'width':2}, 'opacity':1},
	}
	"""A gcode layer that has thread in it."""
	def __init__(self, *args, layer_height=0.4, **kwargs):
		super().__init__(*args, **kwargs)
		self.geometry = Geometry(segments=[], planes=None, outline=[])
		self.layer_height = layer_height
		self.model_isecs  = {}
		self.in_out       = []
		if not isinstance(self.layernum, str):
			self.add_boundary_planes()


	def plot(self, fig=None, plot3d=False, only_outline=True, show=False,
					style:dict={}):
		"""Plot the geometry making up this layer. Set only_outline to True to
		print only the outline of the gcode in the layer .
		"""
		self.add_geometry()

		if style and 'line' in style or 'marker' in style:
			_style = self.style.copy()
			_style['move'] = style
			_style['extrude'] = style
			style = _style
		style = deep_update(self.style, style or {})

		if fig is None:
			fig = go.Figure()

		for gcline, part in self.parts.items():
			if only_outline and 'wall-outer' not in gcline.line.lower():
				continue

			Esegs = {'x': [], 'y': [], 'z': []}
			Msegs = {'x': [], 'y': [], 'z': []}
			for line in part:
				try:
					seg = line.segment
				except AttributeError:
					#print(line)
					continue

				segs = Esegs if line.is_xyextrude else Msegs
				segs['x'].extend([seg.start_point.x, seg.end_point.x, None])
				segs['y'].extend([seg.start_point.y, seg.end_point.y, None])
				segs['z'].extend([seg.start_point.z, seg.end_point.z, None])

			if plot3d:
				scatter = go.Scatter3d
				lineprops = style['3d']
			else:
				scatter = go.Scatter
				lineprops = {}
				if 'z' in Esegs: Esegs.pop('z')
				if 'z' in Msegs: Msegs.pop('z')

			mv_style = deep_update(style['move'],    lineprops)
			ex_style = deep_update(style['extrude'], lineprops)

			if Esegs['x']:
				fig.add_trace(scatter(**Esegs, mode='lines',
					name='Ex'+(repr(gcline).lower()), **ex_style))

			if Msegs['x']:
				fig.add_trace(scatter(**Msegs, mode='lines',
					name='Mx'+(repr(gcline).lower()),
					line=lineprops, **mv_style))

		if show:
			fig.update_layout(template='plotly_dark',# autosize=False,
					yaxis={'scaleanchor':'x', 'scaleratio':1, 'constrain':'domain'},
					margin=dict(l=0, r=20, b=0, t=0, pad=0),
					showlegend=False,)
			fig.show()

		return fig


	def add_boundary_planes(self):
		"""Add top and bottom planes to this layer."""
		if self.geometry.planes: return

		z = self.z
		self.geometry.planes = Planes(
				bottom=Plane(GPoint(0,0,z - self.layer_height), Vector(0,0,1)),
				top   =Plane(GPoint(0,0,z),                     Vector(0,0,1)),
		)


	def add_geometry(self):
		"""Add geometry to this Layer based on the list of gcode lines:
			- segments: a list of GSegments for each pair of extrusion lines
			- planes:   planes representing the top and bottom boundaries of the
								  layer, based on the layer height
			- outline:  a list of GSegments representing the outline of the layer,
									denoted by sections in Cura-generated gcode starting with
									";TYPE:WALL-OUTER"
		"""
		self.add_boundary_planes()

		if self.geometry.segments: return

		#Make segments from GCLines
		self.preamble, self.geometry.segments, self.postamble = gcode2segments(self.lines, self.z)

		#Find the outline by using Cura comments for "wall-outer"
		for part, lines in self.parts.items():
			if 'type:wall-outer' in (lines[0].comment or '').lower():
				self.geometry.outline.extend(
						[line.segment for line in lines if line.is_xyextrude])



	def flatten_thread(self, thread: List[GSegment]) -> List[GSegment]:
		"""Process the input thread:
			* Clip it to the top/bottom of the layer (the layer height)
			* Flatten in-layer segments to have the same z-height as the layer
			* Combine resulting segments that are on the same line into a single segment"""
		self.add_geometry()

		top = self.geometry.planes.top
		bot = self.geometry.planes.bottom
		segs = []

		for i,tseg in enumerate(thread):
			#Is the thread segment entirely below or above (including sitting on top
			# of) the layer? If so, skip it.
			if((tseg.start_point.z <  bot.p.z and tseg.end_point.z <  bot.p.z) or
				 (tseg.start_point.z >= top.p.z and tseg.end_point.z >= top.p.z)):
				log.debug(f'{i}. {tseg} endpoints not in layer',
						extra=dict(style={'line-height':'normal'}))
				continue

			#Is the segment entirely inside the layer? If so, don't need to clip.
			if tseg.start_point.z >= bot.p.z and tseg.end_point.z >= bot.p.z:
				newseg = tseg.copy()
			else:
				#Clip segments to top/bottom of layer (note "walrus" operator := )
				if s := tseg.intersection(bot): self.in_out.append(s)
				if e := tseg.intersection(top): self.in_out.append(e)
				newseg = GSegment(s or tseg.start_point, e or tseg.end_point)

			#Flatten segment to the layer's z-height, but not if the segment is
			# vertical
			if newseg.start_point.as2d() != newseg.end_point.as2d():
				newseg.set_z(self.z)
			segs.append(newseg)

		#Combine collinear segments
		segs = seg_combine(segs)

		#Cache intersections
		# self.intersect_model(segs)

		return segs


	def geometry_snap(self, thread: GPolyLine) -> list[GPoint]:
		"""Snap the thread vertices (in-place!) to the geometry in this layer.
		Return the (possibly new) in-layer vertices."""
		#If none of the thread vertices start, or end in this layer, then skip
		# creating geometry. Don't check the first segment since it will be
		# starting from the anchor point.
		if not any(p.z == self.z for p in thread.points[1:]): return []

		self.add_geometry()

		def _closest_seg_point(p: GPoint) -> tuple[GPoint, GSegment]:
			closest_seg  = None
			closest_isec = None
			mindist = float('inf')
			for seg in self.geometry.segments:
				if p in seg: return p, seg
				isec = seg.closest(p)
				if (dist := isec.distance(p)) < mindist:
					mindist = dist
					closest_isec = isec
					closest_seg  = seg
			assert closest_isec is not None
			return closest_isec, closest_seg

		out_anchors = []

		#Skip the first point since it will be the bed anchor
		for anchor in thread.points[1:]:
			#Don't snap anchors not on this layer
			if anchor.z != self.z: continue

			p, seg = _closest_seg_point(anchor)

			if (move_dist := anchor.distance(p)) > 1:
				log.debug(f"WARNING: moving end point for {anchor} {move_dist:02f} mm")

			if p != anchor:
				thread.move(anchor, to=p)
			log.debug(f'Snap {anchor} to {p}')

			out_anchors.append(p)

		return out_anchors


	def non_intersecting(self, thread: List[GSegment]) -> Set[GSegment]:
		"""Return a list of GSegments which the given thread segments do not
		intersect."""
		thread = listify(thread)
		self.intersect_model(thread)

		#First find all *intersecting* GSegments
		intersecting = self.intersecting(thread)

		#And all non-intersecting GSegments
		non_intersecting = set.union(*[self.model_isecs[tseg]['nsec_segs'] for tseg in thread])

		#And return the difference
		return non_intersecting - intersecting


	def intersecting(self, thread: GSegment|List[GSegment]) -> Set[GSegment]:
		"""Return a set of GSegments which the given thread segment(s) intersect."""
		thread = listify(thread)
		if not thread: return set()
		self.intersect_model(thread)
		return set.union(*[self.model_isecs[t]['isec_segs'] for t in thread])


	def intersect_model(self, segs, skip="SKIRT"):
		"""Given a list of thread segments, calculate all of the intersections with the model's
		printed lines of gcode. Caches in self.model_isecs:
			nsec_segs, isec_segs, isec_points
		where
			nsec_segs is non-intersecting GCLines
			isec_segs is intersecting GCLines
			isec_points is a list of GPoints for the intersections

		Pass `skip` as a type (see Cura4Layer) to always treat lines of that type
		as non-intersecting.
		"""
		self.add_geometry()

		for tseg in segs:
			if tseg in self.model_isecs:
				continue

			isecs = {
				'nsec_segs': set(),                       # Non-intersecting gcode segments
				'isec_segs': set(), 'isec_points': set(), # Intersecting gcode segments and locations
			}

			for gcseg in self.geometry.segments:
				if not gcseg.is_extrude: continue

				if skip in self.parts and gcseg.gc_lines.data[-1] in self.parts[skip]:
					inter = None
				else:
					inter = gcseg.intersection(tseg)

				if inter is None:
					isecs['nsec_segs'].add(gcseg)
				else:
					isecs['isec_segs'].add(gcseg)
					if isinstance(inter, GPoint):
						inter = GPoint(inter)
						isecs['isec_points'].add(inter)
					elif isinstance(inter, GSegment):
						isecs['isec_points'].update(map(GPoint, inter[:]))

			self.model_isecs[tseg] = isecs
