from gclayer import Layer
from util import listsplit
import re

class Cura4Layer(Layer):
	"""A Layer, but using the comments in the Cura gcode to add additional useful
	members:
		Layer.meshes -> a list of sub-meshes to be found in this layer
			each containing
				.features -> a dict of lines by feature type

	Cura Gcode as of 4.12.1 has the same pattern every layer except layer 0.
	"""
	def __init__(self, lines=[], layernum=None):
		super().__init__(lines, layernum)
		parts = listsplit(lines,
				lambda l: l.line.startswith(';TYPE:'), keepsep='>', minsize=1)
		self.parts = {m.group(1) if (m:=re.search('TYPE:(.*)',lines[0].line)) else 'NONE': lines
								for lines in parts}
