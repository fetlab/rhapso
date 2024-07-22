from util import deep_update

styles_dark: dict[str, dict] = {
	#Generic styles
	'segments':     {'mode': 'lines', 'line': dict(color='blue', width=1)},
	'points':       {'mode': 'markers', 'marker': dict(color='violet',  symbol='circle', size=4)},
	'circles':      {'line':  dict(color='magenta', width=1)},
	'segpoints':    {'mode': 'markers+lines',
									 'marker':dict(color='green', symbol='circle', size=4)},

	#Thread styles
	'original_thread': {'line': dict(color='coral',     width=.5, dash='dot')},
	'thread_ring':     {'line': dict(color='white',     width=1,  dash='dot')},
	'future_thread':   {'line': dict(color='yellow',    width=1,  dash='dot')},
	'moved_thread':    {'line': dict(color='cyan',      width=.5, dash='dot')},
	'printed_thread':  {'line': dict(color='olivedrab', width=1,  dash='dot')},

	#Anchors
	'anchor':          {'marker': dict(color='red',     symbol='x', size=4)},
	'original_anchor': {'marker': dict(color='coral',   symbol='x', size=4)},
	'future_anchor':   {'marker': dict(color='blue',    symbol='x', size=4)},
	'thread_fixation': {'marker': dict(color='magenta', symbol='x', size=4)},
	'next_anchor':     {'marker': dict(symbol='circle', size=6, color='white', line=dict(width=2, color='red'))},

	#GCode segment styles
	'gc_segs':    {'line': dict(color='green',     width=2)},
	'old_layer':  {'line': dict(color='gray',      width=.5), 'opacity': .25},
	'old_segs':   {'line': dict(color='gray',      width=1)},
	'to_print':   {'line': dict(color='green',     width=.5), 'opacity': .25},
	'avoid_segs': {'line': dict(color='firebrick', width=1)},
	'isec_segs':  {'line': dict(color='orange',    width=1)},
}

#https://carbondesignsystem.com/data-visualization/color-palettes/
carbon_light = {
	'Purple 70':  '#6929c4',
	'Cyan 50':    '#1192e8',
	'Teal 70':    '#005d5d',
	'Magenta 70': '#9f1853',
	'Red 50':     '#fa4d56',
	'Red 90':     '#570408',
	'Green 60':   '#198038',
	'Blue 80':    '#002d9c',
	'Magenta 50': '#ee538b',
	'Yellow 50':  '#b28600',
	'Teal 50':    '#009d9a',
	'Cyan 90':    '#012749',
	'Orange 70':  '#8a3800',
	'Purple 50':  '#a56eff'
}


carbon_dark = {
	'Purple 60':  '#8a3ffc',
	'Cyan 40':    '#33b1ff',
	'Teal 60':    '#007d79',
	'Magenta 40': '#ff7eb6',
	'Red 50':     '#fa4d56',
	'Red 10':     '#fff1f1',
	'Green 30':   '#6fdc8c',
	'Blue 50':    '#4589ff',
	'Magenta 60': '#d12771',
	'Yellow 40':  '#d2a106',
	'Teal 40':    '#08bdba',
	'Cyan 20':    '#bae6ff',
	'Orange 60':  '#ba4e00',
	'Purple 30':  '#d4bbff',
}


styles_light: dict[str, dict] = {
	#Generic styles
	'segments':     {'mode': 'lines', 'line': dict(color='blue', width=1)},
	'points':       {'mode': 'markers', 'marker': dict(color='violet',  symbol='circle', size=4)},
	'circles':      {'line':  dict(color='magenta', width=1)},
	'segpoints':    {'mode': 'markers+lines',
									 'marker':dict(color='green', symbol='circle', size=4)},

	#Thread styles
	'original_thread': {'line': dict(color='coral',     width=.5, dash='dot')},
	'thread_ring':     {'line': dict(color='white',     width=1,  dash='dot')},
	'future_thread':   {'line': dict(color=carbon_light['Yellow 50'],    width=1,  dash='dot')},
	'moved_thread':    {'line': dict(color='cyan',      width=.5, dash='dot')},
	'printed_thread':  {'line': dict(color='olivedrab', width=1,  dash='dot')},

	#Anchors
	'anchor':          {'marker': dict(color='red',    symbol='x', size=4)},
	'original_anchor': {'marker': dict(color='coral', symbol='x', size=4)},

	#GCode segment styles
	'gc_segs':    {'line': dict(color='green',     width=2)},
	'old_layer':  {'line': dict(color='gray',      width=.5), 'opacity': .25},
	'old_segs':   {'line': dict(color='gray',      width=1)},
	'to_print':   {'line': dict(color='green',     width=.5), 'opacity': .25},
	'avoid_segs': {'line': dict(color='firebrick', width=1)},
	'isec_segs':  {'line': dict(color='orange',    width=1)},
}


styles_paper = deep_update(styles_dark, {
    'gc_segs':         {'line':   dict(width=2)},
    'to_print':        {'line':   dict(color='#1192e8', dash='dot'), 'opacity': 1},
    'future_thread':   {'line':   dict(color='#b28600', width=2, dash='dot')},
    'thread_ring':     {'line':   dict(color='#b28600', width=3, dash='dash')},
    'printed_thread':  {'line':   dict(color='#b28600', width=3, dash=None)},
    'anchor':          {'marker': dict(symbol='circle', size=6)},
    'original_thread': {'line':   dict(color='gray', width=2, dash='dot')},
    'original_anchor': {'marker': dict(color='gray', symbol='circle', size=6)},
    'next_anchor':     {'marker': dict(symbol='circle', size=6, color='white', line=dict(width=2, color='red'))},
})

styles=styles_paper
