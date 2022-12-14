#Avoid circular imports for type checking; see https://adamj.eu/tech/2021/05/13/python-type-hints-how-to-fix-circular-imports/
from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING: from printer import Printer

import re
from rich.markup import RE_TAGS
from util import find
from step import Step
from logger import rprint
from gcline import GCLine, comment
from gclayer import Layer


class Steps:
	def __init__(self, layer:Layer, printer:Printer):
		self.layer   = layer
		self.printer = printer
		self.steps: list[Step] = []


	def __repr__(self):
		return f'{len(self.steps)} Steps for layer {self.layer}\n' + '\n'.join(map(repr, self.steps))


	@property
	def current(self):
		return self.steps[-1] if self.steps else None


	def new_step(self, *messages, debug=True):
		self.steps.append(Step(self, ' '.join(map(str,messages)), debug=debug))
		self.current.number = len(self.steps) - 1
		if debug: rprint(f'\n{self.current}')
		return self.current


	def step_exited(self, step):
		"""When a Step exits it will call this."""
		if not step.valid:
			if step.debug:
				rprint(f"Step {step.number} invalid, deleting")
			del(self.steps[-1])


	def gcode(self) -> list[GCLine]:
		"""Return the gcode for all steps."""
		r: list[GCLine] = self.printer.execute_gcode(self.layer.preamble.data)
		if r:
			r.insert(0, comment(f'::: Layer {self.layer.layernum} preamble :::'))
			r.append(comment(f'::: End layer {self.layer.layernum} preamble :::'))

		for i,step in enumerate(self.steps):
			step_gcode = step.gcode()
			r.append(comment(re.sub(RE_TAGS, '', f'Layer {self.layer.layernum} - {step} {"-"*25}')))
			r.extend(step_gcode)

		#Finally add any extra attached to the layer
		if self.layer.postamble:
			r.append(comment(f'::: Layer {self.layer.layernum} postamble :::'))
			r.extend(self.printer.execute_gcode(self.layer.postamble))
			r.append(comment(f'::: End layer {self.layer.layernum} postamble :::'))

		return r
