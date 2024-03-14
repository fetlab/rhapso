; FLAVOR:Marlin
; TIME:15
; Filament used: 0.00625769m
; Layer height: 0.4
; MINX:10.2
; MINY:10.2
; MINZ:0.2
; MAXX:33.8
; MAXY:33.8
; MAXZ:0.2
; Generated with Cura_SteamEngine 5.4.0
M82 ; absolute extrusion mode
; Ender 3 Custom Start G-code
G92 E0 ; Reset Extruder
G28 X Y Z ; Home only X, Y, and Z axes, but avoid trying to home A
M104 S175 ; Start heating up the nozzle most of the way
M190 S60 ; Start heating the bed, wait until target temperature reached
M109 S200 ; Finish heating the nozzle
G92 A90 ; Assume the ring has been manually homed, set its position to 90°
M92 A52.3977 ; Set fractional steps/unit for ring moves
G0 F5000 X55.0 ; Move head out of the way of the carrier
G0 F5000 A14.891 ; Move ring to initial thread position (🧵H({ 17.00,   0.00,   0.00}, ↗ 90.00° (  0.00,   1.00,   0.00)),  ⃘104.891°)
; --- Printer state ---
; Ring(104.891°, ⌀186 → { 17.00,  80.68,   0.00}, ⊙{ 40.90,  -9.20,   0.00})
; Bed(0, 0, ⚓︎{-21.50,   0.00,   0.00})
; Carrier: { 17.00,  80.68,   0.00}
; Print head: {  0.00,   0.00,   0.00}
G1 Z2.0 F3000 ; Move Z Axis up little to prevent scratching of Heat Bed
G1 X0.1 Y20 Z0.3 F5000.0 ; Movetype:|None|
G1 X0.1 Y200.0 Z0.3 F1500.0 E15 ; Movetype:|None|
G1 X0.4 Y200.0 Z0.3 F5000.0 ; Movetype:|None|
G1 X0.4 Y20 Z0.3 F1500.0 E30 ; Movetype:|None|
G92 E0 ; Reset Extruder
G1 Z2.0 F3000 ; Move Z Axis up little to prevent scratching of Heat Bed
G1 X5 Y20 Z0.3 F5000.0 ; Movetype:|None|
G92 E0
G92 E0
G1 F1500 E-6.5
; LAYER_COUNT:1
; LAYER:0
M107
; MESH:Body1.3mf
G1 F1500 E-13.0
G91 ; Relative positioning
G1 E-14.75769 F2700 ; Retract a bit
G1 E-14.75769 Z0.2 F2400 ; Retract and raise Z
G1 X5 Y5 F3000 ; Movetype:|None|
G1 Z10 ; Raise Z more
; G90 ;Absolute positioning; Drop G90 to avoid ring being absolutely positioned

G1 X0 Y200.0 ; Movetype:|None|
M106 S0 ; Turn-off fan
M104 S0 ; Turn-off hotend
M140 S0 ; Turn-off bed

M84 X Y E ; Disable all steppers but Z

M82 ; absolute extrusion mode
; End of Gcode
; SETTING_3 {"global_quality": "[general]\\nversion = 4\\nname = Standard Quality
; SETTING_3  #2\\ndefinition = creality_ender3pro\\n\\n[metadata]\\ntype = qualit
; SETTING_3 y_changes\\nquality_type = standard\\nsetting_version = 22\\n\\n[valu
; SETTING_3 es]\\nadhesion_type = none\\nlayer_height = 0.4\\n\\n", "extruder_qua
; SETTING_3 lity": ["[general]\\nversion = 4\\nname = Standard Quality #2\\ndefin
; SETTING_3 ition = creality_ender3pro\\n\\n[metadata]\\ntype = quality_changes\\
; SETTING_3 nquality_type = standard\\nsetting_version = 22\\nposition = 0\\n\\n[
; SETTING_3 values]\\nbottom_layers = 0\\ninfill_angles = [135 ]\\ninfill_line_di
; SETTING_3 stance = 6.0\\ninfill_pattern = lines\\ntop_layers = 0\\nwall_line_co
; SETTING_3 unt = 1\\n\\n"]}
