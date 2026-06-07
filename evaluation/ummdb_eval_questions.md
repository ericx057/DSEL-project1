# UMMDB Evaluation Questions — FreeCAD Retrieval Benchmark

**Total**: 250 questions (5 seeds × 50)
**Target repo**: FreeCAD (C++ / Python)
**Metric baselines**: Accuracy@5 ≥ 0.95, MRR ≥ 0.95
**Generalization note**: Each seed uses an orthogonal question pattern so that
retrieval tuning for one pattern does not artificially inflate scores on the
others. Questions span call-chains, property propagation, class hierarchy,
serialization, and algorithmic internals.

## Seed Index

| Seed | rng | Theme | Questions |
|------|-----|-------|-----------|
| 1 | 42  | Call-chain tracing | Q1–Q50 |
| 2 | 137 | Event/property propagation | Q51–Q100 |
| 3 | 271 | Class hierarchy & interface | Q101–Q150 |
| 4 | 314 | Serialization & file I/O | Q151–Q200 |
| 5 | 500 | Algorithm internals | Q201–Q250 |

---

## Seed 1 — Call-Chain Tracing (rng=42)

### Q1
**Query**: When `SketchObject::solve` is called, which function in `Sketch.cpp` does it delegate the actual GCS solving to?
**Expected files**:
- `src/Mod/Sketcher/App/SketchObject.cpp`
- `src/Mod/Sketcher/App/Sketch.cpp`
**Hops**: SketchObject::solve → Sketch::solve
**Difficulty**: 1

### Q2
**Query**: How does `Sketch::solve` invoke the GCS Dog-Leg solver `solve_DL` inside `GCS.cpp`?
**Expected files**:
- `src/Mod/Sketcher/App/Sketch.cpp`
- `src/Mod/Sketcher/App/planegcs/GCS.cpp`
**Hops**: Sketch::solve → GCS::solve → GCS::solve_DL
**Difficulty**: 2

### Q3
**Query**: What call chain connects `Boolean::execute` in `FeatureBoolean.cpp` to `TopoShape::makeBoolean`?
**Expected files**:
- `src/Mod/Part/App/FeatureBoolean.cpp`
- `src/Mod/Part/App/TopoShape.cpp`
**Hops**: Boolean::execute → TopoShape::makeBoolean
**Difficulty**: 1

### Q4
**Query**: How does `Feature::execute` in `PartFeature.cpp` store the computed shape via `Shape.setValue`?
**Expected files**:
- `src/Mod/Part/App/PartFeature.cpp`
- `src/Mod/Part/App/TopoShape.cpp`
**Hops**: Feature::execute → Shape.setValue → TopoShape
**Difficulty**: 1

### Q5
**Query**: Trace the call from `Document::save` in `Document.cpp` through `Persistence::save` to `XMLWriter`.
**Expected files**:
- `src/App/Document.cpp`
- `src/Base/Persistence.cpp`
- `src/Base/XMLWriter.cpp`
**Hops**: Document::save → Persistence::save → XMLWriter::writeElement
**Difficulty**: 2

### Q6
**Query**: How does `Extrusion::execute` in `FeatureExtrusion.cpp` call the OCCT `BRepPrimAPI_MakePrism` to produce the extruded shape?
**Expected files**:
- `src/Mod/Part/App/FeatureExtrusion.cpp`
- `src/Mod/Part/App/TopoShape.cpp`
**Hops**: Extrusion::execute → BRepPrimAPI_MakePrism → TopoShape
**Difficulty**: 1

### Q7
**Query**: What does `Command::invoke` in `Command.cpp` call to run the command through the `CommandManager`?
**Expected files**:
- `src/Gui/Command.cpp`
- `src/Gui/Application.cpp`
**Hops**: Command::invoke → CommandManager::runCommandByName → Application
**Difficulty**: 1

### Q8
**Query**: When `ViewProviderSketch::updateData` detects a geometry change, which draw function is called first?
**Expected files**:
- `src/Mod/Sketcher/Gui/ViewProviderSketch.cpp`
- `src/Mod/Sketcher/App/SketchObject.cpp`
**Hops**: ViewProviderSketch::updateData → draw → drawConstraints
**Difficulty**: 1

### Q9
**Query**: How does `Sketch::initMove` in `Sketch.cpp` register constraints with `GCSsys` inside `GCS.cpp`?
**Expected files**:
- `src/Mod/Sketcher/App/Sketch.cpp`
- `src/Mod/Sketcher/App/planegcs/GCS.cpp`
**Hops**: Sketch::initMove → GCSsys.addConstraintsToGCS → GCS
**Difficulty**: 2

### Q10
**Query**: Trace the full call from `Application::open` in `Gui/Application.cpp` through `App::Application::openDocument` to `Document::restore`.
**Expected files**:
- `src/Gui/Application.cpp`
- `src/App/Application.cpp`
- `src/App/Document.cpp`
**Hops**: Gui::Application::open → App::Application::openDocument → Document::restore
**Difficulty**: 2

### Q11
**Query**: How does `FemAnalysis::run` locate `FemSolver` objects and call `solve` on each of them?
**Expected files**:
- `src/Mod/FEM/App/FemAnalysis.cpp`
- `src/Mod/FEM/App/FemMesh.cpp`
**Hops**: FemAnalysis::run → getSolvers → FemSolver::solve
**Difficulty**: 2

### Q12
**Query**: What function in `DrawViewPart.cpp` ultimately calls `HLRBRep_Algo` to compute hidden-line removal?
**Expected files**:
- `src/Mod/TechDraw/App/DrawViewPart.cpp`
- `src/Mod/TechDraw/App/DrawPage.cpp`
**Hops**: DrawViewPart::execute → HLRBRep_Algo::Add → HLRBRep_HLRToShape
**Difficulty**: 2

### Q13
**Query**: How does `Area::build` in `Area.cpp` pass clipper paths to the underlying `myArea` object?
**Expected files**:
- `src/Mod/Path/App/Area.cpp`
**Hops**: Area::build → toClipperPaths → myArea.add
**Difficulty**: 1

### Q14
**Query**: When `DocumentObject::onChanged` fires, which Document-level signal is emitted next?
**Expected files**:
- `src/App/DocumentObject.cpp`
- `src/App/Document.cpp`
**Hops**: DocumentObject::onChanged → Document::signalChangedObject
**Difficulty**: 1

### Q15
**Query**: How does `CmdSketcherConstrainCoincident::activated` in `CommandSketcherTools.cpp` ultimately call `SketchObject::addConstraint`?
**Expected files**:
- `src/Mod/Sketcher/Gui/CommandSketcherTools.cpp`
- `src/Mod/Sketcher/App/SketchObject.cpp`
**Hops**: activated → cmdAppObjectArgs → addConstraint
**Difficulty**: 2

### Q16
**Query**: What happens when `DrawPage::addView` calls `requestPaint` — which signal is emitted?
**Expected files**:
- `src/Mod/TechDraw/App/DrawPage.cpp`
**Hops**: addView → requestPaint → signalGuiPaint
**Difficulty**: 1

### Q17
**Query**: How does `PropertyContainer::addProperty` set the container on the property object?
**Expected files**:
- `src/App/PropertyContainer.cpp`
**Hops**: addProperty → prop->setContainer(this)
**Difficulty**: 1

### Q18
**Query**: Trace the call from `Document::openTransaction` to `_pActiveUndoTransaction` creation.
**Expected files**:
- `src/App/Document.cpp`
- `src/Gui/Document.cpp`
**Hops**: Gui::Document::openCommand → App::Document::openTransaction → Transaction
**Difficulty**: 2

### Q19
**Query**: How does `PropertyLinkSub::setValue` notify observers via `hasSetValue`?
**Expected files**:
- `src/App/PropertyLinks.cpp`
- `src/App/PropertyContainer.cpp`
**Hops**: PropertyLinkSub::setValue → hasSetValue → PropertyContainer::onChanged
**Difficulty**: 2

### Q20
**Query**: When `SelectionSingleton::addSelection` succeeds, which signal is fired to notify observers?
**Expected files**:
- `src/Gui/Selection.cpp`
**Hops**: addSelection → notify → signalSelectionChanged
**Difficulty**: 1

### Q21
**Query**: How does `Revolution::execute` in `FeatureRevolution.cpp` build the revolved solid using OCCT?
**Expected files**:
- `src/Mod/Part/App/FeatureRevolution.cpp`
- `src/Mod/Part/App/TopoShape.cpp`
**Hops**: Revolution::execute → BRepPrimAPI_MakeRevol → TopoShape
**Difficulty**: 1

### Q22
**Query**: Trace the chain: `ViewProviderSketch::updateData` → `draw` → `drawConstraints` in `ViewProviderSketch.cpp`.
**Expected files**:
- `src/Mod/Sketcher/Gui/ViewProviderSketch.cpp`
**Hops**: updateData → draw → drawConstraints
**Difficulty**: 1

### Q23
**Query**: How does `SketchObject::addConstraint` propagate back to re-solve the sketch?
**Expected files**:
- `src/Mod/Sketcher/App/SketchObject.cpp`
- `src/Mod/Sketcher/App/Sketch.cpp`
**Hops**: addConstraint → solve → Sketch::solve
**Difficulty**: 2

### Q24
**Query**: When `GCS::solve_LM` runs the Levenberg-Marquardt loop, which `SubSystem` function builds the Jacobian?
**Expected files**:
- `src/Mod/Sketcher/App/planegcs/GCS.cpp`
- `src/Mod/Sketcher/App/planegcs/SubSystem.cpp`
**Hops**: GCS::solve_LM → subsystem->calcJacobian → SubSystem::calcJacobian
**Difficulty**: 2

### Q25
**Query**: How does `TaskFemConstraint::onSelectionChanged` in `TaskFemConstraint.cpp` call `setReference`?
**Expected files**:
- `src/Mod/FEM/Gui/TaskFemConstraint.cpp`
**Hops**: onSelectionChanged → setReference
**Difficulty**: 1

### Q26
**Query**: What does `SubSystem::error` compute and which `Constraint` function does it call?
**Expected files**:
- `src/Mod/Sketcher/App/planegcs/SubSystem.cpp`
- `src/Mod/Sketcher/App/planegcs/Constraints.h`
**Hops**: SubSystem::error → Constraint::error
**Difficulty**: 1

