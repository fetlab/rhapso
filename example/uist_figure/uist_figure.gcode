;FLAVOR:Marlin
;TIME:17
;Filament used: 0.00726546m
;Layer height: 0.4
;MINX:10.2
;MINY:10.2
;MINZ:0.2
;MAXX:33.8
;MAXY:33.8
;MAXZ:0.2
;Generated with Cura_SteamEngine 5.4.0
M82 ;absolute extrusion mode
; Ender 3 Custom Start G-code
G92 E0 ; Reset Extruder
G28 ; Home all axes
M104 S175 ; Start heating up the nozzle most of the way
M190 S60 ; Start heating the bed, wait until target temperature reached
M109 S200 ; Finish heating the nozzle
G1 Z2.0 F3000 ; Move Z Axis up little to prevent scratching of Heat Bed
G1 X0.1 Y20 Z0.3 F5000.0 ; Move to start position
G1 X0.1 Y200.0 Z0.3 F1500.0 E15 ; Draw the first line
G1 X0.4 Y200.0 Z0.3 F5000.0 ; Move to side a little
G1 X0.4 Y20 Z0.3 F1500.0 E30 ; Draw the second line
G92 E0 ; Reset Extruder
G1 Z2.0 F3000 ; Move Z Axis up little to prevent scratching of Heat Bed
G1 X5 Y20 Z0.3 F5000.0 ; Move over to prevent blob squish
G92 E0
G92 E0
G1 F1500 E-6.5
;LAYER_COUNT:1
;LAYER:0
M107
;MESH:Body1.3mf
G0 F6000 X33.8 Y33.8 Z0.2
;TYPE:WALL-OUTER
G1 F1500 E0
G1 F1200 X10.2 Y33.8 E0.78494
G1 X10.2 Y10.2 E1.56988
G1 X33.8 Y10.2 E2.35482
G1 X33.8 Y33.8 E3.13976
;TYPE:FILL
G1 X33.719 Y33.719
G1 X10.279 Y10.279 E4.2423
G0 F6000 X10.87 Y10.87
G0 X10.9 Y16.643
G0 X10.279 Y16.643
G1 F1200 X27.355 Y33.719 E5.04551
G0 F6000 X27.355 Y33.1
G0 X20.991 Y33.1
G0 X20.991 Y33.719
G1 F1200 X10.279 Y23.007 E5.54936
G0 F6000 X10.9 Y23.007
G0 X10.9 Y29.371
G0 X10.279 Y29.371
G1 F1200 X14.627 Y33.719 E5.75388
G0 F6000 X14.627 Y33.1
G0 X33.1 Y27.355
G0 X33.719 Y27.355
G1 F1200 X16.643 Y10.279 E6.55708
G0 F6000 X16.643 Y10.9
G0 X23.007 Y10.9
G0 X23.007 Y10.279
G1 F1200 X33.719 Y20.991 E7.06094
G0 F6000 X33.1 Y20.991
G0 X33.1 Y14.627
G0 X33.719 Y14.627
G1 F1200 X29.371 Y10.279 E7.26546
G0 F6000 X29.371 Y11.2
;TIME_ELAPSED:17.759600
G1 F1500 E0.76546
G91 ;Relative positioning
G1 E-2 F2700 ;Retract a bit
G1 E-2 Z0.2 F2400 ;Retract and raise Z
G1 X5 Y5 F3000 ;Wipe out
G1 Z10 ;Raise Z more
G90 ;Absolute positioning

G1 X0 Y200.0 ;Present print
M106 S0 ;Turn-off fan
M104 S0 ;Turn-off hotend
M140 S0 ;Turn-off bed

M84 X Y E ;Disable all steppers but Z

M82 ;absolute extrusion mode
;End of Gcode
;SETTING_3 {"global_quality": "[general]\\nversion = 4\\nname = Standard Quality
;SETTING_3  #2\\ndefinition = creality_ender3pro\\n\\n[metadata]\\ntype = qualit
;SETTING_3 y_changes\\nquality_type = standard\\nsetting_version = 22\\n\\n[valu
;SETTING_3 es]\\nadhesion_type = none\\nlayer_height = 0.4\\n\\n", "extruder_qua
;SETTING_3 lity": ["[general]\\nversion = 4\\nname = Standard Quality #2\\ndefin
;SETTING_3 ition = creality_ender3pro\\n\\n[metadata]\\ntype = quality_changes\\
;SETTING_3 nquality_type = standard\\nsetting_version = 22\\nposition = 0\\n\\n[
;SETTING_3 values]\\nbottom_layers = 0\\ninfill_line_distance = 4.5\\ninfill_pat
;SETTING_3 tern = lines\\ntop_layers = 0\\nwall_line_count = 1\\n\\n"]}
