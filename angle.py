from math import trunc, ceil, floor, degrees as rad2deg, radians as deg2rad
from math import atan2 as _atan2, acos as _acos, asin as _asin
from numbers import Real

#Based on https://github.com/dstl/Stone-Soup/blob/main/stonesoup/types/angle.py
class Angle(Real):
	__slots__ = '_degrees', '_radians'

	def __init__(self, radians=None, degrees=None):
		if degrees is not None and radians is not None:
			raise ValueError('Must provide either degrees or radians, not both')

		if degrees is not None:
			self._degrees = degrees
			self._radians = deg2rad(degrees)
		elif radians is not None:
			self._radians = radians
			self._degrees = rad2deg(radians)
		else:
			raise ValueError('Must provide either degrees or radians')


	@classmethod
	def _r(cls, value): return value.radians if isinstance(value, cls) else value

	@property
	def radians(self): return self._radians

	@property
	def degrees(self): return self._degrees

	def __abs__(self):                 return self.__class__(abs(self.radians))
	def __neg__(self):                 return self.__class__(-self.radians)
	def __add__(self, other):          return self.__class__(self.radians + self._r(other))
	def __sub__(self, other):          return self.__class__(self.radians - self._r(other))
	def __mul__(self, other):          return self.__class__(self.radians * self._r(other))
	def __truediv__(self, other):      return self.__class__(self.radians / self._r(other))
	def __radd__(self, other):         return self.__class__.__add__(self, other)
	def __rsub__(self, other):         return self.__class__.__add__(-self, other)
	def __rmul__(self, other):         return self.radians * other
	def __rtruediv__(self, other):     return other / self.radians
	def __floordiv__(self, other):     return self.radians // self._r(other)
	def __mod__(self, other):          return self.radians % other

	def __hash__(self):                return hash(self.radians)
	def __float__(self):               return float(self.radians)
	def __str__(self):                 return str(self.radians)

	def __eq__(self, other):           return self.radians == other
	def __ne__(self, other):           return self.radians != other
	def __le__(self, other):           return self.radians <= other
	def __lt__(self, other):           return self.radians < other
	def __ge__(self, other):           return self.radians >= other
	def __gt__(self, other):           return self.radians > other

	def __floor__(self):               return floor(self.radians)
	def __ceil__(self):                return ceil(self.radians)

	def __pos__(self):                 return self.__class__(+self.radians)
	def __pow__(self, value):          return pow(self.radians, value)
	def __rfloordiv__(self, other):    return other // self.radians
	def __rmod__(self, other):         return other % self.radians
	def __round__(self, ndigits=None): return round(self.radians, ndigits=ndigits)
	def __rpow__(self, base):          return NotImplemented
	def __trunc__(self):               return trunc(self.radians)

	def __repr__(self):
		return "{0}({1!r})".format(self.__class__.__name__, float(self))



#Redefine trigonometric functions to return Angle objects
def atan2(y, x): return Angle(_atan2(y, x))
def acos(x):     return Angle(_acos(x))
def asin(x):     return Angle(_asin(x))
