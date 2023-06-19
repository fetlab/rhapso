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
from geometry import GPoint, GSegment
from bed      import Bed
from ring     import Ring
from printer  import Printer
from gcline   import GCLine
from geometry.utils import ang_diff
from ender3   import RingConfig, BedConfig, stepper_microsteps_per_rotation, \
										 thread_overlap_feedrate, post_thread_overlap_pause, \
										 default_esteps_per_unit, Ender3 as Ender3v1
from geometry.angle import Angle

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


	def gcfunc_set_axis_value(self, gcline: GCLine, **kwargs):
		"""Process gcode lines with instruction G0, G1, or G92. Move the ring such that the thread stays in place with any Y movement. \n
		We do not do this movement on fixing steps or if the gcode line already includes ring movement."""
		#Fixing segment, we *want* interference! We should have already moved the ring into place, so no processing is required
		if kwargs.get('fixing') == True:
			gcline.comment =  'Fixing - true'
			
			return [gcline]

		if kwargs.get('fixing') == False:
			gcline.comment =  'Fixing - false'

		old_head_y_loc = self.head_loc.y
		#If there's no Y movement we don't need to do anything; the bed doesn't
		# move so the thread angle won't change
		if not gcline.y or gcline.y == old_head_y_loc: return

		self.head_loc: GPoint = GPoint(gcline)

		#If we already have ring movement, we're done
		if 'A' in gcline.args:
			self._ring_angle = Angle(degrees=gcline.args['A'])
			return

		#Find out how to move the ring to keep the thread at the same angle during
		# this move.
		ring_point = self.ring.angle2point(self._ring_angle)
		new_thr = GSegment(self.anchor, ring_point, z=0).moved(y=gcline.y-old_head_y_loc)
		isecs = self.ring.intersection(new_thr)
		if not isecs: return

		#Get the intersection closest to the current carrier location
		isec = isecs[0] if len(isecs) == 1 else sorted(isecs, key=ring_point.distance)[0]

		newring_angle: Angle = self._ring_angle + ang_diff(self._ring_angle, self.ring.point2angle(isec))

		if newring_angle != self._ring_angle:
			gcline = gcline.copy(args={'A': newring_angle.degrees})
			self._ring_angle = newring_angle
		return [gcline]


	def gcode_ring_move(self, move_to: Angle, pause_after=False) -> list[GCLine]:
		"""Add a Gcode instruction to move the ring to a specified angle taking the shortest route possible."""
		new_ring_angle = self._ring_angle + ang_diff(self._ring_angle, move_to)
		gcode = self.execute_gcode([
			GCLine('G0', args={'A':new_ring_angle.degrees})
		])
		self._ring_angle = new_ring_angle
		if pause_after:
			gcode.extend(self.execute_gcode(
				GCLine(code='G4', args={'S': post_thread_overlap_pause},
					comment=f'Pause for {post_thread_overlap_pause} sec before ring move')))
		return gcode