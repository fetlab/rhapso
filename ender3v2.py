"""
Configuration for updated Ender 3 with metal ring:
	* Actual bed  (0,0,0) = (-117.5, -65, 0)
	* Ring (0,0)   = (-5.5, 74.2)
	* Ring x center is 122 mm from bed x = 0

Bed configuration:
	Effective size is 110 x 220. On the actual printer, the effective width as
	measured by moving the head and seeing where the nozzle hits the bed is 110
	mm, with the left side of this area at 65 mm from the left edge of the bed.

	Thus, the new origin for the bed, in the printer frame coordinate system, is
	then (-52.5, -65, 0) (x=235/2 - 65 = 52.5). This is when the bed is at y=0,
	with the front edge of the bed plate underneath the nozzle. When the bed is
	at its other extreme, with the back edge of the plate under the nozzle, then
	the actual front-left corner of the bed is at (-52.5, -285).

The conceptual model for the coordinate system is that the bed is fixed, with
the effective (0, 0) coordinate as actual (0, 0). Then the print head moves as
expected in two dimensions, and the ring is locked in position relative to the
head, so it moves in 2D as well. This inversion of the actual situation should
be more intuitive and require less converting of coordinate systems.

Conveniently for calculations, this "moving ring" model is (I think!) only
necessary during GCode generation. In working with calculations for planning
thread trajectories and print order, we can ignore that part.
"""
from math     import sin, pi
from geometry import GPoint, GSegment
from bed      import Bed
from ring     import Ring
from printer  import Printer
from gcline   import GCLine, comment
from geometry.utils import ang_diff
from geometry_helpers import traj_isec
config      = load_config('ender3v2.yaml')
ring_config = get_ring_config(config)
bed_config  = get_bed_config(config)
print(f"Loaded ring: {ring_config}")
print(f"Loaded bed: {bed_config}")

#Move the zero points so the bed zero is actually 0,0
ring_config['center'] -= bed_config['zero']
bed_config['anchor']  -= bed_config['zero']
bed_config['zero']    -= bed_config['zero']
print(f"Ring relative to bed zero: {ring_config}")
print(f"Bed now: {bed_config}")


class Ender3(Ender3v1):
	def __init__(self):
		print(f"Init: {ring_config}")
		self._ring_config = copy(ring_config)
		self._bed_config  = copy(bed_config)
		self.bed = Bed(anchor=bed_config['anchor'], size=bed_config['size'])
		self.ring = Ring(**ring_config)
		Printer.__init__(self, self.bed, self.ring)


	#Called for G0, G1, G92
	def gcfunc_set_axis_value(self, gcline: GCLine, **kwargs):
		#Keep a copy of the head location since super() might change it
		cur_loc = self.head_loc.copy()

		#Update printer state
		gclines = Printer.gcfunc_set_axis_value(self, gcline)
		if 'A' in gcline.args: self.a = gcline.args['A']

		#If there's no Y movement we don't need to do anything
		if not gcline.y or gcline.y == cur_loc.y: return

		#Find out how to move the ring to keep the thread at the same angle during
		# this move.
		new_thr = GSegment(self.anchor, self.ring.point, z=0).moved(y=gcline.y-cur_loc.y)
		isecs = self.ring.intersection(new_thr)
		if not isecs: return

		#Get the intersection closest to the current carrier location
		isec = isecs[0] if len(isecs) == 1 else sorted(isecs, key=self.ring.point.distance)[0]

		new_ring_angle = self.ring.point2angle(isec)

		if new_ring_angle != self.ring.angle:
			gcline.args['A'] = new_ring_angle
		return [gcline]


	def gcode_ring_move(self, dist, pause_after=False) -> list[GCLine]:
		return [GCLine('G0', A=self.ring.angle+dist)]