### Q27
**Query**: How does `ViewProvider::setVisible` in `ViewProvider.cpp` interact with the Inventor scene graph node?
**Expected files**:
- `src/Gui/ViewProvider.cpp`
**Hops**: setVisible → Visibility.setValue → pcRoot->whichChild
**Difficulty**: 1

### Q28
**Query**: Trace `Application::newDocument` in `App/Application.cpp` to the call that emits `signalNewDocument`.
**Expected files**:
- `src/App/Application.cpp`
- `src/App/Document.cpp`
**Hops**: Application::newDocument → DocMap[name] = doc → signalNewDocument
**Difficulty**: 1

### Q29
**Query**: How does `FemMesh::read` in `FemMesh.cpp` invoke `SMESH_Reader::read`?
**Expected files**:
- `src/Mod/FEM/App/FemMesh.cpp`
**Hops**: FemMesh::read → SMESH_Reader.read → updateSMESH
**Difficulty**: 1

### Q30
**Query**: What call chain connects `DocumentObject::touch` to the `StatusBits` mutation?
**Expected files**:
- `src/App/DocumentObject.cpp`
- `src/App/DocumentObject.h`
**Hops**: touch → StatusBits.set(ObjectStatus::Touch)
**Difficulty**: 1

### Q31
**Query**: How does `Persistence::restore` in `Persistence.cpp` locate properties by name using `getPropertyByName`?
**Expected files**:
- `src/Base/Persistence.cpp`
- `src/App/PropertyContainer.cpp`
**Hops**: Persistence::restore → getPropertyByName → propertyMap.find
**Difficulty**: 2

### Q32
**Query**: What function does `SubSystem::fillParams` call to populate the Eigen vector from constraint parameters?
**Expected files**:
- `src/Mod/Sketcher/App/planegcs/SubSystem.cpp`
**Hops**: fillParams → x.resize → *params[i]
**Difficulty**: 1

### Q33
**Query**: When `Document::commitTransaction` is called from `Gui::Document::commitCommand`, what App-level function is invoked?
**Expected files**:
- `src/Gui/Document.cpp`
- `src/App/Document.cpp`
**Hops**: Gui::Document::commitCommand → App::Document::commitTransaction
**Difficulty**: 1

### Q34
**Query**: How does `SelectionView::onSelectionChanged` in `SelectionView.cpp` add items to the selection list widget?
**Expected files**:
- `src/Gui/SelectionView.cpp`
- `src/Gui/Selection.cpp`
**Hops**: onSelectionChanged → AddSelection → selectionList->addItem
**Difficulty**: 1

### Q35
**Query**: Trace `Area::setParams` through `build` to the `myArea.add` call in `Area.cpp`.
**Expected files**:
- `src/Mod/Path/App/Area.cpp`
**Hops**: setParams → build → myArea.add
**Difficulty**: 1

### Q36
**Query**: When `FeatureBoolean::execute` computes a Boolean cut, which `TopoShape::makeBoolean` overload is chosen?
**Expected files**:
- `src/Mod/Part/App/FeatureBoolean.cpp`
- `src/Mod/Part/App/TopoShape.cpp`
**Hops**: Boolean::execute → BoolCut branch → makeBoolean(BoolCut)
**Difficulty**: 1

### Q37
**Query**: How does `GCS::getRedundant` detect linearly dependent constraints using Eigen's `FullPivLU`?
**Expected files**:
- `src/Mod/Sketcher/App/planegcs/GCS.cpp`
**Hops**: getRedundant → FullPivLU(jacobianMatrix) → redundant list
**Difficulty**: 2

### Q38
**Query**: What chain of calls connects `Sketch::handleRedundantConstraints` to `conflictingConstraintIndices`?
**Expected files**:
- `src/Mod/Sketcher/App/Sketch.cpp`
**Hops**: handleRedundantConstraints → conflictingConstraintIndices.push_back
**Difficulty**: 1

### Q39
**Query**: How does `Application::setActiveDocument` notify the GUI via `signalActiveDocument`?
**Expected files**:
- `src/App/Application.cpp`
- `src/App/Document.cpp`
**Hops**: setActiveDocument → ActiveDoc = doc → signalActiveDocument
**Difficulty**: 1

### Q40
**Query**: Trace `PyObjectBase::getattr` through `PyObject_GenericGetAttr` in `PyObjectBase.cpp`.
**Expected files**:
- `src/Base/PyObjectBase.cpp`
**Hops**: getattr → PyObject_GenericGetAttr
**Difficulty**: 1

### Q41
**Query**: When `ViewProvider::update` is called with a property change, which virtual function dispatches it?
**Expected files**:
- `src/Gui/ViewProvider.cpp`
- `src/Gui/ViewProvider.h`
**Hops**: update → onChanged(prop)
**Difficulty**: 1

### Q42
**Query**: How does `FemAnalysis::getSolvers` filter `DocumentObject` children by `FemSolver` class type?
**Expected files**:
- `src/Mod/FEM/App/FemAnalysis.cpp`
**Hops**: getSolvers → isDerivedFrom(FemSolver::getClassTypeId)
**Difficulty**: 1

### Q43
**Query**: What function does `XMLWriter::writeElement` call to escape XML special characters?
**Expected files**:
- `src/Base/XMLWriter.cpp`
**Hops**: writeElement → encodeXML
**Difficulty**: 1

### Q44
**Query**: How does `PropertyContainer::onChanged` iterate connections to notify observers?
**Expected files**:
- `src/App/PropertyContainer.cpp`
**Hops**: onChanged → connections loop → conn.second(prop)
**Difficulty**: 1

### Q45
**Query**: Trace the call from `Sketch::getRedundant` to `GCS::getRedundant` in `GCS.cpp`.
**Expected files**:
- `src/Mod/Sketcher/App/Sketch.cpp`
- `src/Mod/Sketcher/App/planegcs/GCS.cpp`
**Hops**: Sketch::getRedundant → GCSsys.getRedundant → GCS::getRedundant
**Difficulty**: 2

### Q46
**Query**: What happens inside `TopoShape::write` when it serializes a shape to a `Base::Writer`?
**Expected files**:
- `src/Mod/Part/App/TopoShape.cpp`
- `src/Base/Writer.cpp`
**Hops**: TopoShape::write → BRepTools::Write → Writer::Stream
**Difficulty**: 2

### Q47
**Query**: How does `Writer::incInd` and `Writer::decInd` manage XML indentation in `Writer.cpp`?
**Expected files**:
- `src/Base/Writer.cpp`
**Hops**: incInd → indentation += "  " / decInd → indentation.resize
**Difficulty**: 1

### Q48
**Query**: Trace `DocumentObject::purgeTouched` to the `StatusBits.reset` call.
**Expected files**:
- `src/App/DocumentObject.cpp`
**Hops**: purgeTouched → StatusBits.reset(ObjectStatus::Touch)
**Difficulty**: 1

### Q49
**Query**: How does `Gui::Document::undo` in `Document.cpp` call `App::Document::undo`?
**Expected files**:
- `src/Gui/Document.cpp`
- `src/App/Document.cpp`
**Hops**: Gui::Document::undo → getAppDocument()->undo → signalUndoDocument
**Difficulty**: 1

### Q50
**Query**: What function in `SketchObject.cpp` calls `detectRedundant` to get the list of conflicting constraint indices?
**Expected files**:
- `src/Mod/Sketcher/App/SketchObject.cpp`
- `src/Mod/Sketcher/App/Sketch.cpp`
**Hops**: SketchObject::detectRedundant → Sketch::solve → GCS::getRedundant
**Difficulty**: 2

---

## Seed 2 — Event/Property Propagation (rng=137)

### Q51
**Query**: When a geometry property changes in `SketchObject`, how does the change propagate to `ViewProviderSketch::updateData`?
**Expected files**:
- `src/Mod/Sketcher/App/SketchObject.cpp`
- `src/Mod/Sketcher/Gui/ViewProviderSketch.cpp`
**Hops**: Geometry change → signalConstraintsChanged → ViewProviderSketch::updateData
**Difficulty**: 2

### Q52
**Query**: How does a `DocumentObject::onChanged` call eventually reach `Document::signalChangedObject`?
**Expected files**:
- `src/App/DocumentObject.cpp`
- `src/App/Document.cpp`
**Hops**: onChanged → getDocument()->signalChangedObject
**Difficulty**: 1

### Q53
**Query**: When `PropertyLinkSub::setValue` calls `hasSetValue`, which `PropertyContainer` method is triggered?
**Expected files**:
- `src/App/PropertyLinks.cpp`
- `src/App/PropertyContainer.cpp`
**Hops**: hasSetValue → PropertyContainer::onChanged
**Difficulty**: 1

### Q54
**Query**: How does a selection event in `SelectionSingleton::addSelection` reach `SelectionView::onSelectionChanged`?
**Expected files**:
- `src/Gui/Selection.cpp`
- `src/Gui/SelectionView.cpp`
**Hops**: addSelection → signalSelectionChanged → onSelectionChanged
**Difficulty**: 2

### Q55
**Query**: When the `Visibility` property changes in `ViewProvider::onChanged`, how is the scene graph updated?
**Expected files**:
- `src/Gui/ViewProvider.cpp`
**Hops**: onChanged → setVisible → pcRoot->whichChild
**Difficulty**: 1

### Q56
**Query**: How does `SketchObject::solve` propagate solver failure back via `signalConstraintsChanged`?
**Expected files**:
- `src/Mod/Sketcher/App/SketchObject.cpp`
**Hops**: solve → GCS::Failed branch → signalConstraintsChanged
**Difficulty**: 1

### Q57
**Query**: When `Application::setActiveDocument` is called, how does the GUI receive the active document change?
**Expected files**:
- `src/App/Application.cpp`
- `src/Gui/Application.cpp`
**Hops**: App::Application::setActiveDocument → signalActiveDocument → Gui::Application
**Difficulty**: 2

