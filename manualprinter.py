from __future__      import annotations
from copy            import copy
from rich            import print

from gcode_geom       import GPoint, GSegment, GHalfLine
from bed            import Bed
from python_gcode.gcode_printer  import GCodePrinter, E_REL
from python_gcode.gcline         import GCLine, comment
from logger         import rprint
from config         import get_general_config, get_bed_config


class Manualprinter(GCodePrinter):
	def __init__(self, config, initial_thread_path:GHalfLine, *args, **kwargs):
		self.config = config
		self.general_config = get_general_config(config)
		print(f"Loaded general config: {self.general_config}")
		# We don't load a ring config for the manual printer
		self.bed_config  = get_bed_config(config)
		print(f"Loaded bed: {self.bed_config}")

		#Move the zero points so the bed zero is actually 0,0
		self.bed_config['anchor']  -= self.bed_config['zero']
		self.bed_config['zero']    -= self.bed_config['zero']
		print(f"Bed now: {self.bed_config}")

		self._bed_config  = copy(self.bed_config)
		self.bed = Bed(anchor=self.bed_config['anchor'], size=self.bed_config['size'])
		super().__init__()

		self.next_thread_path = initial_thread_path

		self.add_codes('M109', action=self.gfunc_printer_ready)

		#The current path of the thread: the current thread anchor and the
		# direction of the thread.
		self.thread_path: GHalfLine = None
		self.target_anchor: GPoint|None  = None

		self.add_codes('G28', action=lambda gcline, **kwargs: [
			GCLine('G28 X Y Z ; Home only X, Y, and Z axes, but avoid trying to home A')])


	def __repr__(self):
		return f'Manual Printer (🧵={self.thread_path}, x={self.x}, y={self.y}, z={self.z})'


	@property
	def info(self): return f'🧵{self.thread_path}'


	def set_thread_path(self, thread_path:GHalfLine, target:GPoint) -> list[GCLine]:
		"""We have no ring to move - but we do need to tell the user to move the thread"""
		self.thread_path = thread_path
		self.target_anchor = target
		return [comment("About to move thread; blob_anchor() will happen next")]


	def blob_anchor(self) -> list[GCLine]:
		#Procedure:
		# * Ensure relative extruder mode (M83)
		# * Beep
		# * Display instruction
		# * Retract by ? (Frank uses -5)
		# * Park and wait
		# * Return to a point on the line that will be drawn across the anchor
		#   point, that is .4mm towards the origin of that line.
		# * Draw the "blob" by un-retracting then extruding extra (by 2?), then
		#   raising the head by 1.4mm while extruding 3.3
		# * Return to the start of the anchoring line (self's position) then draw
		#   the anchoring line
		# * Return to absolute extruder mode if that's what it was before (M82)

		gclines: list[GCLine] = []

		manual_settings = self.config['general']['manual_printer']
		park_settings = manual_settings['park_settings']
		blob_settings = manual_settings['blob_anchors']
		if not blob_settings['use_blob_anchors']:
			return gclines

		retract_amount      = park_settings['retract_amount']
		unpark_feedrate     = park_settings['unpark_feedrate']
		blob_amount1        = blob_settings['blob_amount1']
		blob_amount2        = blob_settings['blob_amount2']
		blob_feedrate       = blob_settings['blob_feedrate']
		blob_raise          = blob_settings['blob_raise']
		blob_raise_feedrate = blob_settings['blob_raise_feedrate']

		#Ensure relative extruder mode
		was_abs = False
		if self.e_mode != E_REL:
			was_abs = True
			gclines.append(GCLine('M83'))

		#Next lines will happen after user hits button

		#Unpark to blob point, draw blob
		rprint(f'{self.target_anchor=}\n{self.curr_gcseg=}')
		blob_point = GSegment(self.target_anchor, self.curr_gcseg.start_point).point_at_dist(.4)
		blob_line = GCLine('G0',
										args={'X':blob_point.x, 'Y':blob_point.y, 'Z':blob_point.z,
													'F':unpark_feedrate},
										comment='Move to blob point')
		gclines.extend([
			blob_line,
			blob_line,   #A second time because the first seems to get eaten by Buddy firmware
			GCLine( 'G1', args={'E':blob_amount1 - retract_amount, 'F':blob_feedrate},
						comment='Unretract plus first blob extrude'),
			GCLine( 'G1', args={'Z':blob_point.z + blob_raise, 'E':blob_amount2,
							'F':blob_raise_feedrate}, comment='Second blob extrude, with raise'),
			comment('Next thing should be drawing the original anchoring line')
		])

		if was_abs:
			gclines.append(GCLine('M82'))

		#Next gcline processed should return head to anchoring segment start and
		# print it, smushing down the blob on the way

		return gclines


	def gfunc_printer_ready(self, gcline: GCLine, **kwargs) -> list[GCLine]:
		"""At least with the current version of Cura, M109 is the last command
		before the printer starts actually doing things."""

		self.thread_path = self.next_thread_path

		return [
			gcline,
			GCLine(comment='--- Printer state ---'),
			GCLine(comment=repr(self.bed)),
			GCLine(comment=f'Print head: {self.head_loc}'),
		]


	def gcfunc_move_axis(self, gcline: GCLine, **kwargs) -> list[GCLine]:
		"""Process gcode lines with instruction G0, G1."""
		gclines = []

		#Keep a copy of the head location since super() will change it.
		self.prev_loc    = self.head_loc.copy()
		self.prev_set_by = self.head_set_by

		manual_settings = self.config['general']['manual_printer']
		park_settings = manual_settings['park_settings']

		pre_park_location = GPoint(*park_settings['pre_park_location'])
		retract_amount    = park_settings['retract_amount']
		retract_feedrate  = park_settings['retract_feedrate']
		#unpark_feedrate   = park_settings['unpark_feedrate']

		#Beep, instruct, retract and park
		gclines.extend([
			GCLine('M300', args={'S':40, 'P':10} , comment="Notification chirp"),
			GCLine(f'M117 Move to angle {self.thread_path.angle}'),
			GCLine('G1', args={
					'X': pre_park_location.x, 'Y': pre_park_location.y,
					'Z': self.z + pre_park_location.z,
					'E':retract_amount, 'F':retract_feedrate,
					}, comment="Move to pre-park location",
				),
			GCLine(manual_settings['pause_command'], comment="Pausing for manual thread angle"),
		])

		if self.config['general']['blob_anchors']['use_blob_anchors']:
			gclines.extend(
				self.blob_anchor() if self.target_anchor is not None else [])
		else:
			gclines.append(GCLine('G1', args={'E': -retract_amount}, comment='Unretract'))

		gclines.extend(super().gcfunc_move_axis(gcline, **kwargs) or [gcline])

		self.target_anchor = None

		return gclines
