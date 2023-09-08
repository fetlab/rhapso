from math import pi
from copy import copy, deepcopy
from collections import defaultdict
from typing import Collection, Callable
from itertools import groupby
from more_itertools import flatten
from fastcore.basics import first, listify
from Geometry3D import Line, Vector
from rich.pretty import pretty_repr

from rich.console import Console
print = Console(style="on #272727").print

from util import attrhelper, Number
from geometry import GPoint, GSegment, GHalfLine
from gcline import GCLine, GCLines
from gclayer import Layer
from geometry_helpers import visibility, too_close
from geometry.utils import angsort, ang_diff, ang_dist, eps
from geometry.angle import Angle

class GCodePrinter:
	"""Simulates a printer in order to generate gcode."""
	def __init__(self, *args, **kwargs):

		#State: absolute extrusion amount, print head location, anchor location
		# (initially the bed's anchor)
		self.e          = 0
		self.head_loc   = GPoint(0, 0, 0)
		self.head_set_by = None
		self.prev_loc = GPoint(0,0,0)
		self.prev_set_by = None

		#Functions for different Gcode commands
		self._code_actions: dict[str|None,Callable] = {}
		self.add_codes(None,       action=lambda gcline, **kwargs: [gcline])
		self.add_codes('G28',      action=self.gcfunc_auto_home)
		self.add_codes('G0', 'G1', action=self.gcfunc_move_axis)
		self.add_codes('G92',      action=self.gcfunc_set_axis_value)


	#Create attributes which call Printer.attr_changed on change
	x = property(**attrhelper('head_loc.x'))
	y = property(**attrhelper('head_loc.y'))
	z = property(**attrhelper('head_loc.z'))

	@property
	def xy(self): return self.x, self.y

	def __repr__(self):
		return f'{self.__class__.__name__}(x={self.x}, y={self.y}, z={self.z})'


	def add_codes(self, *codes, action:str|Callable):
		"""Add the given action for each code in `codes`. `action` can be a string,
		in which case the line of gcode will be saved as an attribute with that
		name on this object, or it can be a function, in which case that function
		will be called with the line of gcode as a parameter."""
		for code in codes:
			if isinstance(action, str):
				self._code_actions[code] = lambda v: setattr(self, action, v) #type: ignore #Checked for action type
			elif callable(action):
				self._code_actions[code] = action
			else: raise ValueError(f'Need function or string for `action`, not {type(action)}')


	#Functions to add extra lines of GCode. Each is passed the pre/postamble and
	# should return it, possibly modified.
	def file_preamble  (self, preamble:  list[GCLine]) -> list[GCLine]: return preamble
	def file_postamble (self, postamble: list[GCLine]) -> list[GCLine]: return postamble
	def layer_preamble (self, preamble:  list[GCLine], layer:Layer) -> list[GCLine]: return preamble
	def layer_postamble(self, postamble: list[GCLine], layer:Layer) -> list[GCLine]: return postamble


	def set_thread_path(self, thread_path:GHalfLine, target:GPoint) -> list[GCLine]:
		raise NotImplementedError("Subclass must implement gcode_set_thread_path")


	def _execute_gcline(self, gcline:GCLine, **kwargs) -> list[GCLine]:
		return self._code_actions.get(gcline.code, self._code_actions[None])(gcline, **kwargs) or [gcline]


	def execute_gcode(self, gcline:GCLine|list[GCLine], **kwargs) -> list[GCLine]:
		return sum([self._execute_gcline(l, **kwargs) for l in listify(gcline)], [])


	#G28
	def gcfunc_auto_home(self, gcline: GCLine, **kwargs):
		self.x, self.y, self.z = 0, 0, 0


	#G0, G1
	def gcfunc_move_axis(self, gcline:GCLine, **kwargs):
		return self.gcfunc_set_axis_value(gcline, **kwargs)


	#G0, G1, G92
	def gcfunc_set_axis_value(self, gcline: GCLine, **kwargs):
		#Track head location
		if gcline.x: self.x = gcline.x
		if gcline.y: self.y = gcline.y
		if gcline.z: self.z = gcline.z

		if any((gcline.x, gcline.y, gcline.z)):
			self.head_set_by = gcline

		if 'E' in gcline.args:
			#G92: software set value
			if gcline.code == 'G92':
				self.e = gcline.args['E']

			#A normal extruding line; we need to use the relative extrude value
			# since our lines get emitted out-of-order
			else:
				self.e += gcline.relative_extrude
				return [gcline.copy(args={'E': self.e})]