### Q58
**Query**: How does a new document created via `Application::newDocument` trigger `signalNewDocument`?
**Expected files**:
- `src/App/Application.cpp`
- `src/App/Document.cpp`
**Hops**: newDocument → DocMap insertion → signalNewDocument
**Difficulty**: 1

### Q59
**Query**: When `Document::setModified` is called, which signal notifies observers?
**Expected files**:
- `src/App/Document.cpp`
**Hops**: setModified → signalChanged
**Difficulty**: 1

### Q60
**Query**: How does `FemAnalysis::addObject` propagate the new child to the `Group` property?
**Expected files**:
- `src/Mod/FEM/App/FemAnalysis.cpp`
- `src/App/PropertyLinks.cpp`
**Hops**: addObject → Group.setValues → PropertyLinkSub::setLinks
**Difficulty**: 2

### Q61
**Query**: What event does `DrawPage::requestPaint` emit to trigger a GUI repaint?
**Expected files**:
- `src/Mod/TechDraw/App/DrawPage.cpp`
**Hops**: requestPaint → signalGuiPaint
**Difficulty**: 1

### Q62
**Query**: When a `ConstraintCoincident` error changes, how does `SubSystem::error` propagate to the GCS solver?
**Expected files**:
- `src/Mod/Sketcher/App/planegcs/Constraints.h`
- `src/Mod/Sketcher/App/planegcs/SubSystem.cpp`
- `src/Mod/Sketcher/App/planegcs/GCS.cpp`
**Hops**: ConstraintCoincident::error → SubSystem::error → GCS::solve_DL
**Difficulty**: 3

### Q63
**Query**: How does `Command::testActive` propagate the active state to the `Action` widget?
**Expected files**:
- `src/Gui/Command.cpp`
**Hops**: testActive → _pcAction->setEnabled(isActive())
**Difficulty**: 1

### Q64
**Query**: When `Sketch::solve` detects redundant constraints, how does the failure propagate back to `SketchObject`?
**Expected files**:
- `src/Mod/Sketcher/App/Sketch.cpp`
- `src/Mod/Sketcher/App/SketchObject.cpp`
**Hops**: Sketch::solve returns -1 → SketchObject::solve checks dofs < 0 → signalConstraintsChanged
**Difficulty**: 2

### Q65
**Query**: How does `PropertyContainer::onChanged` in `PropertyContainer.cpp` iterate its connection map?
**Expected files**:
- `src/App/PropertyContainer.cpp`
**Hops**: onChanged → for conn in connections → conn.second(prop)
**Difficulty**: 1

### Q66
**Query**: When `Area::setParams` is called, how does the change propagate through `build` to update `myArea`?
**Expected files**:
- `src/Mod/Path/App/Area.cpp`
**Hops**: setParams → build → myArea.clean → myArea.add
**Difficulty**: 1

### Q67
**Query**: How does `TaskFemConstraint::onButtonReference` react to button toggle by clearing selection?
**Expected files**:
- `src/Mod/FEM/Gui/TaskFemConstraint.cpp`
- `src/Gui/Selection.cpp`
**Hops**: onButtonReference → Gui::Selection().clearSelection → _SelList.clear
**Difficulty**: 2

### Q68
**Query**: When `ViewProviderSketch::draw` is called, how does it signal the constraint redraw to the 3D view?
**Expected files**:
- `src/Mod/Sketcher/Gui/ViewProviderSketch.cpp`
**Hops**: draw → drawConstraints → drawGeometry
**Difficulty**: 1

### Q69
**Query**: How does `GCS::applySolution` propagate solved parameters back through `SubSystem::applySolution`?
**Expected files**:
- `src/Mod/Sketcher/App/planegcs/GCS.cpp`
- `src/Mod/Sketcher/App/planegcs/SubSystem.cpp`
**Hops**: GCS::applySolution → SubSystem::applySolution
**Difficulty**: 1

### Q70
**Query**: How does a boolean operation result from `TopoShape::makeBoolean` get stored in `FeatureBoolean`?
**Expected files**:
- `src/Mod/Part/App/FeatureBoolean.cpp`
- `src/Mod/Part/App/TopoShape.cpp`
**Hops**: makeBoolean returns TopoShape → Boolean::execute → Shape.setValue(result)
**Difficulty**: 1

### Q71
**Query**: When `Document::restore` is called, how does it propagate property restoration to each `DocumentObject`?
**Expected files**:
- `src/App/Document.cpp`
- `src/Base/Persistence.cpp`
**Hops**: restore → Persistence::restore → Property::restore
**Difficulty**: 2

### Q72
**Query**: How does the `SketchObject::updateGeometry` call trigger a re-draw in `ViewProviderSketch`?
**Expected files**:
- `src/Mod/Sketcher/App/SketchObject.cpp`
- `src/Mod/Sketcher/Gui/ViewProviderSketch.cpp`
**Hops**: updateGeometry → Geometry property change → updateData
**Difficulty**: 2

### Q73
**Query**: When `SelectionSingleton::clearSelection` fires, how does `SelectionView` react?
**Expected files**:
- `src/Gui/Selection.cpp`
- `src/Gui/SelectionView.cpp`
**Hops**: clearSelection → signalSelectionChanged(ClrSelection) → selectionList->clear
**Difficulty**: 2

### Q74
**Query**: How does `XMLReader::readElement` advance the XML parser to the next matching element?
**Expected files**:
- `src/Base/XMLReader.cpp`
**Hops**: readElement → while !isStartElement → reader.next
**Difficulty**: 1

### Q75
**Query**: When `FeatureExtrusion::execute` sets `Shape.setValue`, how is the property change propagated?
**Expected files**:
- `src/Mod/Part/App/FeatureExtrusion.cpp`
- `src/App/PropertyContainer.cpp`
**Hops**: Shape.setValue → PropertyContainer::onChanged → observer notification
**Difficulty**: 2

### Q76
**Query**: How does `Gui::Document::openCommand` propagate to `App::Document::openTransaction`?
**Expected files**:
- `src/Gui/Document.cpp`
- `src/App/Document.cpp`
**Hops**: openCommand → getAppDocument()->openTransaction
**Difficulty**: 1

### Q77
**Query**: When `SketchObject::addConstraint` inserts a constraint, how does the Constraints property notify observers?
**Expected files**:
- `src/Mod/Sketcher/App/SketchObject.cpp`
- `src/App/PropertyContainer.cpp`
**Hops**: Constraints.insert → PropertyContainer::onChanged → solve
**Difficulty**: 2

### Q78
**Query**: How does a property change in `Feature::execute` propagate through `Shape.setValue` to dependent objects?
**Expected files**:
- `src/Mod/Part/App/PartFeature.cpp`
- `src/App/PropertyContainer.cpp`
**Hops**: Shape.setValue → onChanged → dependent feature recompute
**Difficulty**: 2

### Q79
**Query**: When `DrawViewPart::execute` updates edges, how does `DrawPage::requestPaint` receive the update signal?
**Expected files**:
- `src/Mod/TechDraw/App/DrawViewPart.cpp`
- `src/Mod/TechDraw/App/DrawPage.cpp`
**Hops**: execute → property change → DrawPage::requestPaint → signalGuiPaint
**Difficulty**: 2

### Q80
**Query**: How does `ViewProvider::attach` invoke `onAttach` to let subclasses react?
**Expected files**:
- `src/Gui/ViewProvider.cpp`
**Hops**: attach → pcObject = obj → onAttach(obj)
**Difficulty**: 1

### Q81
**Query**: When `GCS::clear` is called, how does it reset the parameter and constraint lists?
**Expected files**:
- `src/Mod/Sketcher/App/planegcs/GCS.cpp`
**Hops**: clear → params.clear → constraints.clear → subSystems.clear
**Difficulty**: 1

### Q82
**Query**: How does `FemMesh::write` propagate mesh data to `SMESH_Writer`?
**Expected files**:
- `src/Mod/FEM/App/FemMesh.cpp`
**Hops**: write → SMESH_Writer.write(myMesh)
**Difficulty**: 1

### Q83
**Query**: When `PyObjectBase::setCustomAttributes` is overridden, how does attribute setting reach the C++ layer?
**Expected files**:
- `src/Base/PyObjectBase.cpp`
**Hops**: setattr → setCustomAttributes → C++ property
**Difficulty**: 2

### Q84
**Query**: How does `Application::updateActions` notify all registered commands of an action state change?
**Expected files**:
- `src/Gui/Application.cpp`
- `src/Gui/Command.cpp`
**Hops**: updateActions → getAllCommands → cmd->testActive
**Difficulty**: 1

### Q85
**Query**: When `PropertyLinkSub::setLinks` fires `hasSetValue`, which container method processes the change?
**Expected files**:
- `src/App/PropertyLinks.cpp`
- `src/App/PropertyContainer.cpp`
**Hops**: setLinks → hasSetValue → PropertyContainer::onChanged
**Difficulty**: 1

### Q86
**Query**: How does `Sketch::initMove` propagate geometry to the GCS `SubSystem`?
**Expected files**:
- `src/Mod/Sketcher/App/Sketch.cpp`
- `src/Mod/Sketcher/App/planegcs/GCS.cpp`
- `src/Mod/Sketcher/App/planegcs/SubSystem.cpp`
**Hops**: initMove → addGeometryToGCS → SubSystem params
**Difficulty**: 3

### Q87
**Query**: When `Document::undo` is called, how does the `Gui::Document` receive the undo signal?
**Expected files**:
- `src/App/Document.cpp`
- `src/Gui/Document.cpp`
**Hops**: App::Document::undo → signalUndoDocument → Gui::Document::undo
**Difficulty**: 2

### Q88
**Query**: How does `Persistence::save` iterate properties and call each one's `save` method?
**Expected files**:
- `src/Base/Persistence.cpp`
- `src/App/PropertyContainer.cpp`
**Hops**: Persistence::save → getPropertyMap → pair.second->save(writer)
**Difficulty**: 2

### Q89
**Query**: When `Area::build` processes each shape, how does `toClipperPaths` feed into `myArea.add`?
**Expected files**:
- `src/Mod/Path/App/Area.cpp`
**Hops**: build → toClipperPaths(shape, paths) → myArea.add(paths, myOp)
**Difficulty**: 1

