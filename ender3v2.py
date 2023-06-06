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
"""
from copy     import copy
from math     import sin, pi
from geometry import GPoint, GSegment
from bed      import Bed
from ring     import Ring
from printer  import Printer
from gcline   import GCLine, comment
from geometry.utils import ang_diff
from geometry_helpers import traj_isec
from ender3   import RingConfig, BedConfig, stepper_microsteps_per_rotation, \
										 thread_overlap_feedrate, post_thread_overlap_pause, \
										 default_esteps_per_unit, Ender3 as Ender3v1
from geometry.angle import Angle, atan2, asin, acos

motor_gear_teeth = 19
ring_gear_teeth  = 112

esteps_per_degree = stepper_microsteps_per_rotation * ring_gear_teeth / motor_gear_teeth / 360

# --- Actual measured parameters of the printer, in the coordinate system of
# the printer frame (see comments above) ---
ring_config: RingConfig = {
	'center':  GPoint(-5.5, 74.2, 0),
	'radius':  93,   #effective thread radius from thread carrier to ring center
	'rot_mul': esteps_per_degree / default_esteps_per_unit,
	'angle':   Angle(90),
}

bed_config: BedConfig = {
	'zero': GPoint(-52.5, -65, 0),
	'size': (110, 220),
	'anchor': GPoint(-72.5, 0, 0),   #In frame coordinates (45mm from actual bed left edge)
}

#Move the zero points so the bed zero is actually 0,0
ring_config['center'] -= bed_config['zero']
bed_config['anchor']  -= bed_config['zero']
bed_config['zero']    -= bed_config['zero']


class Ender3(Ender3v1):
	def __init__(self):
		self.bed = Bed(anchor=bed_config['anchor'], size=bed_config['size'])
		self.ring = Ring(**ring_config)
		Printer.__init__(self, self.bed, self.ring)


	#Called for G0, G1, G92
	def gcfunc_set_axis_value(self, gcline: GCLine, **kwargs):
		#Keep a copy of the head location since super() will change it
		prev_loc = self.head_loc.copy()

		#Update printer state
		gclines = Printer.gcfunc_set_axis_value(self, gcline)
		if 'A' in gcline.args: self.ring_angle = Angle(degrees=gcline.args['A'])

		#If there's no Y movement we don't need to do anything; the bed doesn't
		# move so the thread angle won't change
		if not gcline.y or gcline.y == prev_loc.y: return

		#Find out how to move the ring to keep the thread at the same angle during
		# this move.
		new_thr = GSegment(self.anchor, self.ring.point, z=0).moved(y=gcline.y-prev_loc.y)
		isecs = self.ring.intersection(new_thr)
		if not isecs: return

		#Get the intersection closest to the current carrier location
		isec = isecs[0] if len(isecs) == 1 else sorted(isecs, key=self.ring.point.distance)[0]

		new_ring_angle = self.ring.point2angle(isec)

		if new_ring_angle != self.ring.angle:
			gcline = gcline.copy(args={'A': new_ring_angle.degrees})
		return [gcline]


	def gcode_ring_move(self, dist, pause_after=False) -> list[GCLine]:
		gcode = self.execute_gcode([
			GCLine('G0', args={'A':(self.ring.angle+dist).degrees})
		])
		if pause_after:
			gcode.extend(self.execute_gcode(
				GCLine(code='G4', args={'S': post_thread_overlap_pause},
					comment=f'Pause for {post_thread_overlap_pause} sec before ring move')))
		return gcode
