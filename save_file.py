exec("""
import adsk.core, adsk.fusion, adsk.cam, traceback

def save_view_as_png(filename_prefix):
    app = adsk.core.Application.get()
    ui = app.userInterface
    design = app.activeProduct
    viewport = app.activeViewport
    visual_styles = {
        'shaded':                       adsk.core.VisualStyles.ShadedVisualStyle,
        'shaded_with_hidden_edges':     adsk.core.VisualStyles.ShadedWithHiddenEdgesVisualStyle,
        'shaded_with_visible_edges': adsk.core.VisualStyles.ShadedWithVisibleEdgesOnlyVisualStyle,
        'wireframe':                    adsk.core.VisualStyles.WireframeVisualStyle,
        'wireframe_with_hidden_edges':  adsk.core.VisualStyles.WireframeWithHiddenEdgesVisualStyle,
        'wireframe_with_visible_edges': adsk.core.VisualStyles.WireframeWithVisibleEdgesOnlyVisualStyle
    }

    for style_name, visual_style in visual_styles.items():
        viewport.visualStyle = visual_style
        #app.executeTextCommand('ViewFit')
        filepath = f'{filename_prefix}-{style_name}.png'
        viewport.saveAsImageFile(filepath, 3200, 1359)

#save_view_as_png('/tmp/robot')
""")