### Q90
**Query**: How does `SubSystem::getResiduals` aggregate per-constraint errors into an Eigen vector?
**Expected files**:
- `src/Mod/Sketcher/App/planegcs/SubSystem.cpp`
- `src/Mod/Sketcher/App/planegcs/Constraints.h`
**Hops**: getResiduals → r[i] = constraints[i]->error()
**Difficulty**: 1

### Q91
**Query**: When `Revolution::execute` accesses `Source.getValue`, how is the source shape retrieved?
**Expected files**:
- `src/Mod/Part/App/FeatureRevolution.cpp`
- `src/Mod/Part/App/PartFeature.cpp`
**Hops**: Source.getValue → Part::Feature::getTopoShape
**Difficulty**: 1

### Q92
**Query**: How does `DrawPage::addView` connect the view to the page via `view->setPage`?
**Expected files**:
- `src/Mod/TechDraw/App/DrawPage.cpp`
**Hops**: addView → view->setPage(this) → requestPaint
**Difficulty**: 1

### Q93
**Query**: When `Boolean::execute` calls `base->getTopoShape()`, how does `Feature` return the cached shape?
**Expected files**:
- `src/Mod/Part/App/FeatureBoolean.cpp`
- `src/Mod/Part/App/PartFeature.cpp`
**Hops**: getTopoShape → Shape.getShape() → TopoShape
**Difficulty**: 1

### Q94
**Query**: How does `Writer::beginCharStream` and `endCharStream` bracket binary data in the XML document?
**Expected files**:
- `src/Base/Writer.cpp`
**Hops**: beginCharStream → "<CharData>" → endCharStream → "</CharData>"
**Difficulty**: 1

### Q95
**Query**: When `CommandSketcherTools::activated` calls `commitCommand`, how does the undo stack get updated?
**Expected files**:
- `src/Mod/Sketcher/Gui/CommandSketcherTools.cpp`
- `src/Gui/Document.cpp`
- `src/App/Document.cpp`
**Hops**: commitCommand → Gui::Document → App::Document::commitTransaction
**Difficulty**: 3

### Q96
**Query**: How does `ViewProvider::onChanged` respond specifically to a `Visibility` property update?
**Expected files**:
- `src/Gui/ViewProvider.cpp`
**Hops**: onChanged → if prop == &Visibility → setVisible
**Difficulty**: 1

### Q97
**Query**: When `Persistence::restore` calls `prop->restore(reader)`, what reader method is used to get attribute values?
**Expected files**:
- `src/Base/Persistence.cpp`
- `src/Base/XMLReader.cpp`
**Hops**: prop->restore → XMLReader::readElement → getAttribute
**Difficulty**: 2

### Q98
**Query**: How does `GCS::dofsNumber` compute degrees of freedom accounting for redundant constraints?
**Expected files**:
- `src/Mod/Sketcher/App/planegcs/GCS.cpp`
**Hops**: dofsNumber → params.size - constraints.size + redundantCount
**Difficulty**: 1

### Q99
**Query**: When `FileInfo::extension` is called, how does it extract the file extension from the full path?
**Expected files**:
- `src/Base/FileInfo.cpp`
**Hops**: extension → rfind('.') → substr(pos+1)
**Difficulty**: 1

### Q100
**Query**: How does `SelectionView::setMode` in `SelectionView.cpp` reset the preselection in `Gui::Selection`?
**Expected files**:
- `src/Gui/SelectionView.cpp`
- `src/Gui/Selection.cpp`
**Hops**: setMode → Gui::Selection().setPreselect(nullptr, ...)
**Difficulty**: 1

---

## Seed 3 — Class Hierarchy & Interface (rng=271)

### Q101
**Query**: Which class does `SketchObject` inherit from, and where is that base class defined?
**Expected files**:
- `src/Mod/Sketcher/App/SketchObject.h`
- `src/Mod/Part/App/PartFeature.h`
**Hops**: SketchObject → Part2DObject → Feature
**Difficulty**: 1

### Q102
**Query**: What is the inheritance chain from `PropertyContainer` up to `Base::Persistence`?
**Expected files**:
- `src/App/PropertyContainer.h`
- `src/Base/Persistence.cpp`
**Hops**: PropertyContainer inherits Persistence → Persistence defines save/restore
**Difficulty**: 1

### Q103
**Query**: Which class does `Document` inherit from, and which property management interface does it gain?
**Expected files**:
- `src/App/Document.h`
- `src/App/PropertyContainer.h`
**Hops**: Document → PropertyContainer → property management
**Difficulty**: 1

### Q104
**Query**: Where is the `ViewProvider` base class defined and which virtual methods must subclasses implement?
**Expected files**:
- `src/Gui/ViewProvider.h`
- `src/Gui/ViewProvider.cpp`
**Hops**: ViewProvider → attach, update, onChanged virtuals
**Difficulty**: 1

### Q105
**Query**: How does `DocumentObject` inherit from `PropertyContainer` and what interface does that give it?
**Expected files**:
- `src/App/DocumentObject.h`
- `src/App/PropertyContainer.h`
**Hops**: DocumentObject → PropertyContainer → addProperty, getPropertyByName
**Difficulty**: 1

### Q106
**Query**: Where is the `Constraint` base class defined in the planegcs system, and which pure virtual methods must subclasses override?
**Expected files**:
- `src/Mod/Sketcher/App/planegcs/Constraints.h`
**Hops**: Constraint → error(), grad() pure virtuals → ConstraintCoincident, ConstraintParallel
**Difficulty**: 1

### Q107
**Query**: Which concrete classes implement the `Constraint` interface in `Constraints.h`?
**Expected files**:
- `src/Mod/Sketcher/App/planegcs/Constraints.h`
**Hops**: Constraint → ConstraintCoincident, ConstraintParallel, ConstraintPerpendicular, ConstraintDistance
**Difficulty**: 1

### Q108
**Query**: How does `FemMesh` inherit from `App::GeoFeature` and what does that give it?
**Expected files**:
- `src/Mod/FEM/App/FemMesh.h`
- `src/App/DocumentObject.h`
**Hops**: FemMesh → GeoFeature → DocumentObject → PropertyContainer
**Difficulty**: 2

### Q109
**Query**: Where does `Feature` (Part workbench) inherit from, and which property does it gain for shape storage?
**Expected files**:
- `src/Mod/Part/App/PartFeature.h`
**Hops**: Feature → GeoFeature, gains PropertyPartShape Shape
**Difficulty**: 1

### Q110
**Query**: Which class does `Boolean` in `FeatureBoolean.cpp` extend to inherit shape storage?
**Expected files**:
- `src/Mod/Part/App/FeatureBoolean.cpp`
- `src/Mod/Part/App/PartFeature.h`
**Hops**: Boolean → Part::Feature → PropertyPartShape
**Difficulty**: 1

### Q111
**Query**: What does the `GCS` class in `GCS.h` provide as an interface for the Sketch solver?
**Expected files**:
- `src/Mod/Sketcher/App/planegcs/GCS.h`
- `src/Mod/Sketcher/App/Sketch.h`
**Hops**: GCS → solve, getRedundant, dofsNumber, applySolution interface
**Difficulty**: 1

### Q112
**Query**: How does `SubSystem` relate to `GCS` — which class owns and drives the SubSystem?
**Expected files**:
- `src/Mod/Sketcher/App/planegcs/SubSystem.cpp`
- `src/Mod/Sketcher/App/planegcs/GCS.cpp`
**Hops**: GCS → subSystems vector → SubSystem::calcJacobian, error, applySolution
**Difficulty**: 2

### Q113
**Query**: What virtual methods must a `ViewProvider` subclass override to handle property changes?
**Expected files**:
- `src/Gui/ViewProvider.h`
- `src/Gui/ViewProvider.cpp`
**Hops**: ViewProvider → onChanged, attach, update virtual interface
**Difficulty**: 1

### Q114
**Query**: How does `DrawPage` relate to `DrawViewPart` in the TechDraw class hierarchy?
**Expected files**:
- `src/Mod/TechDraw/App/DrawPage.cpp`
- `src/Mod/TechDraw/App/DrawViewPart.cpp`
**Hops**: DrawPage owns DrawView children → DrawViewPart inherits DrawView
**Difficulty**: 2

### Q115
**Query**: Which interface does `PyObjectBase` implement for Python attribute access?
**Expected files**:
- `src/Base/PyObjectBase.cpp`
**Hops**: PyObjectBase → repr, getattr, setattr Python slots
**Difficulty**: 1

### Q116
**Query**: Where is `Persistence` defined and how does it enforce save/restore contracts on subclasses?
**Expected files**:
- `src/Base/Persistence.cpp`
- `src/App/PropertyContainer.h`
**Hops**: Persistence → save/restore pure virtuals → PropertyContainer implements
**Difficulty**: 2

### Q117
**Query**: Which class does `SketchObject` ultimately derive from in the `App` module, through `Part::Part2DObject`?
**Expected files**:
- `src/Mod/Sketcher/App/SketchObject.h`
- `src/App/DocumentObject.h`
**Hops**: SketchObject → Part2DObject → Feature → GeoFeature → DocumentObject → PropertyContainer
**Difficulty**: 3

### Q118
**Query**: How does `Sketch` in `Sketch.h` compose a `GCS::GCS` object rather than inheriting from it?
**Expected files**:
- `src/Mod/Sketcher/App/Sketch.h`
- `src/Mod/Sketcher/App/planegcs/GCS.h`
**Hops**: Sketch has private GCS::GCS GCSsys member (composition, not inheritance)
**Difficulty**: 1

### Q119
**Query**: Which SMESH class does `FemMesh` wrap, and how does it expose mesh node counts?
**Expected files**:
- `src/Mod/FEM/App/FemMesh.cpp`
- `src/Mod/FEM/App/FemMesh.h`
**Hops**: FemMesh wraps SMESH_Mesh → getNodeCount → NbNodes()
**Difficulty**: 1

### Q120
**Query**: How does `FeatureExtrusion` relate to `Feature` (Part) and inherit shape storage?
**Expected files**:
- `src/Mod/Part/App/FeatureExtrusion.cpp`
- `src/Mod/Part/App/PartFeature.h`
**Hops**: Extrusion → Feature → PropertyPartShape Shape
**Difficulty**: 1

