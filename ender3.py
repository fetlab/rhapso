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
		* Actual bed  (0,0,0) = (-117.5, -65, 0)
		* Ring (0,0)   = (-5.5, 74.2)
		* Ring x center is 122 mm from bed x = 0

Ring configuration:
	- ring is fixed to the x-axis gantry
	- ring y center (nearly) matches the center of the x-axis gantry bar, which
		is 1 in towards the rear from the center of the nozzle
	- ring x center is 129.5 mm from left z-axis gantry, or 122 mm from bed x = 0

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
from __future__      import annotations
from copy            import copy
from math            import radians
from typing          import Collection
from more_itertools  import flatten
from rich            import print
from fastcore.basics import first

from geometry       import GPoint, GSegment, GHalfLine
from bed            import Bed
from ring           import Ring
from gcode_printer  import GCodePrinter
from gcline         import GCLine, comments, comment
from geometry.angle import Angle, atan2, asin, acos
from geometry.utils import ang_diff, circle_intersection
from logger         import rprint
from util           import Saver, Number
from config         import load_config, get_ring_config, get_bed_config, RingConfig, BedConfig


class Ender3(GCodePrinter):
	def __init__(self, config, initial_thread_path:GHalfLine, z:Number=0, *args, **kwargs):
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
		print(f"Init: {ring_config}")

		self._ring_config = copy(ring_config)
		self._bed_config  = copy(bed_config)
		self.bed = Bed(anchor=bed_config['anchor'], size=bed_config['size'])
		self.ring = Ring(**ring_config)
		super().__init__(initial_thread_path, z)

		self.next_thread_path = initial_thread_path

		self.add_codes('M109', action=self.gfunc_printer_ready)

		#The current path of the thread: the current thread anchor and the
		# direction of the thread.
		self.thread_path: GHalfLine = None

		#BUG: this doesn't get run
		self.add_codes('G28', action=lambda gcline, **kwargs: [
			GCLine('G28 X Y Z ; Home only X, Y, and Z axes, but avoid trying to home A')])


	def __repr__(self):
		return f'Ender3(🧵={self.thread_path}, x={self.x}, y={self.y}, z={self.z})'


	@property
	def info(self): return f'🧵{self.thread_path},  ⃘{self.ring.angle:.3f}°'


	def ring_delta_for_thread(self, current_thread:GSegment, new_y:Number) -> Angle|None:
		"""Find out how to rotate the ring to keep the thread at the same angle during
		this move. "Move" the ring's center-y coordinate while keeping the bed
		static, then find where the thread will intersect it."""
		#Shift thread by moved bed location, then find where the current thread
		# intersects the moved ring
		isecs = self.ring.intersection(current_thread.moved(y=-new_y))

		#Return amount to move the ring, involving least movement
		if not isecs: return None
		delta = min((ang_diff(self.ring.angle, isec.angle(self.ring.center)) for isec in isecs), key=abs)
		return delta if abs(delta) >= ring_config['min_move'] else Angle(degrees=0)


	def gcode_set_thread_path(self, thread_path:GHalfLine, target:GPoint) -> list[GCLine]:
		"""Set the thread path to the new value and move the ring based on the bed
		being set to the thread anchor's `y`."""
		ring_move_by = self.ring_delta_for_thread(thread_path, target.y)
		if ring_move_by is None:
			raise ValueError(f'No ring/thread intersection for {thread_path}')
		new_ring_angle = self.ring.angle + ring_move_by
		ring_info = f'{self.thread_path.repr_diff(thread_path)},  ⃘{self.ring.angle + ring_move_by:.3f}°'
		rprint(ring_info)
		self.thread_path = thread_path
		self.ring.angle = new_ring_angle
		return [GCLine(code='G0', args={'A': ring_move_by.degrees, 'F': 5000}, comment=ring_info)]



	def gfunc_printer_ready(self, gcline: GCLine, **kwargs) -> list[GCLine]:
		"""At least with the current version of Cura, M109 is the last command
		before the printer starts actually doing things."""

		self.ring.angle = ring_config['home_angle']
		self.thread_path = self.next_thread_path
		ring_home_to_thread = self.ring_delta_for_thread(self.next_thread_path, self.bed.y)
		self.ring.angle += ring_home_to_thread

		#Fractional steps per unit don't seem to stick in the Marlin firmware, so
		# set manually at init
		steps_per_unit = ring_config['stepper_microsteps_per_rotation'] * \
			ring_config['ring_gear_teeth'] / ring_config['motor_gear_teeth'] / 360

		return [
			gcline,
			GCLine(f'G92 A{ring_config["home_angle"]} '
				f'; Assume the ring has been manually homed, set its position to {ring_config["home_angle"]}°'),
			GCLine(f'M92 A{steps_per_unit:.4f} ; Set fractional steps/unit for ring moves'),
			GCLine(f'G0 F5000 X{self.bed.width/2} ; Move head out of the way of the carrier'),
			GCLine(f'G0 F5000 A{ring_home_to_thread} ; Move ring to initial thread position ({self.info})'),
			GCLine(comment='--- Printer state ---'),
			GCLine(comment=repr(self.ring)),
			GCLine(comment=repr(self.bed)),
			GCLine(comment=f'Carrier: {self.ring.point}'),
			GCLine(comment=f'Print head: {self.head_loc}'),
		]


	def gcfunc_set_axis_value(self, gcline: GCLine, **kwargs) -> list[GCLine]:
		"""Process gcode lines with instruction G0, G1, or G92. Move the ring such
		that the angle of `self.thread_path` stays constant with any Y movement."""

		gclines:list[GCLine] = []

		#Keep a copy of the head location since super() will change it.
		prev_loc = self.head_loc.copy()

		#Run the passed gcode line `gcline` through the Printer class's
		# gfunc_set_axis_value() function. This might return multiple lines, so we
		# need to process each of the returned list values.
		super_gclines = super().gcfunc_set_axis_value(gcline) or [gcline]

		for gcline in super_gclines:
			#Avoid head collision - move ring before the head movees
			if gcline.x:
				for collision in ring_config['collision_avoid']:
					if(collision['head_between'][0] <= gcline.x        <= collision['head_between'][1] and
						 collision['ring_between'][0] <= self.ring.angle <= collision['ring_between'][1]):
						gclines.extend(self.gcode_ring_move(angle=collision['move_ring_to'],
										 comment=f'Avoid head collision at {gcline.x} by moving '
														 f'ring to {collision["move_ring_to"]}'))

			#If there's no Y movement we don't need to do anything; the bed doesn't
			# move so the thread angle won't change
			if not gcline.y or gcline.y == prev_loc.y:
				pass

			#If the bed is moving, we want to move the thread simultaneously to keep
			# it in the same relative position
			else:
				ring_move_by = self.ring_delta_for_thread(self.thread_path, gcline.y)

				if ring_move_by is None:
					gclines.append(gcline.copy(add_comment=f'--- No ring intersection for thread {self.thread_path}'))
				else:
					if ring_move_by != 0:
						new_ring_angle = self.ring.angle + ring_move_by
						gcline = gcline.copy(args={'A': ring_move_by.degrees},
															add_comment=f'(🧵{self.thread_path.angle:.3f}°,  ⃘{new_ring_angle:.3f}°)' if
															new_ring_angle != self.ring.angle else f'({self.info})')
						self.ring.angle = new_ring_angle


			gclines.append(gcline)

		return gclines


	def gcode_ring_move(self, dist:Angle=None, angle:Angle=None, comment='') -> list[GCLine]:
		"""Emit gcode to move the ring. Specify exactly one of dist or angle."""
		if (dist is not None and angle is not None) or (dist is None and angle is None):
			raise ValueError('Specify exactly one of dist or angle')

		ring_move_by = dist if dist is not None else ang_diff(self.ring.angle, angle)
		self.ring.angle += ring_move_by
		return [GCLine('G0', args={'A': ring_move_by.degrees, 'F': ring_config['feedrate']},
								 comment=comment)]



	def old_gcode_ring_move(self, dist, pause_after=False) -> list[GCLine]:
		if dist == 0: return []

		gcode = comments(f"""
			gcode_ring_move({dist:.3f}°)
			{self.ring}
			{self.ring.angle = }
			""")

		#Save the current z value, then raise the print head if needed
		with Saver(self.head_loc, 'z') as saver:
			gcode += self.execute_gcode([
				GCLine('G0', args={'Z':self.head_loc.z + config['general']['thread_crossing_head_raise']},
					 comment='Raise head to avoid thread snag'),
				#Here we're setting the angle to the "nominal" value - where the
				# carrier should be based on the bed not moving; e.g., if y=0.
				GCLine('G0', args={'A':dist.degrees}, comment=f'({self.ring.angle+dist:.3f}°)')
			])
			if pause_after:
				pause = config['general']['post_thread_overlap_pause']
				gcode.extend(self.execute_gcode(
					GCLine(code='G4', args={'S': pause}, comment=f'Pause for {pause} sec before ring move')))

		#Restore the z value if changed
		if saver.originals:
			gcode.extend(self.execute_gcode([
				GCLine('G0', args={'Z': saver.originals['z']},
				comment='Drop head back to original location')]))

		return gcode


	def gcfunc_auto_home(self, gcline: GCLine, **kwargs):
		#Also reset the ring to its default configuration when we get a home command
		super().gcfunc_auto_home(gcline)
		self.ring = Ring(**self._ring_config)
		self.bed = Bed(anchor=self._bed_config['anchor'], size=self._bed_config['size'])
