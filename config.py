from typing         import TypedDict
from geometry       import GPoint
from geometry.angle import Angle
from util           import Number
from importlib      import import_module
from pathlib        import Path
import yaml

BedConfig  = TypedDict(
	'BedConfig',  {
		'zero':   GPoint,
		'size':   tuple[Number, Number],
		'anchor': GPoint,
	})


CollisionAvoid = TypedDict(
	'CollisionAvoid', {
		'head_between':  tuple[Number, Number],
		'ring_between': tuple[Angle, Angle],
		'move_ring_to':  Angle,
	})

RingConfig = TypedDict(
	'RingConfig', {
		'center':           GPoint,
		'radius':           Number,
		'angle':            Angle,
		'home_angle':       Angle,
		'min_move':         Angle,
		'feedrate':         Number,
		'motor_gear_teeth': Number,
		'ring_gear_teeth':  Number,
		'stepper_microsteps_per_rotation': Number,
		'collision_avoid': list[CollisionAvoid],
	})


def get_ring_config(config:dict) -> RingConfig:
	"""Construct a ring configuration from the config dictionary."""
	r = config['ring']

	return dict(
		center           = GPoint(*r['center']),
		radius           = r['radius'],
		angle            = Angle(degrees=r['home_angle']),
		home_angle       = Angle(degrees=r['home_angle']),
		min_move         = Angle(degrees=360/r['stepper_microsteps_per_rotation']),
		feedrate         = r['feedrate'],
		motor_gear_teeth = r['motor_gear_teeth'],
		ring_gear_teeth  = r['ring_gear_teeth'],
		stepper_microsteps_per_rotation = r['stepper_microsteps_per_rotation'],
		collision_avoid = [dict(
			head_between  = ca['head_between'],
			ring_between = (Angle(degrees=ca['ring_between'][0]),
											Angle(degrees=ca['ring_between'][1])),
			move_ring_to  = Angle(degrees=ca['move_ring_to']),
			) for ca in r.get('collision_avoid', []) or []
		]
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
	try:
		module_name = Path(config_file).stem
		module = import_module(module_name)
		classname = ''.join(x.capitalize() or '_' for x in module_name.split('_'))
		_class = getattr(module, classname)
	except ModuleNotFoundError:
		raise ModuleNotFoundError(f"Can't load expected module {module_name} for config file {config_file}")
	except ImportError:
		raise ImportError(f"Can't load expected class {classname} from {module_name} for config file {config_file}")
	config['printer_class'] = _class
	return config
