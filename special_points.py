from geometry import GPoint

class NoSnapAnchor(GPoint):
	"""Represents an anchor which will not be snapped to the nearest 2D geometry
  It will still be snapped in Z."""
	def __repr__(self):
		return 'Š' + GPoint.__repr__(self)


class NonFixedAnchor(NoSnapAnchor):
	"""Represents an anchor which will not be printed over, so error checking
	should not be done."""
	def __repr__(self):
		return 'Ḟ' + GPoint.__repr__(self)


class BlobAnchor(GPoint):
	"""Represents an anchor which will be fixed with a blob"""
	def __repr__(self):
		return 'Ḇ' + GPoint.__repr__(self)
