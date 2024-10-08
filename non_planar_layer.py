from python_gcode.gcline import GCLines
from python_gcode.gclayer import Layer
from gcode_geom import GSegment
from geometry_helpers import Geometry

class NonPlanarLayer(Layer):
	def __init__(self, *args, add_geom=True, **kwargs):
		super().__init__(*args, **kwargs)
		self.geometry = Geometry(segments=[], planes=None, outline=[])
		if add_geom:
			self.add_geometry()


	def add_geometry(self):
		lines = self.lines.copy()
		extra = GCLines()
		last = None
		segments = []

		preamble = GCLines()
		while lines and not lines.first.is_xyextrude():
			preamble.append(lines.popidx(0))

		#Put back lines from the end until we get an xymove
		putback = []
		while preamble and not preamble.last.is_xymove():
			putback.append(preamble.popidx(-1))
		if preamble and preamble.last.is_xymove(): putback.append(preamble.popidx(-1))
		if putback: lines = list(reversed(putback)) + lines

		#Put the first xymove as the "last" item
		last = lines.popidx(0)

		for line in lines:
			if line.is_xyextrude():
				line.segment = GSegment(last, line, gc_lines=extra, is_extrude=line.is_xyextrude())
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

		self.geometry.segments = segments