### Q121
**Query**: Where are the `ConstraintParallel` and `ConstraintPerpendicular` classes declared?
**Expected files**:
- `src/Mod/Sketcher/App/planegcs/Constraints.h`
**Hops**: Constraints.h → ConstraintParallel, ConstraintPerpendicular : Constraint
**Difficulty**: 1

### Q122
**Query**: What is the role of `PropertyContainer` in the inheritance of `App::Application`?
**Expected files**:
- `src/App/Application.cpp`
- `src/App/PropertyContainer.h`
**Hops**: Application → PropertyContainer → property map management
**Difficulty**: 1

### Q123
**Query**: How does `FileInfo` in `FileInfo.cpp` interface with the C++ `std::filesystem` API?
**Expected files**:
- `src/Base/FileInfo.cpp`
**Hops**: FileInfo → std::filesystem::exists, parent_path
**Difficulty**: 1

### Q124
**Query**: Which pure virtual methods does `UnifiedStore` define that `SQLiteUnifiedStore` must implement?
**Expected files**:
- `src/retrieval/database.py`
**Hops**: UnifiedStore → vector_search, graph_search abstract methods
**Difficulty**: 1

### Q125
**Query**: How does `XMLWriter` extend `Writer` to add structured XML output?
**Expected files**:
- `src/Base/XMLWriter.cpp`
- `src/Base/Writer.cpp`
**Hops**: XMLWriter → Writer, adds writeElement, beginElement, endElement
**Difficulty**: 1

### Q126
**Query**: Where is the `Reader` base class defined and what does `XMLReader` add on top of it?
**Expected files**:
- `src/Base/Reader.cpp`
- `src/Base/XMLReader.cpp`
**Hops**: Reader → file stream → XMLReader adds XML parsing, readElement, getAttribute
**Difficulty**: 1

### Q127
**Query**: How does `Area` in `Area.cpp` use a `ClipperLib` backend and what interface does it expose?
**Expected files**:
- `src/Mod/Path/App/Area.cpp`
**Hops**: Area → ClipperLib::Paths → myArea.add → getShape
**Difficulty**: 1

### Q128
**Query**: Which property type does `SketchObject` use to store its constraint list?
**Expected files**:
- `src/Mod/Sketcher/App/SketchObject.h`
**Hops**: SketchObject → PropertyConstraintList Constraints
**Difficulty**: 1

### Q129
**Query**: How does `Feature::getTopoShape` in `PartFeature.h` give access to the underlying `TopoShape`?
**Expected files**:
- `src/Mod/Part/App/PartFeature.h`
- `src/Mod/Part/App/TopoShape.h`
**Hops**: getTopoShape → Shape.getShape() → TopoShape::_Shape
**Difficulty**: 1

### Q130
**Query**: What is the relationship between `GCS::Algorithm` enum values and the solve dispatch in `GCS::solve`?
**Expected files**:
- `src/Mod/Sketcher/App/planegcs/GCS.cpp`
- `src/Mod/Sketcher/App/planegcs/GCS.h`
**Hops**: Algorithm enum {DogLeg, LM, BFGS} → switch dispatch → solve_DL / solve_LM / solve_BFGS
**Difficulty**: 1

### Q131
**Query**: Which class implements the `save` and `restore` virtual methods declared in `Base::Persistence`?
**Expected files**:
- `src/Base/Persistence.cpp`
- `src/App/PropertyContainer.cpp`
**Hops**: Persistence declares → PropertyContainer implements save/restore
**Difficulty**: 1

### Q132
**Query**: How does `ConstraintDistance` extend `Constraint` to enforce a distance between two points?
**Expected files**:
- `src/Mod/Sketcher/App/planegcs/Constraints.h`
**Hops**: ConstraintDistance : Constraint → error/grad for distance constraint
**Difficulty**: 1

### Q133
**Query**: Where does `ViewProviderSketch` inherit from to get scene graph connection?
**Expected files**:
- `src/Mod/Sketcher/Gui/ViewProviderSketch.cpp`
- `src/Gui/ViewProvider.h`
**Hops**: ViewProviderSketch → ViewProvider2D → ViewProvider
**Difficulty**: 1

### Q134
**Query**: What is the parent class of `FemAnalysis` and how does it inherit the `Group` property?
**Expected files**:
- `src/Mod/FEM/App/FemAnalysis.cpp`
- `src/App/DocumentObject.h`
**Hops**: FemAnalysis → DocumentObject → PropertyContainer → Group property
**Difficulty**: 2

### Q135
**Query**: How does `CmdSketcherConstrainCoincident` in `CommandSketcherTools.cpp` inherit `Command`?
**Expected files**:
- `src/Mod/Sketcher/Gui/CommandSketcherTools.cpp`
- `src/Gui/Command.cpp`
**Hops**: CmdSketcherConstrainCoincident → Command → invoke, activated, isActive
**Difficulty**: 1

### Q136
**Query**: Which virtual method of `DocumentObject` must subclasses override to implement computation?
**Expected files**:
- `src/App/DocumentObject.h`
- `src/App/DocumentObject.cpp`
**Hops**: execute() virtual → Feature::execute, Boolean::execute overrides
**Difficulty**: 1

### Q137
**Query**: How does `TopoShape` implement the `ComplexGeoData` interface for shape access?
**Expected files**:
- `src/Mod/Part/App/TopoShape.h`
**Hops**: TopoShape : ComplexGeoData → getShape, write, read
**Difficulty**: 1

### Q138
**Query**: What does the `BooleanOperation` enum in `TopoShape.h` enumerate and how is it used in `makeBoolean`?
**Expected files**:
- `src/Mod/Part/App/TopoShape.h`
- `src/Mod/Part/App/TopoShape.cpp`
**Hops**: BooleanOperation {BoolFuse, BoolCut, BoolCommon} → switch in makeBoolean
**Difficulty**: 1

### Q139
**Query**: How does `Extrusion` use `LengthFwd` property compared to `Base` in `PartFeature.h`?
**Expected files**:
- `src/Mod/Part/App/FeatureExtrusion.cpp`
- `src/Mod/Part/App/PartFeature.h`
**Hops**: Extrusion → Feature, adds Dir/LengthFwd/LengthRev properties
**Difficulty**: 1

### Q140
**Query**: Which class does `DrawViewPart` extend, and which abstract `execute` does it implement?
**Expected files**:
- `src/Mod/TechDraw/App/DrawViewPart.cpp`
- `src/App/DocumentObject.h`
**Hops**: DrawViewPart → DrawView → DocumentObject → execute virtual
**Difficulty**: 2

### Q141
**Query**: How does `HybridSearcher` use `UnifiedStore` as a composition dependency rather than inheritance?
**Expected files**:
- `src/retrieval/hybrid.py`
- `src/retrieval/database.py`
**Hops**: HybridSearcher has self.store: UnifiedStore → calls vector_search, graph_search
**Difficulty**: 1

### Q142
**Query**: What base class does `SQLiteUnifiedStore` extend to satisfy the retrieval interface?
**Expected files**:
- `src/retrieval/database.py`
**Hops**: SQLiteUnifiedStore → UnifiedStore → vector_search, graph_search implementations
**Difficulty**: 1

### Q143
**Query**: Where is `ArtifactRecord` defined and which fields does it expose to the indexer?
**Expected files**:
- `src/retrieval/database.py`
**Hops**: ArtifactRecord dataclass → artifact_id, repository, file_path, language, text, tier
**Difficulty**: 1

### Q144
**Query**: How does `Revolution` relate to `Feature` (Part) and what axis parameters does it require?
**Expected files**:
- `src/Mod/Part/App/FeatureRevolution.cpp`
- `src/Mod/Part/App/PartFeature.h`
**Hops**: Revolution → Feature → Base, Axis, Angle properties
**Difficulty**: 1

### Q145
**Query**: Which class owns `signalConstraintsChanged` — is it `Sketch` or `SketchObject`?
**Expected files**:
- `src/Mod/Sketcher/App/SketchObject.h`
- `src/Mod/Sketcher/App/Sketch.h`
**Hops**: SketchObject.h → signalConstraintsChanged (Sketch.h does not have it)
**Difficulty**: 1

### Q146
**Query**: How does the `PropertyMap` typedef in `PropertyContainer.h` define the container for all properties?
**Expected files**:
- `src/App/PropertyContainer.h`
**Hops**: PropertyContainer → std::map<std::string, Property*> propertyMap
**Difficulty**: 1

### Q147
**Query**: Which Python magic method does `PyObjectBase::repr` implement, and where is it called?
**Expected files**:
- `src/Base/PyObjectBase.cpp`
**Hops**: repr → __repr__ Python slot → Py_BuildValue
**Difficulty**: 1

### Q148
**Query**: How does `SelectionSingleton` broadcast selection events — which signal does it use?
**Expected files**:
- `src/Gui/Selection.cpp`
**Hops**: SelectionSingleton → signalSelectionChanged → subscribers
**Difficulty**: 1

### Q149
**Query**: What is the relationship between `Document::openTransaction` and `Gui::Document::openCommand`?
**Expected files**:
- `src/App/Document.cpp`
- `src/Gui/Document.cpp`
**Hops**: Gui::openCommand wraps App::openTransaction with undoActive flag
**Difficulty**: 1

### Q150
**Query**: How does `FemMesh::getSMesh` expose the raw `SMESH_Mesh*` pointer to callers?
**Expected files**:
- `src/Mod/FEM/App/FemMesh.h`
**Hops**: getSMesh → return myMesh
**Difficulty**: 1

---

## Seed 4 — Serialization & File I/O (rng=314)

### Q151
**Query**: How does `Document::save` in `Document.cpp` write each `DocumentObject` to disk using `Base::Writer`?
**Expected files**:
- `src/App/Document.cpp`
- `src/Base/Writer.cpp`
**Hops**: save → Writer(filename) → obj->save(writer)
**Difficulty**: 1

