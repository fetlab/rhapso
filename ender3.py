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
from copy           import copy
from math           import radians
from typing         import Collection
from more_itertools import flatten

from geometry       import GPoint, GSegment, GHalfLine
from bed            import Bed
from ring           import Ring
from printer        import Printer
from gcline         import GCLine, comments
from geometry.angle import Angle, atan2, asin, acos
from geometry.utils import ang_diff, circle_intersection
from logger         import rprint
from util           import Saver, Number
from config         import load_config, get_ring_config, get_bed_config, RingConfig, BedConfig

config      = load_config('ender3.yaml')
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


class Ender3(Printer):
	def __init__(self):
		print(f"Init: {ring_config}")
		self._ring_config = copy(ring_config)
		self._bed_config  = copy(bed_config)
		self.bed = Bed(anchor=bed_config['anchor'], size=bed_config['size'])
		self.ring = Ring(**ring_config)
		super().__init__(self.bed, self.ring)

		self.add_codes('M109', action=self.gfunc_printer_ready)


		#BUG: this doesn't get run
		self.add_codes('G28', action=lambda gcline, **kwargs: [
			GCLine('G28 X Y Z ; Home only X, Y, and Z axes, but avoid trying to home A')])


	def _calc_new_ring_angle(self, current_thread:GSegment, new_y:Number) -> Angle:
		"""Find out how to rotate the ring to keep the thread at the same angle during
		this move. "Move" the ring's center-y coordinate while keeping the bed
		static, then find where the thread will intersect it."""
		#Move ring center so x-axis is on new_y
		cur_ring_y = self.ring.y
		self.ring.center = self.ring.center.moved(y=new_y)

		#Find where the current thread intersects the moved ring
		isecs = self.ring.intersection(current_thread)

		#Return amount to move the ring, involving least movement
		ring_move = min((ang_diff(isec.angle(self.ring.center), self.ring.angle) for isec in isecs), key=abs)

		#Restore ring center
		self.ring.y = cur_ring_y
	def gfunc_printer_ready(self, gcline: GCLine, **kwargs) -> list[GCLine]:
		"""At least with the current version of Cura, M109 is the last command
		before the printer starts actually doing things."""

		self.ring.angle = ring_config['home_angle']
		self.anchor = bed_config['anchor']
		return [
			gcline,
			GCLine(f'G92 A{ring_config["home_angle"]} '
				f'; Assume the ring has been manually homed, set its position to {ring_config["home_angle"]}°'),
			GCLine(comment='--- Printer state ---'),
			GCLine(comment=repr(self.ring)),
			GCLine(comment=repr(self.bed)),
			GCLine(comment=f'Anchor: {self.anchor}'),
			GCLine(comment=f'Carrier: {self.ring.point}'),
			GCLine(comment=f'Print head: {self.head_loc}'),
		]

		return ring_move



	#Note: in order to avoid confusion and keep things cleaner, we use
	# self.gcode_ring_angle in order to track the ring angle as output in
	# gcode, rather than (as previously) making changes to the Ring object.
	def gcfunc_set_axis_value(self, gcline: GCLine, **kwargs) -> list[GCLine]:
		"""Process gcode lines with instruction G0, G1, or G92. Move the ring such
		that the thread stays in place with any Y movement.  We do not do this
		movement on fixing steps or if the gcode line already includes ring
		movement."""

		gclines:list[GCLine] = []

		#Keep a copy of the head location since super() will change it.
		prev_loc = self.head_loc.copy()

		#Run the passed gcode line `gcline` through the Printer class's
		# gfunc_set_axis_value() function. This might return multiple lines, so we
		# need to process each of the returned list values.
		super_gclines = super().gcfunc_set_axis_value(gcline) or [gcline]

		#Fixing segment, we *want* interference! We should have already moved the
		# ring into place, so no processing is required
		if kwargs.get('fixing'):
			return [l.copy(add_comment='Fixing segment, no ring movement') for l in super_gclines]

		for gcline in super_gclines:

			#If there's an 'A' argument, it's a ring move line already, which means
			# it's "on purpose" and we need to keep track of it in our state. We're
			# assuming ring moves use relative coordinates.
			if 'A' in gcline.args:
				#This will be the "nominal" angle, under the assumption that the bed
				# and ring don't move relative to each other.
				self.ring.angle += radians(gcline.args['A'])  #GCode A arguments are in degrees
				self.ring.angle %= 360

				#But in fact the bed does move, so we need to re-calculate to find
				# out what the angle should actually be.
				current_thread = GSegment(self.anchor, self.ring.point).as2d()
				ring_move_by   = self._calc_new_ring_angle(current_thread, self.y)
				new_ring_angle = self.gcode_ring_angle + ring_move_by

				gclines.append(gcline.copy(args={'A': ring_move_by.degrees}, add_comment=(
					f'Ring at {self.ring.angle:.3f}°, gcode angle at {self.gcode_ring_angle:.3f}°,',
					f'change requested was {ring_move_by:.3f}°, new ring angle is {new_ring_angle:.3f}°')))

				self.gcode_ring_angle = new_ring_angle

				if gcline.is_xymove(): raise ValueError("Can't handle a move plus an angle set")

				continue

			#If there's no Y movement we don't need to do anything; the bed doesn't
			# move so the thread angle won't change
			if not gcline.y or gcline.y == prev_loc.y:
				gclines.append(gcline.copy(add_comment=(
					f'(No Y coord)'
					if not gcline.y else
					f'- gcline.y ({gcline.y}) == prev_loc.y ({prev_loc.y})')))

				continue

			#Find out how to rotate the ring to keep the thread at the same angle during
			# this move. "Move" the ring's center-y coordinate while keeping the bed
			# static, then find where the thread will intersect it.
			current_thread  = GSegment(self.anchor, self.ring.point).as2d()
			try:
				ring_move_by = self._calc_new_ring_angle(current_thread, gcline.y)
			except ValueError:
				gclines.append(gcline.copy(add_comment=f'--- No ring intersection for segment {current_thread}'))
				continue

			new_ring_angle = self.ring.angle + ring_move_by
			if new_ring_angle != self.ring.angle:
				gcline = gcline.copy(args={'A': ring_move_by.degrees}, add_comment=f'({new_ring_angle:.3f}°)')
				self.gcode_ring_angle = new_ring_angle
			gclines.append(gcline)

		return gclines


	def gcode_ring_move(self, dist, pause_after=False) -> list[GCLine]:
		if dist == 0: return []

		gcode = comments(f"""
			gcode_ring_move({dist:.3f}°)
			{self.ring}
			{self.gcode_ring_angle = }
			""")

		#Save the current z value, then raise the print head if needed
		with Saver(self.head_loc, 'z') as saver:
			gcode += self.execute_gcode([
				GCLine('G0', args={'Z':self.head_loc.z + config['general']['thread_crossing_head_raise']},
					 comment='Raise head to avoid thread snag'),
				#Here we're setting the angle to the "nominal" value - where the
				# carrier should be based on the bed not moving; e.g., if y=0.
				GCLine('G0', args={'A':dist.degrees}, comment=f'({self.gcode_ring_angle+dist:.3f}°)')
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
		self.anchor = self.bed.anchor


	def thread_intersect(self, target:GPoint, anchor:GPoint|None=None, set_new_anchor=True, move_ring=True) -> Angle:
		#Move the ring's `y` to the target's `y` to simulate the moving bed, then
		# do thread intersection.
		cur_ring_y = self.ring.y
		self.ring.center = self.ring.center.moved(y=target.y)
		rprint(f'Ring.y {cur_ring_y:.2f} → {self.ring.center.y:.2f}')

		r = super().thread_intersect(target, anchor, set_new_anchor, move_ring)

		self.ring.y = cur_ring_y

		return r
