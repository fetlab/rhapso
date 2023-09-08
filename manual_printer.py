from math import sin, cos
from pathlib import Path
from zipfile import ZipFile
from fastcore.basics import first
from gcode_printer import GCodePrinter
from geometry import GHalfLine, GPolyLine, GSegment
from geometry.angle import Angle
from gcline import GCLine
import xml.etree.ElementTree as ET
import numpy as np

namespace = {
		"3mf": "http://schemas.microsoft.com/3dmanufacturing/core/2015/02",
		"m"  : "http://schemas.microsoft.com/3dmanufacturing/material/2015/02"
}

class ManualPrinter(GCodePrinter):
	def __init__(self, config, initial_thread_path:GHalfLine, thread:GPolyLine, *args, **kwargs):
		self.config = config
		self.thread = thread
		super().__init__()

	def set_thread_path(self, thread_path, target) -> list[GCLine]:
		"""Return code to pause the print and display a message about where the
		thread should be moved to next."""
		return [
				GCLine(code='M117', args={None: f'Move thread to {thread_path.angle}'}),
				GCLine(code='M601', comment='Pause, wait for user to click buttton')
				]


	def add_grabbers(self, grabber_filename, model_filename, xml_grabber_name="Grabber"):
		"""Add grabbers to the model. Both `grabber_filename` and `model_filename`
		should refer to .3MF files."""
		x0, y0, _ = self.config['bed']['zero']
		x1, y1    = self.config['bed']['size']
		bed_outline = [
			GSegment((x0,    y0,    0), (x0,    y0+y1, 0)),
			GSegment((x0,    y0+y1, 0), (x0+x1, y0+y1, 0)),
			GSegment((x0+x1, y0+y1, 0), (x0+x1, y0,    0)),
			GSegment((x0+x1, y0,    0), (x0,    y0,    0))
		]

		grabber_size = [0.0, 0.0, 0.0]

		#Get the grabber model from its 3mf file
		with ZipFile(grabber_filename, 'r') as model_zip:
			tree = ET.parse(model_zip.open('3D/3dmodel.model'))
			grabber = tree.find(f'./3mf:resources/3mf:object[@name="{xml_grabber_name}"]', namespace)
			build = tree.find(f'./3mf:build/3mf:item[@objectid="{grabber.attrib["id"]}"]', namespace)

			mins = [float( 'inf')]*3
			maxs = [float('-inf')]*3
			for vertex in tree.findall("./3mf:resources/3mf:object/3mf:mesh/3mf:vertices/3mf:vertex", namespace):
				vals = [float(vertex.get(a, 0)) for a in 'xyz']
				mins = [min(old, new) for old, new in zip(mins, vals)]
				maxs = [max(old, new) for old, new in zip(maxs, vals)]
			grabber_size = max([x-n for x,n in zip(maxs, mins)])

		#Modify the model file with grabbers
		with ZipFile(model_filename, 'r') as model_zip:
			model = model_zip.open('3D/3dmodel.model')
			#Register namespaces so writing works correctly (https://stackoverflow.com/a/54491129/49663)
			for _, (ns, uri) in ET.iterparse(model, events=['start-ns']):
				ET.register_namespace(ns, uri)
			model.seek(0)

			#Load the model 3mf file
			tree = ET.parse(model)
			objects = tree.findall('./3mf:resources/3mf:object', namespace)
			max_id = max([int(obj.attrib['id']) for obj in objects])

			#Add the grabber geometry to the model file
			gid = str(max_id + 1)
			grabber.attrib['id'] = gid
			tree.find('./3mf:resources', namespace).append(grabber)
			builds = tree.find(f'./3mf:build', namespace)

			#Make multiple instances of grabber, then rotate and place them
			for i, seg in enumerate(self.thread.segments):
				seg = seg.as2d()
				hl = GHalfLine(*seg[:])
				isec = first([hl.intersection(i) for i in bed_outline], f=lambda v:v is not None and v != hl.point)

				#Find the point in from the intersection to prevent grabbers being
				# off-bed
				new_loc = isec.moved(-hl.vector.normalized() * grabber_size * 1.1)

				ang = seg.angle()
				matrix = np.array([
					[ cos(ang), sin(ang), 0],
					[-sin(ang), cos(ang), 0],
					[       0,         0, 1],
					list(new_loc[:]),
				])
				transform = ' '.join(f'{i:.6f}' for i in np.reshape(matrix, -1))

				print(seg, hl, isec)
				print(f'Grabber {i} at {new_loc} with angle {ang}')
				builds.append(ET.Element(f'{{{namespace["3mf"]}}}item',
														 attrib={'objectid': gid, 'transform':transform }))

			new_model = ET.tostring(tree.getroot(), xml_declaration=True)
			# tree.write('tmp/output_tree.xml', encoding='unicode', xml_declaration=True)
			#model_zip.writestr('3D/3dmodel.model', new_model)
