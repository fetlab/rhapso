"""Select the thread sketch line. Copy the below and paste into the text
commands window of Fusion."""

exec("""
import sys
from subprocess import Popen, PIPE
import adsk.core, adsk.fusion
app = adsk.core.Application.get()
ui  = app.userInterface

def get_thread():
	selections = ui.activeSelections
	curve = selections[0].entity
	sketch = curve.parentSketch
	connected_curves = sketch.findConnectedCurves(curve)

	for c in connected_curves:
		selections.add(c)

	def m(l):
		return [f'{i*10:.4f}' for i in l]

	#Get geometry
	geom = []
	for c in connected_curves:
		geom.append(
			'[' + ', '.join(m(c.worldGeometry.startPoint.asArray())) + ']'
		)
	geom.append(
		'[' + ', '.join(m(c.worldGeometry.endPoint.asArray())) + ']'
	)
	geom = '[' + ', '.join(geom) + ']'

	if sys.platform == 'darwin':
		Popen("pbcopy",
			env={'LANG': 'en_US.UTF-8'},
			stdin=PIPE).communicate(repr(geom).encode('utf-8'))
		print("Copied path to clipboard in millimeters:")

	print(geom)

get_thread()
""")

#Old version, makes [(p0, p1), (p1, p2), ...]
exec("""
import sys
from subprocess import Popen, PIPE
import adsk.core, adsk.fusion
app = adsk.core.Application.get()
ui  = app.userInterface

def get_thread():
	selections = ui.activeSelections
	curve = selections[0].entity
	sketch = curve.parentSketch
	connected_curves = sketch.findConnectedCurves(curve)

	for c in connected_curves:
		selections.add(c)

	def m(l):
		return [f'{i*10:.4f}' for i in l]

	#Get geometry
	geom = []
	for c in connected_curves:
		geom.append('(' +
			'[' + ', '.join(m(c.worldGeometry.startPoint.asArray())) + '], ' +
			'[' + ', '.join(m(c.worldGeometry.endPoint.asArray())) + ']' +
			')')
	geom = '[' + ', '.join(geom) + ']'

	if sys.platform == 'darwin':
		Popen("pbcopy",
			env={'LANG': 'en_US.UTF-8'},
			stdin=PIPE).communicate(repr(geom).encode('utf-8'))
		print("Copied path to clipboard in millimeters:")

	print(geom)

get_thread()
""")
