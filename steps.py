from util import find
from step import Step
from logger import rprint
from gcline import GCLine, comment


class Steps:
	def __init__(self, layer, printer):
		self.layer         = layer
		self.printer       = printer
		self.steps         = []


	def __repr__(self):
		return f'{len(self.steps)} Steps for layer {self.layer}\n' + '\n'.join(map(repr, self.steps))


	@property
	def current(self):
		return self.steps[-1] if self.steps else None


	def new_step(self, *messages, debug=True):
		self.steps.append(Step(self, ' '.join(map(str,messages)), debug=debug))
		self.current.number = len(self.steps) - 1
		self.current.printer.debug_avoid = set()
		if debug: rprint(f'\n{self.current}')
		return self.current


	def step_exited(self, step):
		"""When a Step exits it will call this."""
		if not step.valid:
			rprint(f"Step {step.number} invalid, deleting")
			del(self.steps[-1])


	def gcode(self) -> list[GCLine]:
		"""Return the gcode for all steps."""
		r: list[GCLine] = self.printer.execute_gcode(self.layer.preamble.data)

		for i,step in enumerate(self.steps):
			step_gcode = step.gcode()
			r.append(comment(f'Step {step.number} ({len(step_gcode)} lines): {step.name} {"-"*25}'))
			r.extend(step_gcode)

		#Finally add any extra attached to the layer
		r.append(comment('Layer postamble ------'))
		r.extend(self.printer.execute_gcode(self.layer.postamble))

		return r
