from Geometry3D import Circle, Vector, Line, get_eps
from math import cos, sin

from gcline import GCLine
from geometry import GPoint, GSegment, GHalfLine
from geometry.utils import ang_diff
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
		self.radius      = radius
		self.angle:Angle = angle
		self.center      = GPoint(radius, 0, 0) if center is None else GPoint(center).copy()
		self.geometry    = Circle(self.center, Vector.z_unit_vector(), self.radius, n=100)

		#Set to -1 if positive E commands make the ring go clockwise
		self.rot_mul  = rot_mul

	x = property(**attrhelper('center.x'))
	z = property(**attrhelper('center.z'))


	def __repr__(self):
		return f'Ring({self.angle}, ⌀{self.radius*2}, ⊙{self.center})'


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


	#Source: https://stackoverflow.com/a/59582674/49663
	def intersection(self, seg:GSegment|GHalfLine|Line) -> list[GPoint]:
		"""Return the intersection points between a segment, HalfLine, or Line, and
		the ring, or an empty list if there are none. If the segment is tangent to
		the ring, return a list with one point."""
		if   isinstance(seg, GSegment):  p1, p2 = seg[:]
		elif isinstance(seg, GHalfLine): p1, p2 = seg.point, seg.point + seg.vector
		elif isinstance(seg, Line):      p1, p2 = GPoint(*seg.sv), GPoint(*(seg.sv + seg.dv))
		else: raise ValueError(f"Can't intersect with {type(seg)}")

		#Shift the points by the ring center and extract x and y
		x1, y1, _ = (p1 - self.center)[:]
		x2, y2, _ = (p2 - self.center)[:]

		dx, dy, _    = (p2 - p1)[:]
		dr           = (dx**2 + dy**2)**.5
		big_d        = x1*y2 - x2*y1
		discriminant = self.radius**2 * dr**2 - big_d**2

		#No intersection between segment and circle
		if discriminant < 0: return []

		#Find intersections and shift them back by the ring center
		intersections = [GPoint(
			( big_d * dy + sign * (-1 if dy < 0 else 1) * dx * discriminant**.5) / dr**2,
			(-big_d * dx + sign * abs(dy) * discriminant**.5) / dr**2,
			0).moved(Vector(*self.center))
									 for sign in ((1,-1) if dy < 0 else (-1, 1))]

		if not isinstance(seg, Line):
			hl = (GHalfLine(*seg) if isinstance(seg, GSegment) else seg).as2d()
			intersections = [p for p in intersections if p in hl]

		if len(intersections) == 2 and abs(discriminant) <= get_eps(): return [intersections[0]]

		return sorted(intersections, key=p1.distance)


	def angle2point(self, angle:Angle) -> GPoint:
		"""Return an x,y,z=0 location on the ring based on the given angle, without
		moving the ring."""
		return GPoint(
			cos(angle) * self.radius + self.center.x,
			sin(angle) * self.radius + self.center.y,
			self.center.z
		)


	def point2angle(self, point:GPoint) -> Angle:
		"""Given a point, return the angle between the ring center and that
		point in degrees."""
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