### Q152
**Query**: How does `Persistence::save` in `Persistence.cpp` write properties to an XML `Writer`?
**Expected files**:
- `src/Base/Persistence.cpp`
- `src/Base/XMLWriter.cpp`
**Hops**: Persistence::save → Writer::Stream → XMLWriter tags
**Difficulty**: 1

### Q153
**Query**: What format does `XMLWriter::writeElement` use to emit a tagged value into the document stream?
**Expected files**:
- `src/Base/XMLWriter.cpp`
**Hops**: writeElement → "<tag>val</tag>" via encodeXML
**Difficulty**: 1

### Q154
**Query**: How does `TopoShape::write` serialize a `TopoDS_Shape` using OCCT `BRepTools`?
**Expected files**:
- `src/Mod/Part/App/TopoShape.cpp`
- `src/Base/Writer.cpp`
**Hops**: write → BRepTools::Write(_Shape, writer.Stream())
**Difficulty**: 1

### Q155
**Query**: How does `TopoShape::read` deserialize a `TopoDS_Shape` from a `Base::Reader`?
**Expected files**:
- `src/Mod/Part/App/TopoShape.cpp`
- `src/Base/Reader.cpp`
**Hops**: read → BRep_Builder → BRepTools::Read(_Shape, reader.Stream())
**Difficulty**: 1

### Q156
**Query**: What XML header does `XMLWriter` write at construction time before any elements?
**Expected files**:
- `src/Base/XMLWriter.cpp`
**Hops**: XMLWriter ctor → "<?xml version='1.0'..." → "<Document SchemaVersion=4>"
**Difficulty**: 1

### Q157
**Query**: How does `Persistence::restore` in `Persistence.cpp` match property names from the XML stream?
**Expected files**:
- `src/Base/Persistence.cpp`
- `src/Base/XMLReader.cpp`
**Hops**: restore → reader.readElement("Property") → getAttribute("name") → getPropertyByName
**Difficulty**: 2

### Q158
**Query**: When `FemMesh::write` is called, which SMESH writer class is responsible for the output?
**Expected files**:
- `src/Mod/FEM/App/FemMesh.cpp`
**Hops**: write → SMESH_Writer.write(myMesh, fileName)
**Difficulty**: 1

### Q159
**Query**: How does `FemMesh::read` in `FemMesh.cpp` load mesh data from disk using `SMESH_Reader`?
**Expected files**:
- `src/Mod/FEM/App/FemMesh.cpp`
**Hops**: read → SMESH_Reader → read(fileName, mesh) → updateSMESH
**Difficulty**: 1

### Q160
**Query**: What does `Writer::beginCharStream` and `endCharStream` wrap, and why is this used for binary data?
**Expected files**:
- `src/Base/Writer.cpp`
**Hops**: beginCharStream → "<CharData>" → binary/base64 content → "</CharData>"
**Difficulty**: 1

### Q161
**Query**: How does `XMLReader::getAttributeAsInteger` convert a string attribute to an integer?
**Expected files**:
- `src/Base/XMLReader.cpp`
**Hops**: getAttributeAsInteger → getAttribute → std::stoi
**Difficulty**: 1

### Q162
**Query**: What is the structure of the FreeCAD `.FCStd` file format in terms of nested XML and binary blobs?
**Expected files**:
- `src/App/Document.cpp`
- `src/Base/XMLWriter.cpp`
- `src/Base/Writer.cpp`
**Hops**: Document::save → XMLWriter header → binary shape blobs via Writer
**Difficulty**: 3

### Q163
**Query**: How does `Document::restore` reconstruct document objects from the `XMLReader`?
**Expected files**:
- `src/App/Document.cpp`
- `src/Base/XMLReader.cpp`
**Hops**: restore → XMLReader::readElement → Persistence::restore → obj->restore
**Difficulty**: 2

### Q164
**Query**: Where does `FileInfo::extension` parse the file extension and what string operation does it use?
**Expected files**:
- `src/Base/FileInfo.cpp`
**Hops**: extension → rfind('.') → substr(pos+1)
**Difficulty**: 1

### Q165
**Query**: How does `FileInfo::exists` check whether a file is present on disk?
**Expected files**:
- `src/Base/FileInfo.cpp`
**Hops**: exists → std::filesystem::exists(FileName)
**Difficulty**: 1

### Q166
**Query**: How does `XMLWriter::beginElement` and `endElement` maintain indentation during write?
**Expected files**:
- `src/Base/XMLWriter.cpp`
- `src/Base/Writer.cpp`
**Hops**: beginElement → indent++ → endElement → indent--
**Difficulty**: 1

### Q167
**Query**: How does `Writer::incInd` and `Writer::decInd` manage the indentation string?
**Expected files**:
- `src/Base/Writer.cpp`
**Hops**: incInd → indentation += "  " / decInd → indentation.resize
**Difficulty**: 1

### Q168
**Query**: When `Area::getShape` retrieves the result, how does it convert Clipper paths back to a `TopoDS_Shape`?
**Expected files**:
- `src/Mod/Path/App/Area.cpp`
**Hops**: getShape → getCombinedPaths → fromClipperPaths → TopoDS_Shape
**Difficulty**: 1

### Q169
**Query**: How does `TopoShape::makeBoolean` with `BoolFuse` call `BRepAlgoAPI_Fuse` to produce the union?
**Expected files**:
- `src/Mod/Part/App/TopoShape.cpp`
**Hops**: makeBoolean → BoolFuse branch → BRepAlgoAPI_Fuse(_Shape, other._Shape).Shape()
**Difficulty**: 1

### Q170
**Query**: What OCCT functions does `DrawViewPart::execute` use to extract visible and hidden edge sets?
**Expected files**:
- `src/Mod/TechDraw/App/DrawViewPart.cpp`
**Hops**: execute → HLRBRep_Algo → HLRBRep_HLRToShape → VCompound / HCompound
**Difficulty**: 2

### Q171
**Query**: How does `Persistence::save` use `getPropertyCount` to write the count attribute in the XML?
**Expected files**:
- `src/Base/Persistence.cpp`
- `src/App/PropertyContainer.cpp`
**Hops**: save → getPropertyCount() → "<Properties Count=..."
**Difficulty**: 1

### Q172
**Query**: What does `XMLReader::readElement` loop over while advancing to the target tag?
**Expected files**:
- `src/Base/XMLReader.cpp`
**Hops**: readElement → while !isStartElement(tag) → reader.next()
**Difficulty**: 1

### Q173
**Query**: How does `Reader::readLine` in `Reader.cpp` extract a single line from the file stream?
**Expected files**:
- `src/Base/Reader.cpp`
**Hops**: readLine → std::getline(*ifs, line)
**Difficulty**: 1

### Q174
**Query**: Which SMESH function gives the element count in `FemMesh::getElementCount`?
**Expected files**:
- `src/Mod/FEM/App/FemMesh.cpp`
**Hops**: getElementCount → myMesh->GetMeshDS()->NbElements()
**Difficulty**: 1

### Q175
**Query**: How does `Document::save` iterate over `Objects` to call save on each object?
**Expected files**:
- `src/App/Document.cpp`
**Hops**: save → for obj in Objects → obj->save(writer)
**Difficulty**: 1

### Q176
**Query**: What does `Writer::Stream` do with the string passed to it — which underlying stream does it write to?
**Expected files**:
- `src/Base/Writer.cpp`
**Hops**: Stream → *ofs << str
**Difficulty**: 1

### Q177
**Query**: How does `XMLWriter::writeAttribute` embed a named attribute in the XML output?
**Expected files**:
- `src/Base/XMLWriter.cpp`
**Hops**: writeAttribute → *ofs << " " name "=" encodeXML(val)
**Difficulty**: 1

### Q178
**Query**: When `Application::openDocument` is called, how does `Document::restore` read back properties?
**Expected files**:
- `src/App/Application.cpp`
- `src/App/Document.cpp`
- `src/Base/Persistence.cpp`
**Hops**: openDocument → doc->restore(fileName) → Persistence::restore
**Difficulty**: 2

### Q179
**Query**: How does `FileInfo::dirPath` extract the directory part of a filename?
**Expected files**:
- `src/Base/FileInfo.cpp`
**Hops**: dirPath → std::filesystem::path(FileName).parent_path().string()
**Difficulty**: 1

### Q180
**Query**: How does `FeatureExtrusion::execute` pass the extrusion length to `BRepPrimAPI_MakePrism`?
**Expected files**:
- `src/Mod/Part/App/FeatureExtrusion.cpp`
**Hops**: execute → gp_Vec(dir) * LengthFwd.getValue() → MakePrism
**Difficulty**: 1

### Q181
**Query**: What file extension does FreeCAD use for native documents, and how does `FileInfo::extension` detect it?
**Expected files**:
- `src/Base/FileInfo.cpp`
- `src/App/Document.cpp`
**Hops**: FCStd extension → FileInfo::extension → hasExtension("FCStd")
**Difficulty**: 2

### Q182
**Query**: How does `XMLWriter` differ from `Writer` in terms of structured output for FreeCAD documents?
**Expected files**:
- `src/Base/XMLWriter.cpp`
- `src/Base/Writer.cpp`
**Hops**: Writer → raw stream → XMLWriter adds element/attribute structure
**Difficulty**: 1

### Q183
**Query**: How does `Boolean::execute` handle the case where base or tool shape is missing?
**Expected files**:
- `src/Mod/Part/App/FeatureBoolean.cpp`
**Hops**: execute → if !base || !tool → return new DocumentObjectExecReturn("Missing...")
**Difficulty**: 1

### Q184
**Query**: What data does `SQLiteUnifiedStore::upsert_artifacts` write to the SQLite database?
**Expected files**:
- `src/retrieval/database.py`
**Hops**: upsert_artifacts → INSERT INTO artifacts → id, repository, file_path, text, embedding
**Difficulty**: 1

### Q185
**Query**: How does `HashingEmbeddingProvider::embed` convert text into a fixed-dimension vector?
**Expected files**:
- `src/retrieval/database.py`
**Hops**: embed → tokenize → sha256 per token → sparse vector → normalize
**Difficulty**: 1

### Q186
**Query**: How does `SQLiteUnifiedStore::vector_search` compute cosine similarity between query and artifact embeddings?
**Expected files**:
- `src/retrieval/database.py`
**Hops**: vector_search → embed(query) → _cosine(query_embedding, row_embedding)
**Difficulty**: 1

