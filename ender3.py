"""This is the specific Ender 3 Pro we have and its parameters:

	- the bed moves for the y axis (XZ gantry)
	- at (0,0) the bed is all the way towards the rear of the printer and the
		print head is at the extreme left
	- printable bed size is 220x220
	- actual bed size is 235x235
	- in X, the bed is centered on the frame coordinate system

	We'll use the X/Y parts of the Fusion 360 model's coordinate system as the
	X/Y for the base printer coordinate system, so (0, 0) is centered above one
	of the bolts on the bottom of the printer. Note that in Fusion the model is
	oriented with Y up and Z towards the front of the printer, but I'm switching
	coordinates here so that Z is up and Y is towards the back.

	Looking straight down from the top of the printer, x=0 is at the center of
	the top cross-piece of the printer, and y=0 is at the top/back edge of that
	piece. We'll set z=0 as the bed surface (in the Fusion model this is at
	z=100.964 mm above the table surface, but in real life is at 100 mm).

	By this coordinate system then (verified by measuring):
	* Bed (0,0,0) = (-117.5, -65, 0)
	* Ring
		* (0,0) = (5, -37)

Ring configuration:
	- ring is fixed to the x-axis gantry
	- ring y center (nearly) matches the center of the x-axis gantry bar, which
		is 1 in towards the rear from the center of the nozzle
	- ring x center is 130 mm from left z-axis gantry, or 122.5 mm from bed x = 0

Bed configuration:
	The actual printable bed area is very restricted by the print head's ability
	to move on the x-axis within the ring. Thus, its effective size should be
	79 x 220. On the actual printer, the effective width as measured by moving the
	heat and seeing where the nozzle hits the bed is 77.5 mm, with the left side
	of this area at 85 mm from the left edge of the bed.

	Thus, the new origin for the bed, in the printer frame coordinate system, is
	then (-32.5, -65, 0). This is when the bed is at y=0, with the front edge of
	the bed plate underneath the nozzle. When the bed is at its other extreme,
	with the back edge of the plate under the nozzle, then the actual front-left
	corner of the bed is at (-32.5, -285).

Print head configuration:
	The print head moves in X/Z; for our purposes, we only care about X, where
	we use the bed coordinates.

Transforms to provide:
	The point is that when we have a move, we want to know the actual path of the
	thread between the carrier and the print head. So there is a transform
	between the head (bed) coordinate and the ring coordinate, complicated by the
	fact that the bed moves in the y-axis.
"""

from printer  import Printer
from bed      import Bed
from ring     import Ring
from geometry import GPoint, GSegment
from typing   import TypedDict
from util     import Number, Saver
from gcline   import GCLine, comment
from geometry.utils import ang_diff
from geometry_helpers import traj_isec

# --- Ring gearing ---
stepper_microsteps_per_rotation = 200 * 16   #For the stepper motor; 16 microsteps, 200 steps per rotation

motor_gear_teeth   = 30
ring_gear_teeth    = 125

#Set to -1 if positive E commands make the ring go clockwise
rot_mul = 1  # 1 since positive steps make it go CCW

#How many motor steps per CCW degree?
esteps_per_degree = stepper_microsteps_per_rotation * ring_gear_teeth / motor_gear_teeth / 360

#Default defined in Marlin for second extruder by Diana
default_esteps_per_unit = 93

#Slow down when we print over the thread
thread_overlap_feedrate = 900

#Pause before we move the thread carrier if we just printed over thread
post_thread_overlap_pause = 2

# --- Actual measured parameters of the printer, in the coordinate system of
# the printer frame (see comments above) ---
BedConfig  = TypedDict(
	'BedConfig',  {
		'zero':   GPoint,
		'size':   tuple[Number, Number],
		'anchor': GPoint,
	})
RingConfig = TypedDict(
	'RingConfig', {
		'center': GPoint,
		'radius': Number,
		'rot_mul': Number,
		'angle': Number,
	})

ring_config: RingConfig = {
	'center': GPoint(5, -37, 0),
	'radius': 93,   #effective thread radius from thread carrier to ring center
	'rot_mul': esteps_per_degree / default_esteps_per_unit,
	'angle': 0,
}
bed_config: BedConfig = {
	'zero': GPoint(-32.5, -65, 0),
	'size': (77.5, 220),
	'anchor': GPoint(ring_config['radius'] + ring_config['center'].x, 0, 0),
}

#Move the zero points so the bed zero is actually 0,0
ring_config['center'] -= bed_config['zero']
bed_config ['zero']   -= bed_config['zero']


