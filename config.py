from typing         import TypedDict
from gcode_geom       import GPoint
from gcode_geom.angle import Angle
from util           import Number
from importlib      import import_module
from pathlib        import Path
import yaml

HeadCrossesThread = TypedDict(
	'HeadCrossesThread', {
		'head_raise':       Number,
		'head_raise_speed': Number,
    'overlap_length':   Number,
		'move_feedrate':    Number,
		'extrude_multiply': Number,
		'post_pause':       Number,
	})

GeneralConfig  = TypedDict(
	'GeneralConfig', {
		'initial_thread_angle': Number,
    'defaults':             HeadCrossesThread,
    'anchor_fixing':        HeadCrossesThread,
    'extruding':            HeadCrossesThread,
    'non_extruding':        HeadCrossesThread,
	})

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

def process_cross_config(crossConfig:dict[str]) -> HeadCrossesThread:
	return HeadCrossesThread(
		head_raise       = crossConfig.get('head_raise',			-1),
		head_raise_speed = crossConfig.get('head_raise_speed',	-1),
		overlap_length   = crossConfig.get('overlap_length',		-1),
		move_feedrate    = crossConfig.get('move_feedrate',		-1),
		extrude_multiply = crossConfig.get('extrude_multiply',	-1),
		post_pause       = crossConfig.get('post_pause',			-1),
	)

def get_general_config(config:dict) -> GeneralConfig:
	"""Construct a general configuration from the config dictionary."""
	general:dict[str] = config['general']
	crossConfigs:dict[str] = general['head_crosses_thread']

	return GeneralConfig(
		initial_thread_angle = general['initial_thread_angle'],
		defaults             = process_cross_config(crossConfigs['defaults']),
		anchor_fixing        = process_cross_config(crossConfigs['anchor_fixing']),
		extruding            = process_cross_config(crossConfigs['extruding']),
		non_extruding        = process_cross_config(crossConfigs['non_extruding']),
	)

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
		#Split on underscores here to allow for different configs for the same machine.
		# e.g. UoB_ender3.yaml
		module_name = Path(config_file).stem.split('_')[-1]
		module = import_module(module_name)
		classname = ''.join(x.capitalize() or '_' for x in module_name.split('_'))
		_class = getattr(module, classname)
	except ModuleNotFoundError:
		raise ModuleNotFoundError(f"Can't load expected module {module_name} for config file {config_file}")
	except ImportError:
		raise ImportError(f"Can't load expected class {classname} from {module_name} for config file {config_file}")
	config['printer_class'] = _class
	return config
