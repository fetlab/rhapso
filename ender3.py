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
# from Geometry3D      import Polygon

from geometry       import GPoint, GSegment, GHalfLine
from geometry.angle import Angle, atan2, asin, acos
from geometry.utils import ang_diff, circle_intersection, sign
from geometry_helpers import traj_isec
from bed            import Bed
from ring           import Ring
from gcode_printer  import GCodePrinter
from gcline         import GCLine, comments, comment
from logger         import rprint
from util           import Saver, Number
from config         import load_config, get_ring_config, get_bed_config, RingConfig, BedConfig


class Ender3(GCodePrinter):
	def __init__(self, config, initial_thread_path:GHalfLine, *args, **kwargs):
		self.config = config
		self.ring_config = get_ring_config(config)
		self.bed_config  = get_bed_config(config)
		print(f"Loaded ring: {self.ring_config}")
		print(f"Loaded bed: {self.bed_config}")

		#Move the zero points so the bed zero is actually 0,0
		self.ring_config['center'] -= self.bed_config['zero']
		self.bed_config['anchor']  -= self.bed_config['zero']
		self.bed_config['zero']    -= self.bed_config['zero']
		print(f"Ring relative to bed zero: {self.ring_config}")
		print(f"Bed now: {self.bed_config}")
		print(f"Init: {self.ring_config}")

		self._ring_config = copy(self.ring_config)
		self._bed_config  = copy(self.bed_config)
		self.bed = Bed(anchor=self.bed_config['anchor'], size=self.bed_config['size'])
		self.ring = Ring(**self.ring_config)
		super().__init__()

		self.next_thread_path = initial_thread_path

		self.add_codes('M109', action=self.gfunc_printer_ready)

		#The current path of the thread: the current thread anchor and the
		# direction of the thread.
		self.thread_path: GHalfLine = None

		self.add_codes('G28', action=lambda gcline, **kwargs: [
			GCLine('G28 X Y Z ; Home only X, Y, and Z axes, but avoid trying to home A')])

		#Comment out any G90s we find
		self.add_codes('G90', action=self.gfunc_set_absolute_positioning)



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
		return delta if abs(delta) >= self.ring_config['min_move'] else Angle(degrees=0)


	def set_thread_path(self, thread_path:GHalfLine, target:GPoint) -> list[GCLine]:
		"""Set the thread path to the new value and move the ring based on the bed
		being set to the thread anchor's `y`."""
		if (ring_move_by := self.ring_delta_for_thread(thread_path, target.y)) is None:
			raise ValueError(f'No ring/thread intersection for {thread_path}')
		new_ring_angle = self.ring.angle + ring_move_by
		self.thread_path = thread_path
		return self.ring_move(dist=ring_move_by, raise_head=True,
			comment=f'{self.thread_path.repr_diff(thread_path)},  ⃘{self.ring.angle + ring_move_by:.3f}°')


	def gfunc_set_absolute_positioning(self, gcline: GCLine, **kwargs) -> list[GCLine]:
		rprint(f'[yellow]Warning[/]: dropping G90 on line {gcline.lineno} to avoid ring absolute positioning')
		return [GCLine(comment=gcline.line + '; Drop G90 to avoid ring being absolutely positioned')]


	def gfunc_printer_ready(self, gcline: GCLine, **kwargs) -> list[GCLine]:
		"""At least with the current version of Cura, M109 is the last command
		before the printer starts actually doing things."""

		self.ring.angle = self.ring_config['home_angle']
		self.thread_path = self.next_thread_path
		ring_home_to_thread = self.ring_delta_for_thread(self.next_thread_path, self.bed.y)
		self.ring.angle += ring_home_to_thread

		#Fractional steps per unit don't seem to stick in the Marlin firmware, so
		# set manually at init
		steps_per_unit = self.ring_config['stepper_microsteps_per_rotation'] * \
			self.ring_config['ring_gear_teeth'] / self.ring_config['motor_gear_teeth'] / 360

		return [
			gcline,
			GCLine(f'G92 A{self.ring_config["home_angle"]} '
				f'; Assume the ring has been manually homed, set its position to {self.ring_config["home_angle"]}°'),
			GCLine(f'M92 A{steps_per_unit:.4f} ; Set fractional steps/unit for ring moves'),
			GCLine(f'G0 F5000 X{self.bed.width/2} ; Move head out of the way of the carrier'),
			GCLine(f'G0 F5000 A{ring_home_to_thread} ; Move ring to initial thread position ({self.info})'),
			GCLine(comment='--- Printer state ---'),
			GCLine(comment=repr(self.ring)),
			GCLine(comment=repr(self.bed)),
			GCLine(comment=f'Carrier: {self.ring.point}'),
			GCLine(comment=f'Print head: {self.head_loc}'),
		]


	def gcfunc_move_axis(self, gcline: GCLine, **kwargs) -> list[GCLine]:
		"""Process gcode lines with instruction G0, G1. Move the ring such
		that the angle of `self.thread_path` stays constant with any Y movement."""

		gclines:list[GCLine] = []

		#Keep a copy of the head location since super() will change it.
		prev_loc = self.head_loc.copy()
		self.prev_loc = prev_loc
		self.prev_set_by = self.head_set_by

		#BUG: Ender3 specific code and hardcoded, should maybe be in config
		if gcline.is_xymove() and gcline.x == 0 and gcline.y == 220:
			gcline = gcline.copy(args={'X': 55}, add_comment='Avoid knocking clip off the back of the bed')

		#Run the passed gcode line `gcline` through the parent class's
		# gfunc_set_axis_value() function. This might return multiple lines, so we
		# need to process each of the returned list values.
		super_gclines = super().gcfunc_move_axis(gcline) or [gcline]

		for gcline in super_gclines:
			#Avoid head collision - move ring before the head moves
			if gcline.x:
				for collision in self.ring_config['collision_avoid']:
					if(collision['head_between'][0] <= gcline.x        <= collision['head_between'][1] and
						 collision['ring_between'][0] <= self.ring.angle <= collision['ring_between'][1]):
						gclines.extend(self.ring_move(angle=collision['move_ring_to'],
										 comment=f'Avoid head collision at {gcline.x} by moving '
														 f'ring to {collision["move_ring_to"]}'))

			isec = self.head_cross_thread(prev_loc, gcline) if gcline.is_xymove() else None
			move_type = 'fixing' if gcline.is_xyextrude() else 'normal'
			with Saver(self.head_loc, 'z') as saver:
				raise_amt = self.config['general'].get('thread_crossing_head_raise', {}).get(move_type)
				if isec and raise_amt > 0:
					gclines.extend(self.execute_gcode(GCLine('G0',
					args={'Z':self.head_loc.z + raise_amt},
						comment=f'gfunc_move_axis({gcline}) raise head by {raise_amt} to avoid thread snag')))

			if 'fake from [747]' in (gcline.comment or '') and gcline.x == 69.8:
				print(f'{prev_loc=}, {self.head_loc=}')

			#If there's no Y movement we don't need to do anything; the bed doesn't
			# move so the thread angle won't change
			if not gcline.y or gcline.y == prev_loc.y:
				pass

			#If the bed is moving, we want to move the thread simultaneously to keep
			# it in the same relative position
			else:
				gcline = self.sync_ring(gcline)

			#Add the line to the list of lines to be executed
			gclines.append(gcline)

			#Pause for fixing moves if so configured
			if isec and move_type == 'fixing':
				if pause := self.config['general'].get('post_thread_overlap_pause', 0):
					gclines.extend(self.execute_gcode(
						GCLine(code='G4', args={'S': pause}, comment=f'Pause for {pause} sec after print-over')))

			if saver:
				gclines.extend(self.execute_gcode(
					GCLine('G0', args={'Z': saver.originals['z']}, comment='Drop head back to original location')))

		return gclines


	def sync_ring(self, gcline:GCLine) -> GCLine:
		"""Return the a copy of the line with a ring movement added to keep the
		thread angle in sync with bed movement. Update the ring angle accordingly.
		If the line contains no y movement, return the line unmodified."""
		if 'fake from [747]' in (gcline.comment or '') and gcline.x == 69.8:
			print(f'ring_delta_for_thread({self.thread_path}, {gcline.y}) with ring {self.ring}')
		ring_move_by = self.ring_delta_for_thread(self.thread_path, gcline.y)

		if ring_move_by is None:
			gcline = gcline.copy(add_comment=f'--- No ring intersection for thread {self.thread_path}')
		else:
			if ring_move_by != 0:
				new_ring_angle = self.ring.angle + ring_move_by
				gcline = gcline.copy(args={'A': ring_move_by.degrees},
													add_comment=f'(🧵{self.thread_path.angle:.3f}°,  ⃘{new_ring_angle:.3f}°)' if
													new_ring_angle != self.ring.angle else f'({self.info})')
				self.ring.angle = new_ring_angle

		return gcline


	def ring_move(self, dist:Angle=None, angle:Angle=None, comment='', raise_head=False) -> list[GCLine]:
		"""Emit gcode to move the ring. Specify exactly one of dist or angle. If
		raise_head is True and the thread will cross the head position, raise the
		head by the amount set in the configuration file."""
		if (dist is not None and angle is not None) or (dist is None and angle is None):
			raise ValueError('Specify exactly one of dist or angle')

		ring_move_by = dist if dist is not None else ang_diff(self.ring.angle, angle) #type: ignore # (checked for None above)
		self.ring.angle += ring_move_by

		gcode:list[GCLine] = []

		with Saver(self.head_loc, 'z') as saver:
			raise_amt = self.config['general'].get('thread_crossing_head_raise', {}).get('fixing' if raise_head else 'normal', 0)
			if raise_amt > 0 and self.thread_cross_head(ring_move_by):
				gcode.extend(self.execute_gcode(
					GCLine('G0', args={'Z':self.head_loc.z + raise_amt}, comment=f'ring_move() raise head by {raise_amt} to avoid thread snag')))

		gcode.extend([
			GCLine(f'M117 Ring {self.ring.angle+ring_move_by}'),
			GCLine('G0', args={'A': ring_move_by.degrees, 'F': self.ring_config['feedrate']}, comment=comment),
		])

		if saver:
			gcode.extend(self.execute_gcode(
				GCLine('G0', args={'Z': saver.originals['z']}, comment='Drop head back to original location')))

		return gcode


	def thread_cross_head(self, ring_move:Angle) -> bool:
		"""Return True if the ring move would cause the thread to cross the print
		head."""
		head_angle = self.head_loc.angle(self.thread_path.point)
		new_thread_angle = GHalfLine(self.thread_path.point, self.ring.angle2point(self.ring.angle + ring_move)).angle
		return sign(new_thread_angle - head_angle) == sign(head_angle - self.thread_path.angle)


	def head_cross_thread(self, head_loc, gcline:GCLine) -> None|GPoint:
		"""Return where the move from the current head position to the position
		in `gcline` would cause the head to cross the thread, or None if it doesn't."""
		if head_loc.x == gcline.x and head_loc.y == gcline.y:
			return None
		head_traj = GSegment(head_loc.as2d(), head_loc.copy(x=gcline.x, y=gcline.y, z=0))
		if gcline.lineno == 1285:
			print(f'Line: {gcline}, head: {head_loc}')
			print(f'Head set by: {self.head_set_by}')
			print(f'Prev head: {self.prev_loc}')
			print(f'Prev head set by: {self.prev_set_by}')
			print(f'Traj: {head_traj}')
			print(f'Thread: {self.thread_path}')
		#Assuming here that the ring is synced to the bed movement
		return self.thread_path.as2d().intersection(head_traj)



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
				GCLine('G0', args={'Z':self.head_loc.z + self.config['general']['thread_crossing_head_raise']},
					 comment='Raise head to avoid thread snag'),
				#Here we're setting the angle to the "nominal" value - where the
				# carrier should be based on the bed not moving; e.g., if y=0.
				GCLine('G0', args={'A':dist.degrees}, comment=f'({self.ring.angle+dist:.3f}°)')
			])
			if pause_after:
				pause = self.config['general']['post_thread_overlap_pause']
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