class Ender3(Printer):
	def __init__(self):
		self.bed = Bed(anchor=(ring_config['radius']+ring_config['center'].x, 0, 0), size=bed_config['size'])
		self.ring = Ring(**ring_config)
		super().__init__(self.bed, self.ring)

		#State to save/restore for switching to ring movement and back
		self.save_vars = 'extruder_no', 'extrusion_mode', 'cold_extrusion'
		self.extruder_no    = GCLine(code='T0', comment='Switch to main extruder', fake=True)
		self.extrusion_mode = GCLine(code='M82',comment='Set absolute extrusion mode', fake=True)
		self.cold_extrusion = GCLine(code='M302', args={'P':0}, comment='Prevent cold extrusion', fake=True)

		#Save attributes on these Gcode lines
		self.add_codes('M82', 'M83',      action='extrusion_mode')
		self.add_codes('T0', 'T1',        action='extruder_no')
		self.add_codes('M302',            action='cold_extrusion')


	def gcode_file_preamble(self, preamble: list[GCLine]) -> list[GCLine]:
		"""Add a z-move and a pause in order to attach the thread after homing."""
		home_idx = next((i for i,l in reversed(list(enumerate(preamble))) if l.code == 'G28'))
		bed_temp = next((l for l in preamble if l.code == 'M190')).args['S']
		return [GCLine(code='T0', comment='Ensure main extruder', fake=True),
						GCLine(code='M82', comment='Ensure absolute extrusion', fake=True),
						GCLine(code='M302', args={'P':0}, comment='Disallow cold extrusion', fake=True),
						] + preamble[:home_idx+1] + [
				GCLine(code='M140', args={'S': bed_temp}, comment='Start heating bed', fake=True),
				#GCLine(code='G0', args=dict(Z=50, F=5000.0), comment='Raise Z to allow thread attachment'),
				#GCLine('M117 Bed heating, attach thread', comment='Display message'),
			] + preamble[home_idx+1:]



	def gcode_ring_move(self, dist, pause_after=False) -> list[GCLine]:
		#Save and restore state while moving ring
		with Saver(self, self.save_vars) as saver:
			#Find "extrusion" amount
			extrude = self.ring.rot_mul * dist
			dir_str = 'CCW' if dist > 0 else 'CW'

			message = f'Ring move by {dist:.2f}° {dir_str}'
			gcode = self.execute_gcode([
				GCLine(code='M300', args={'P':50, 'S':10000}, comment='Beep', fake=True),
				GCLine(f'M117 {message}', fake=True),
				GCLine('G4 S1'),
				GCLine(code='T1', comment='Switch to ring extruder', fake=True),
				GCLine(code='M83', comment='Set relative extrusion mode', fake=True),
				GCLine(code='M302', args={'P':1}, comment='Allow cold extrusion', fake=True),
				GCLine(code='G1', args={'E':round(extrude,3), 'F':8000},
						comment=message, fake=True, meta={'ring_move_deg': dist}),
				GCLine(code='M300', args={'P':50, 'S':1000}, comment='Beep', fake=True),
			])

		if pause_after:
			gcode.extend(self.execute_gcode(
				GCLine(code='G4', args={'S': post_thread_overlap_pause},
					comment=f'Pause for {post_thread_overlap_pause} sec before ring move')))
		gcode.extend(self.execute_gcode(saver.originals.values()))

		#Reset extrusion value back to what it was
		gcode.append(GCLine(code='G92', args={'E': self.e}))

		return gcode

	# Segment:      <{ 28.66,  50.91,   0.20}←→{ 26.03,  50.91,   0.20} (2.64 mm)>
	# Thread (0°):  <{ 33.27,  21.60,   0.00}←→{130.50,  28.00,   0.00} (97.44 mm)>

	#Called for G0, G1, G92
	def gcfunc_set_axis_value(self, gcline: GCLine, **kwargs):
		#Keep track of current ring angle
		if self.extruder_no.code == 'T1':
			if gcline.code in ('G0', 'G1'):
				if dist := gcline.meta.get('ring_move_deg', None):
					self.ring_angle += dist
			return

		#Keep a copy of the head location since super() might change it
		cur_loc = self.head_loc.copy()

		#Do super() stuff
		gclines = super().gcfunc_set_axis_value(gcline)

		#If not printing, don't need to do anything
		if not gclines or not gcline.is_xyextrude(): return

		#Fixing segment, we *want* interference! See if the anchor's there and if
		# so we're done.
		printed_seg = GSegment(cur_loc, self.head_loc)
		if self.anchor in printed_seg.copy(z=0):
			if kwargs.get('fixing', False):
				gcline.args['F'] = thread_overlap_feedrate
			return [gcline]

		#Otherwise we need to see if the head will intersect the thread during a
		# move.
		thread_seg  = GSegment(self.anchor, self.ring.angle2point(self.ring_angle))
		if traj_isec(printed_seg, thread_seg):
			#Move anchor by negative of endpoint of printed segment's y value, then
			# avoid the segment formed by the two x values of the endpoints
			ang1 = self.thread_intersect(cur_loc.copy(y=0), self.anchor.moved(y=-cur_loc.y),       False, False)
			ang2 = self.thread_intersect(cur_loc.copy(y=0), self.anchor.moved(y=-self.head_loc.y), False, False)
			dist1 = ang_diff(self.ring_angle, ang1)
			dist2 = ang_diff(self.ring_angle, ang2)
			move_by = min(dist1, dist2, key=abs)
			return ([
							comment(f'Move thread to avoid head during bed move for [{gcline.lineno}]'),
							comment(f'  Segment: {printed_seg}'),
							comment(f'  Thread ({self.ring_angle:.2f}°):  {thread_seg}'),
						] + self.gcode_ring_move(move_by) + gclines)
