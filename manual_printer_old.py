from math import sin, cos
from pathlib import Path
from zipfile import ZipFile
from fastcore.basics import first
from gcode_printer import GCodePrinter
from geometry import GHalfLine, GPolyLine, GSegment, GPoint
from geometry.angle import Angle
from gcline import GCLine
import xml.etree.ElementTree as ET
import numpy as np

namespace = {
		"3mf": "http://schemas.microsoft.com/3dmanufacturing/core/2015/02",
		"m"  : "http://schemas.microsoft.com/3dmanufacturing/material/2015/02"
}

class ManualPrinter(GCodePrinter):
	def __init__(self, config, initial_thread_path:GHalfLine, thread:GPolyLine,
							grabber_filename: str|Path, model_filename: str|Path, *args, **kwargs):
		self.config = config
		self.thread = thread
		super().__init__()

		self.grabber_filename = Path(grabber_filename)
		self.model_filename   = Path(model_filename)
		self.xml_grabber_name = self.config.get('general', {}).get('xml_grabber_name', 'Grabber')

		if self.grabber_filename.suffix.lower() != '.3mf' or self.model_filename.suffix.lower() != '.3mf':
			raise ValueError('Filenames must end in .3mf')


	def set_thread_path(self, thread_path, target) -> list[GCLine]:
		"""Return code to pause the print and display a message about where the
		thread should be moved to next."""
		gclines = [GCLine(code='M117', args={None: f'Move thread to {thread_path.angle}'})]
		return gclines + self.gcode_pause_for_thread(thread_path, target)


	def gcode_pause_for_thread(self, thread_path:GPolyLine, target:GPoint) -> list[GCLine]:
		"""Return gcode to pause for thread insertion."""
		raise NotImplementedError


	def create_grabbers(self):
		"""Create grabbers. The grabber in `grabber_filename` should be named
		`xml_grabber_name` (e.g., name the body that in Fusion). Both filenames
		should have .3mf extensions."""
		x0, y0, _ = self.config['bed']['zero']
		x1, y1    = self.config['bed']['size']
		bed_outline = [
			GSegment((x0,    y0,    0), (x0,    y0+y1, 0)),
			GSegment((x0,    y0+y1, 0), (x0+x1, y0+y1, 0)),
			GSegment((x0+x1, y0+y1, 0), (x0+x1, y0,    0)),
			GSegment((x0+x1, y0,    0), (x0,    y0,    0))
		]

		grabber_size = [0.0, 0.0, 0.0]

		new_grabber_filename = self.model_filename.parent.joinpath(
			self.model_filename.stem + '-grab' + self.model_filename.suffix)

		with ZipFile(self.grabber_filename, 'r') as grabber_zip:
			#Register namespaces so writing works correctly (https://stackoverflow.com/a/54491129/49663)
			model = grabber_zip.open('3D/3dmodel.model')
			for _, (ns, uri) in ET.iterparse(model, events=['start-ns']):
				ET.register_namespace(ns, uri)
			model.seek(0)

			#Find the grabber size so we can keep it from overlapping the bed edges
			tree = ET.parse(model)
			root = tree.getroot()
			if root is None: raise ValueError("No root element in XML file")
			grabber = root.find(f'./3mf:resources/3mf:object[@name="{self.xml_grabber_name}"]', namespace)
			if grabber is None:
				raise ValueError(f"Can't find any object named {self.xml_grabber_name} in file.")

			mins = [float( 'inf')]*3
			maxs = [float('-inf')]*3
			for vertex in root.findall("./3mf:resources/3mf:object/3mf:mesh/3mf:vertices/3mf:vertex", namespace):
				vals = [float(vertex.get(a, 0)) for a in 'xyz']
				mins = [min(old, new) for old, new in zip(mins, vals)]
				maxs = [max(old, new) for old, new in zip(maxs, vals)]
			grabber_size = max([x-n for x,n in zip(maxs, mins)])

			#Remove any instances of the grabber in the 3mf
			builds = root.find(f'./3mf:build', namespace)
			if builds is None:
				raise ValueError("Can't find <build> section in 3D/3dmodel.model")
			for build_obj in builds:
				builds.remove(build_obj)

			seg_hls = [GHalfLine(*seg[:]).as2d() for seg in self.thread.segments]

			#Make multiple instances of grabber, then rotate and place them
			for i, hl in enumerate(seg_hls):
				isec = first([hl.intersection(i) for i in bed_outline], f=lambda v:v is not None and v != hl.point)

				#Find the point in from the intersection to prevent grabbers being off-bed
				#TODO: Need to avoid overlapping grabbers!
				# This probably needs to be done as a Fusion plugin?
				new_loc = isec.moved(-hl.vector.normalized() * grabber_size * 1.1)

				ang = hl.angle()
				matrix = np.array([
					[ cos(ang), sin(ang), 0],
					[-sin(ang), cos(ang), 0],
					[       0,         0, 1],
					list(new_loc[:]),
				])
				transform = ' '.join(f'{i:.6f}' for i in np.reshape(matrix, -1))

				builds.append(ET.Element(f'{{{namespace["3mf"]}}}item',
					attrib={'objectid':grabber.attrib["id"], 'transform':transform }))

			#Copy the contents of the grabber file, but add the new grabbers
			with ZipFile(new_grabber_filename, 'w') as new_grabber_zip:
				for item in grabber_zip.infolist():
					if item.filename.lower() != '3D/3dmodel.model'.lower():
						data = grabber_zip.read(item.filename)
						new_grabber_zip.writestr(item, data)
					else:
						new_grabber_zip.writestr('3D/3dmodel.model', ET.tostring(root, xml_declaration=True))

			print(f'Made grabber file {new_grabber_filename}')