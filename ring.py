from Geometry3D import Circle, Vector, Line, get_eps
from math import cos, sin

from gcline import GCLine
from geometry import GPoint, GSegment, GHalfLine
from geometry.utils import ang_diff, circle_intersection
from util import attrhelper
from geometry.angle import Angle, atan2

from plot_helpers import update_figure

class Ring:
	"""A class representing the ring and thread carrier."""
	#Default plotting style
	style = {
		'ring':      {'line': dict(color='white', width=10), 'opacity':.25},
		'indicator': {'line': dict(color='blue',  width= 4)},
	}

	#TODO: add y-offset between printer's x-axis and ring's x-axis
	def __init__(self, angle:Angle, radius=100, center:GPoint=None, rot_mul=1):
		self.radius       = radius
		self._angle:Angle = angle
		self.center       = GPoint(radius, 0, 0) if center is None else GPoint(center).copy()

		#Set to -1 if positive E commands make the ring go clockwise
		self.rot_mul  = rot_mul

	x = property(**attrhelper('center.x'))
	z = property(**attrhelper('center.z'))


	def __repr__(self):
		return f'Ring({self.angle:.2f}°, ⌀{self.radius*2}, ⊙{self.center})'


	@property
	def y(self): return self.center.y

	@y.setter
	def y(self, val):
		if val == self.center.y: return
		mv = Vector(0, val - self.center.y, 0)
		self.center.move(mv)
		self.geometry.move(mv)


	def attr_changed(self, attr, old_value, new_value):
		raise ValueError(f"Can't adjust the {attr} coordinate of the ring!")


	@property
	def point(self):
		return self.angle2point(self.angle)








	def intersection(self, seg:GSegment|GHalfLine|Line) -> list[GPoint]:
		return circle_intersection(self.center, self.radius, seg)


	def angle2point(self, angle:Angle):
		"""Return an x,y,z=0 location on the ring based on the given angle, without
		moving the ring."""
		return GPoint(
			cos(angle) * self.radius + self.center.x,
			sin(angle) * self.radius + self.center.y,
			self.center.z
		)


	def point2angle(self, point:GPoint) -> Angle:
		"""Given a point in the coordinate system of the ring's center coordinate,
		return the angle between the ring center and that point in degrees."""
		return atan2(point.y - self.center.y, point.x - self.center.x)


	def plot(self, fig, style=None, offset:Vector=None, angle:Angle=None):
		angle = self.angle if angle is None else angle
		center = self.center.copy()
		if offset: center.move(offset)
		fig.add_shape(
			name='ring',
			type='circle',
			xref='x', yref='y',
			x0=center.x-self.radius, y0=center.y-self.radius,
			x1=center.x+self.radius, y1=center.y+self.radius,
			**self.style['ring'],
		)
		update_figure(fig, 'ring', style, what='shapes')

		ringwidth = next(fig.select_shapes(selector={'name':'ring'})).line.width

		c1 = GPoint(
				self.center.x + cos(angle)*(self.radius-ringwidth/2),
				self.center.y + sin(angle)*(self.radius-ringwidth/2),
				self.center.z)
		c2 = GPoint(
				self.center.x + cos(angle)*(self.radius+ringwidth/2),
				self.center.y + sin(angle)*(self.radius+ringwidth/2),
				self.center.z)


		if offset:
			c1.move(offset)
			c2.move(offset)
		fig.add_shape(
			name='indicator',
			type='line',
			xref='x', yref='y',
			x0=c1.x, y0=c1.y,
			x1=c2.x, y1=c2.y,
			**self.style['indicator'],
		)
		update_figure(fig, 'indicator', style, what='shapes')


