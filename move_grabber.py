exec("""
import adsk.core, adsk.fusion
app = adsk.core.Application.get()
ui = app.userInterface
product = app.activeProduct
design = adsk.fusion.Design.cast(product)
rootComp = design.rootComponent
features = rootComp.features
bodies = adsk.core.ObjectCollection.create()
bodies.add(ui.activeSelections[0].entity)

vector1 = adsk.core.Vector3D.create(0.0, 10.0, 0.0)
vector2 = adsk.core.Vector3D.create(115.714, 180, 0)

transform = adsk.core.Matrix3D.create()
transform.setToRotateTo(vector1, vector2)

moveFeats = features.moveFeatures
moveFeatureInput = moveFeats.createInput(bodies, transform)
moveFeats.add(moveFeatureInput)
""")