### Q187
**Query**: What does `HybridSearcher::search` do when `lambda_ratio` is exactly 0.5?
**Expected files**:
- `src/retrieval/hybrid.py`
**Hops**: search → both vector_search and graph_search → interleave results
**Difficulty**: 1

### Q188
**Query**: How does `LexicalReranker` in `reranker.py` reorder candidates after initial retrieval?
**Expected files**:
- `src/retrieval/reranker.py`
**Hops**: rerank → keyword overlap scoring → sort → top_m
**Difficulty**: 1

### Q189
**Query**: What happens when `Writer` opens a file in `Writer::Writer` — which C++ file stream mode is used?
**Expected files**:
- `src/Base/Writer.cpp`
**Hops**: Writer(filename) → FileStream.open(std::ios::out | std::ios::binary)
**Difficulty**: 1

### Q190
**Query**: How does `Persistence::restore` use `getAttributeAsInteger` to read property count from XML?
**Expected files**:
- `src/Base/Persistence.cpp`
- `src/Base/XMLReader.cpp`
**Hops**: restore → readElement("Properties") → getAttributeAsInteger("Count", "0")
**Difficulty**: 2

### Q191
**Query**: How does `Area::build` clean the internal area state before re-adding paths?
**Expected files**:
- `src/Mod/Path/App/Area.cpp`
**Hops**: build → myArea.clean() → then re-add shapes
**Difficulty**: 1

### Q192
**Query**: What happens inside `FemMesh::updateSMESH` after reading mesh data?
**Expected files**:
- `src/Mod/FEM/App/FemMesh.cpp`
**Hops**: read → updateSMESH (internal refresh of SMESH data structures)
**Difficulty**: 1

### Q193
**Query**: How does `TopoShape::makeBoolean` produce `BoolCommon` (intersection)?
**Expected files**:
- `src/Mod/Part/App/TopoShape.cpp`
**Hops**: makeBoolean → BoolCommon → BRepAlgoAPI_Common(_Shape, other._Shape).Shape()
**Difficulty**: 1

### Q194
**Query**: What does `Document::commitTransaction` do to finalize an undo transaction?
**Expected files**:
- `src/App/Document.cpp`
**Hops**: commitTransaction → mUndoTransactions.push_back → _pActiveUndoTransaction = nullptr
**Difficulty**: 1

### Q195
**Query**: How does `XMLReader::getAttribute` retrieve a named attribute from the current XML element?
**Expected files**:
- `src/Base/XMLReader.cpp`
**Hops**: getAttribute → reader.attributeValue(name).toStdString()
**Difficulty**: 1

### Q196
**Query**: When `PyObjectBase::setattr` is called, what generic Python setter is used?
**Expected files**:
- `src/Base/PyObjectBase.cpp`
**Hops**: setattr → PyObject_GenericSetAttr
**Difficulty**: 1

### Q197
**Query**: How does `RepositoryIndexer` in `indexer.py` break source files into artifact records?
**Expected files**:
- `src/ingestion/indexer.py`
**Hops**: index_repository → parse → chunk → ArtifactRecord → upsert_artifacts
**Difficulty**: 2

### Q198
**Query**: Where does `Document::restore` call `Reader::readLine` to progress through the file?
**Expected files**:
- `src/App/Document.cpp`
- `src/Base/Reader.cpp`
**Hops**: restore → XMLReader → readElement → Reader::readLine
**Difficulty**: 2

### Q199
**Query**: How does `FeatureRevolution::execute` compute the revolution angle in radians from `Angle` property?
**Expected files**:
- `src/Mod/Part/App/FeatureRevolution.cpp`
**Hops**: execute → Angle.getValue() * M_PI / 180.0 → BRepPrimAPI_MakeRevol
**Difficulty**: 1

### Q200
**Query**: What `BooleanOperation` value does `FeatureBoolean` use for a subtraction (cut) operation?
**Expected files**:
- `src/Mod/Part/App/FeatureBoolean.cpp`
- `src/Mod/Part/App/TopoShape.h`
**Hops**: Type.getValue()==0 → BoolCut → BRepAlgoAPI_Cut
**Difficulty**: 1

---

## Seed 5 — Algorithm Internals (rng=500)

### Q201
**Query**: What numerical algorithm does `GCS::solve_DL` implement for solving the geometric constraint system?
**Expected files**:
- `src/Mod/Sketcher/App/planegcs/GCS.cpp`
**Hops**: solve_DL → Dog-Leg trust-region method
**Difficulty**: 2

### Q202
**Query**: How does `GCS::solve_LM` compute the Levenberg-Marquardt update step using the Jacobian?
**Expected files**:
- `src/Mod/Sketcher/App/planegcs/GCS.cpp`
- `src/Mod/Sketcher/App/planegcs/SubSystem.cpp`
**Hops**: solve_LM → JtJ + lambda*I → ldlt().solve → step
**Difficulty**: 3

### Q203
**Query**: What stopping criterion does `GCS::solve_DL` use to declare convergence?
**Expected files**:
- `src/Mod/Sketcher/App/planegcs/GCS.cpp`
**Hops**: solve_DL → f < XconvergenceFine → return Success
**Difficulty**: 1

### Q204
**Query**: How does `SubSystem::calcJacobian` construct the constraint Jacobian matrix entry-by-entry?
**Expected files**:
- `src/Mod/Sketcher/App/planegcs/SubSystem.cpp`
- `src/Mod/Sketcher/App/planegcs/Constraints.h`
**Hops**: calcJacobian → J(i,j) = constraints[i]->grad(params[j])
**Difficulty**: 2

### Q205
**Query**: What is the role of the `redundantCount` field in `GCS` when computing degrees of freedom?
**Expected files**:
- `src/Mod/Sketcher/App/planegcs/GCS.cpp`
- `src/Mod/Sketcher/App/planegcs/GCS.h`
**Hops**: dofsNumber → params.size - constraints.size + redundantCount
**Difficulty**: 1

### Q206
**Query**: How does `GCS::getRedundant` use Eigen's `FullPivLU` to find linearly dependent constraints?
**Expected files**:
- `src/Mod/Sketcher/App/planegcs/GCS.cpp`
**Hops**: getRedundant → FullPivLU(jacobianMatrix) → rank check → redundant list
**Difficulty**: 2

### Q207
**Query**: What mathematical operation does `SubSystem::error` compute to aggregate constraint violations?
**Expected files**:
- `src/Mod/Sketcher/App/planegcs/SubSystem.cpp`
**Hops**: error → sum of squared constraint errors → 0.5 * err
**Difficulty**: 1

### Q208
**Query**: How does `TopoShape::makeBoolean` with `BoolCut` subtract one OCCT shape from another?
**Expected files**:
- `src/Mod/Part/App/TopoShape.cpp`
**Hops**: makeBoolean → BoolCut → BRepAlgoAPI_Cut(_Shape, other._Shape).Shape()
**Difficulty**: 1

### Q209
**Query**: What algorithm does `BRepPrimAPI_MakePrism` implement to extrude a profile along a vector?
**Expected files**:
- `src/Mod/Part/App/FeatureExtrusion.cpp`
- `src/Mod/Part/App/TopoShape.cpp`
**Hops**: FeatureExtrusion → MakePrism → linear sweep of base profile
**Difficulty**: 2

### Q210
**Query**: How does `HybridSearcher::search` blend vector results and graph results using `lambda_ratio`?
**Expected files**:
- `src/retrieval/hybrid.py`
**Hops**: search → vector_slots = lambda_ratio * len(v_res) → interleave v+g results
**Difficulty**: 1

### Q211
**Query**: What hash function does `HashingEmbeddingProvider::embed` use per token to build the vector?
**Expected files**:
- `src/retrieval/database.py`
**Hops**: embed → sha256 per token → index from digest[:4] → sign from digest[4]
**Difficulty**: 2

### Q212
**Query**: How does `SQLiteUnifiedStore::graph_search` perform BFS from anchor artifacts along graph edges?
**Expected files**:
- `src/retrieval/database.py`
**Hops**: graph_search → _find_anchor_ids → BFS queue → _outgoing_edges
**Difficulty**: 2

### Q213
**Query**: What scoring formula does `SQLiteUnifiedStore::vector_search` use to combine cosine and keyword scores?
**Expected files**:
- `src/retrieval/database.py`
**Hops**: vector_search → cosine + keyword_score (0.05 per term) → sort
**Difficulty**: 1

### Q214
**Query**: How does `GCS::solve_DL` compute the Cauchy (steepest descent) step `h_sd`?
**Expected files**:
- `src/Mod/Sketcher/App/planegcs/GCS.cpp`
**Hops**: solve_DL → alpha = ||g||^2 / ||J*g||^2 → h_sd = -alpha * g
**Difficulty**: 2

### Q215
**Query**: What linear algebra operation does `GCS::solve_LM` use to solve the normal equations?
**Expected files**:
- `src/Mod/Sketcher/App/planegcs/GCS.cpp`
**Hops**: solve_LM → JtJ.ldlt().solve(-Jt * residuals)
**Difficulty**: 2

### Q216
**Query**: How does `Area::toClipperPaths` in `Area.cpp` convert a `TopoDS_Shape` to Clipper integer paths?
**Expected files**:
- `src/Mod/Path/App/Area.cpp`
**Hops**: build → toClipperPaths(shape, paths) → ClipperLib::Paths
**Difficulty**: 2

### Q217
**Query**: What data structure does `GCS` use to store the list of active parameters?
**Expected files**:
- `src/Mod/Sketcher/App/planegcs/GCS.h`
**Hops**: GCS → std::vector<double*> params
**Difficulty**: 1

### Q218
**Query**: How does `DrawViewPart::execute` use the HLR (Hidden Line Removal) algorithm to separate visible from hidden edges?
**Expected files**:
- `src/Mod/TechDraw/App/DrawViewPart.cpp`
**Hops**: execute → HLRBRep_Algo → HLRBRep_HLRToShape → VCompound (visible) / HCompound (hidden)
**Difficulty**: 2

