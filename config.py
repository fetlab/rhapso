from typing import TypedDict
from geometry import GPoint
from geometry.angle import Angle
from util import Number
import yaml

BedConfig  = TypedDict(
	'BedConfig',  {
		'zero':   GPoint,
		'size':   tuple[Number, Number],
		'anchor': GPoint,
	})

RingConfig = TypedDict(
	'RingConfig', {
		'center':     GPoint,
		'radius':     Number,
		'rot_mul':    Number,
		'angle':      Angle,
		'home_angle': Angle,
	})


def get_ring_config(config:dict) -> RingConfig:
	"""Construct a ring configuration from the config dictionary."""
	r = config['ring']
	esteps_per_degree = r['stepper_microsteps_per_rotation'] * r['ring_gear_teeth'] / r['motor_gear_teeth'] / 360

	return dict(
		center     = GPoint(*r['center']),
		radius     = r['radius'],
		rot_mul    = esteps_per_degree / config['general']['default_esteps_per_unit'],
		angle      = Angle(degrees=r['home_angle']),
		home_angle = Angle(degrees=r['home_angle']),
	)


def get_bed_config(config:dict) -> BedConfig:
	b = config['bed']
	return dict(
		zero   = GPoint(*b['zero']),
		size   = b['size'],
		anchor = GPoint(*b['anchor']),
	)


def load_config(config_file:str) -> dict:
	with open(config_file, 'rb') as fp:
		config = yaml.load(fp, yaml.Loader)
	if not config: raise ValueError(f"Empty config file {config_file}")
	return config