### Q219
**Query**: How does `BRepPrimAPI_MakeRevol` in `FeatureRevolution.cpp` generate the revolution solid?
**Expected files**:
- `src/Mod/Part/App/FeatureRevolution.cpp`
**Hops**: Revolution → gp_Ax1 axis → MakeRevol(shape, axis, angle_radians)
**Difficulty**: 1

### Q220
**Query**: What convergence criterion does `GCS::solve_DL` apply to the gradient norm?
**Expected files**:
- `src/Mod/Sketcher/App/planegcs/GCS.cpp`
**Hops**: solve_DL → f < XconvergenceFine → return Success
**Difficulty**: 1

### Q221
**Query**: How does `SubSystem::applySolution` copy solved parameter values back to their storage locations?
**Expected files**:
- `src/Mod/Sketcher/App/planegcs/SubSystem.cpp`
**Hops**: applySolution → *params[i] = solution[i]
**Difficulty**: 1

### Q222
**Query**: What edge-priority ordering does `SQLiteUnifiedStore::_outgoing_edges` use for BFS traversal?
**Expected files**:
- `src/retrieval/database.py`
**Hops**: _outgoing_edges → priority dict {calls:0, defines:1, imports:2, ...} → sort
**Difficulty**: 2

### Q223
**Query**: How does `ConstraintCoincident::error` quantify the distance between two coincident points?
**Expected files**:
- `src/Mod/Sketcher/App/planegcs/Constraints.h`
**Hops**: ConstraintCoincident::error → distance metric between p1 and p2
**Difficulty**: 1

### Q224
**Query**: What does `HashingEmbeddingProvider._tokens` use to tokenize text for embedding?
**Expected files**:
- `src/retrieval/database.py`
**Hops**: _tokens → re.findall(r"[A-Za-z_][A-Za-z0-9_]*", text.lower())
**Difficulty**: 1

### Q225
**Query**: How does `Sketch::solve` decide whether to report redundant constraints vs. convergence failure?
**Expected files**:
- `src/Mod/Sketcher/App/Sketch.cpp`
- `src/Mod/Sketcher/App/planegcs/GCS.cpp`
**Hops**: Sketch::solve → GCS::Failed → getRedundant → handleRedundantConstraints
**Difficulty**: 2

### Q226
**Query**: How does `Area::fromClipperPaths` reconstruct geometry from integer Clipper coordinates?
**Expected files**:
- `src/Mod/Path/App/Area.cpp`
**Hops**: getShape → getCombinedPaths → fromClipperPaths → TopoDS_Shape
**Difficulty**: 2

### Q227
**Query**: What Eigen decomposition does `GCS::getRedundant` use to identify rank-deficient constraints?
**Expected files**:
- `src/Mod/Sketcher/App/planegcs/GCS.cpp`
**Hops**: getRedundant → Eigen::FullPivLU<MatrixXd> → rank check
**Difficulty**: 2

### Q228
**Query**: How does `BRepAlgoAPI_Fuse` in `TopoShape::makeBoolean` compute the union of two OCCT shapes?
**Expected files**:
- `src/Mod/Part/App/TopoShape.cpp`
**Hops**: makeBoolean → BoolFuse → BRepAlgoAPI_Fuse(_Shape, other._Shape).Shape()
**Difficulty**: 1

### Q229
**Query**: What normalization step does `HashingEmbeddingProvider::embed` apply to the raw vector?
**Expected files**:
- `src/retrieval/database.py`
**Hops**: embed → norm = sqrt(sum(v^2)) → [v/norm for v in vector]
**Difficulty**: 1

### Q230
**Query**: How does `GCS::MaxIterations` bound the number of solver iterations in `solve_DL`?
**Expected files**:
- `src/Mod/Sketcher/App/planegcs/GCS.cpp`
- `src/Mod/Sketcher/App/planegcs/GCS.h`
**Hops**: solve_DL → for iter in MaxIterations → bounded loop
**Difficulty**: 1

### Q231
**Query**: How does `HybridSearcher` handle the case where `lambda_ratio == 1.0` (pure vector search)?
**Expected files**:
- `src/retrieval/hybrid.py`
**Hops**: search → if lambda_ratio == 1.0 → return store.vector_search only
**Difficulty**: 1

### Q232
**Query**: What distance metric does `SQLiteUnifiedStore::_cosine` compute between two embedding vectors?
**Expected files**:
- `src/retrieval/database.py`
**Hops**: _cosine → dot product (assumes pre-normalized vectors)
**Difficulty**: 1

### Q233
**Query**: How does `ConstraintParallel::error` measure non-parallelism between two lines?
**Expected files**:
- `src/Mod/Sketcher/App/planegcs/Constraints.h`
**Hops**: ConstraintParallel::error → cross product magnitude or angle between directions
**Difficulty**: 2

### Q234
**Query**: What algorithm does `PromptAssembler::_u_shape_order` use to arrange context chunks?
**Expected files**:
- `src/retrieval/assembler.py`
**Hops**: _u_shape_order → even indices left, odd indices right reversed → U-shape
**Difficulty**: 1

### Q235
**Query**: How does `GCS::solve` dispatch to the three solver algorithms based on the `Algorithm` parameter?
**Expected files**:
- `src/Mod/Sketcher/App/planegcs/GCS.cpp`
- `src/Mod/Sketcher/App/planegcs/GCS.h`
**Hops**: solve → switch(alg) → DogLeg: solve_DL, LM: solve_LM, BFGS: solve_BFGS
**Difficulty**: 1

### Q236
**Query**: How does `SQLiteUnifiedStore::_signal_terms` filter stopwords before keyword matching?
**Expected files**:
- `src/retrieval/database.py`
**Hops**: _signal_terms → QUERY_STOPWORDS set → exclude terms ≤ 1 char
**Difficulty**: 1

### Q237
**Query**: What does `SubSystem::fillParams` do to prepare the initial parameter vector for optimization?
**Expected files**:
- `src/Mod/Sketcher/App/planegcs/SubSystem.cpp`
**Hops**: fillParams → x.resize(params.size()) → x[i] = *params[i]
**Difficulty**: 1

### Q238
**Query**: How does `DrawViewPart::execute` handle the projection axis when setting up the HLR algorithm?
**Expected files**:
- `src/Mod/TechDraw/App/DrawViewPart.cpp`
**Hops**: execute → getViewAxis() → gp_Ax2 transform for HLR
**Difficulty**: 1

### Q239
**Query**: How does `Area::setParams` update the internal `myParams` and trigger a rebuild?
**Expected files**:
- `src/Mod/Path/App/Area.cpp`
**Hops**: setParams → myParams = params → build()
**Difficulty**: 1

### Q240
**Query**: What is the trust-region update strategy in `GCS::solve_DL` for adjusting the step size?
**Expected files**:
- `src/Mod/Sketcher/App/planegcs/GCS.cpp`
**Hops**: solve_DL → compute h_sd, h_gn → dog-leg combination → trust region update
**Difficulty**: 3

### Q241
**Query**: How does `GCS::solve` return `GCS::Failed` when no algorithm converges?
**Expected files**:
- `src/Mod/Sketcher/App/planegcs/GCS.cpp`
**Hops**: solve_DL → exceeds MaxIterations → return Failed
**Difficulty**: 1

### Q242
**Query**: What penalty coefficient does `Constraint::rescale` apply, and which subclasses override it?
**Expected files**:
- `src/Mod/Sketcher/App/planegcs/Constraints.h`
**Hops**: rescale(coef=1.0) → default no-op → subclasses may override
**Difficulty**: 1

### Q243
**Query**: How does `SQLiteUnifiedStore::graph_search` limit the BFS to `breadth` total artifacts?
**Expected files**:
- `src/retrieval/database.py`
**Hops**: graph_search → while queue and len(ordered_ids) < breadth
**Difficulty**: 1

### Q244
**Query**: What OCCT BRep builder is used in `TopoShape::read` to reconstruct a shape from stream data?
**Expected files**:
- `src/Mod/Part/App/TopoShape.cpp`
**Hops**: read → BRep_Builder builder → BRepTools::Read(_Shape, reader.Stream(), builder)
**Difficulty**: 1

### Q245
**Query**: How does `HashingEmbeddingProvider` handle the zero-norm edge case in `embed`?
**Expected files**:
- `src/retrieval/database.py`
**Hops**: embed → if norm == 0 → return vector (no division)
**Difficulty**: 1

### Q246
**Query**: What role does `SubSystem::getResiduals` play in the LM iteration of `GCS::solve_LM`?
**Expected files**:
- `src/Mod/Sketcher/App/planegcs/SubSystem.cpp`
- `src/Mod/Sketcher/App/planegcs/GCS.cpp`
**Hops**: solve_LM → -Jt * getResiduals() → right-hand side of normal equations
**Difficulty**: 2

### Q247
**Query**: How does `SketchObject::detectRedundant` expose the redundant constraint indices to Python callers?
**Expected files**:
- `src/Mod/Sketcher/App/SketchObject.cpp`
- `src/Mod/Sketcher/App/planegcs/GCS.cpp`
**Hops**: detectRedundant → Sketch::solve → GCS::getRedundant → std::vector<int>
**Difficulty**: 2

### Q248
**Query**: What BFS traversal order does `SQLiteUnifiedStore::graph_search` use when multiple anchors exist?
**Expected files**:
- `src/retrieval/database.py`
**Hops**: graph_search → queue [(anchor, 0)] → pop front → BFS level-order
**Difficulty**: 2

### Q249
**Query**: How does `GCS::applySolution` propagate final parameter values back through all active SubSystems?
**Expected files**:
- `src/Mod/Sketcher/App/planegcs/GCS.cpp`
- `src/Mod/Sketcher/App/planegcs/SubSystem.cpp`
**Hops**: applySolution → for sys in subSystems → sys->applySolution() → *params[i] = solution[i]
**Difficulty**: 2

### Q250
**Query**: How does the `PromptAssembler::assemble` method in `assembler.py` build the final LLM prompt from retrieved chunks?
**Expected files**:
- `src/retrieval/assembler.py`
**Hops**: assemble → system_rule + context chunks (_u_shape_order) + Query line
**Difficulty**: 1
