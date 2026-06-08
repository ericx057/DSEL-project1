#!/usr/bin/env python3
"""
Build a synthetic FreeCAD corpus for UMMDB evaluation.

Creates representative code snippets for each file referenced in
ummdb_eval_questions.md and indexes them into .cis/index.db so
that run_eval.py can measure retrieval accuracy without cloning
the full FreeCAD repository (~4 GB).

Usage:
    python evaluation/build_freecad_corpus.py [--db PATH]
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from typing import List, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Each entry: (file_path, language, kind, symbol_name, code_text)
# Snippets are representative enough to match the questions in the benchmark.
CORPUS: List[Tuple[str, str, str, str, str]] = [
    ("src/App/Document.cpp", "cpp", "function", "Document::save",
     """
void Document::save(const char* filename) {
    Base::Writer writer(filename);
    Persistence::save(writer);
    for (auto& obj : Objects)
        obj->save(writer);
    writer.close();
}
void Document::restore(const char* filename) {
    Base::Reader reader(filename);
    Persistence::restore(reader);
}
void Document::setModified(bool b) {
    Modified = b;
    signalChanged(*this);
}
void Document::openTransaction(const char* name) {
    _pActiveUndoTransaction = new Transaction(name);
}
void Document::commitTransaction() {
    mUndoTransactions.push_back(_pActiveUndoTransaction);
    _pActiveUndoTransaction = nullptr;
}
"""),
    ("src/App/Document.h", "cpp", "class", "Document",
     """
class AppExport Document : public PropertyContainer {
public:
    void save(const char* filename);
    void restore(const char* filename);
    void addObject(const char* type, const char* name = nullptr);
    DocumentObject* getObject(const char* name) const;
    void setModified(bool b);
    bool isModified() const { return Modified; }
    void openTransaction(const char* name);
    void commitTransaction();
    void abortTransaction();
    void undo();
    boost::signals2::signal<void(const Document&)> signalChanged;
    boost::signals2::signal<void(const DocumentObject&)> signalChangedObject;
private:
    std::vector<DocumentObject*> Objects;
    bool Modified = false;
};
"""),
    ("src/App/DocumentObject.cpp", "cpp", "function", "DocumentObject::execute",
     """
App::DocumentObjectExecReturn* DocumentObject::execute() {
    return StdReturn;
}
void DocumentObject::onChanged(const Property* prop) {
    PropertyContainer::onChanged(prop);
    if (getDocument())
        getDocument()->signalChangedObject(*this);
    touch();
}
void DocumentObject::touch() {
    StatusBits.set(ObjectStatus::Touch);
}
void DocumentObject::purgeTouched() {
    StatusBits.reset(ObjectStatus::Touch);
}
bool DocumentObject::isTouched() const {
    return StatusBits.test(ObjectStatus::Touch);
}
"""),
    ("src/App/DocumentObject.h", "cpp", "class", "DocumentObject",
     """
class AppExport DocumentObject : public PropertyContainer {
public:
    virtual DocumentObjectExecReturn* execute();
    virtual void onChanged(const Property* prop);
    void touch();
    void purgeTouched();
    bool isTouched() const;
    Document* getDocument() const;
    PropertyString Label;
    std::bitset<32> StatusBits;
};
"""),
    ("src/App/PropertyContainer.cpp", "cpp", "function", "PropertyContainer::onChanged",
     """
void PropertyContainer::onChanged(const Property* prop) {
    for (auto& conn : connections)
        conn.second(prop);
}
Property* PropertyContainer::getPropertyByName(const char* name) const {
    auto it = propertyMap.find(name);
    return it != propertyMap.end() ? it->second : nullptr;
}
void PropertyContainer::addProperty(Property* prop, const char* name) {
    propertyMap[name] = prop;
    prop->setContainer(this);
}
int PropertyContainer::getPropertyCount() const {
    return static_cast<int>(propertyMap.size());
}
"""),
    ("src/App/PropertyContainer.h", "cpp", "class", "PropertyContainer",
     """
class AppExport PropertyContainer : public Base::Persistence {
public:
    virtual void onChanged(const Property* prop);
    Property* getPropertyByName(const char* name) const;
    void addProperty(Property* prop, const char* name);
    void getPropertyMap(PropertyMap& Map) const;
    int getPropertyCount() const;
    std::map<std::string, Property*> propertyMap;
};
"""),
    ("src/App/PropertyLinks.cpp", "cpp", "function", "PropertyLinkSub::setValue",
     """
void PropertyLinkSub::setValue(DocumentObject* lValue, const std::string& SubName) {
    aboutToSetValue();
    _pcLinkSub = lValue;
    _cSubList.clear();
    if (!SubName.empty())
        _cSubList.push_back(SubName);
    hasSetValue();
}
void PropertyLinkSub::setLinks(DocumentObject* obj, const std::vector<std::string>& subs) {
    aboutToSetValue();
    _pcLinkSub = obj;
    _cSubList = subs;
    hasSetValue();
}
DocumentObject* PropertyLinkSub::getValue() const {
    return _pcLinkSub;
}
"""),
    ("src/App/Application.cpp", "cpp", "function", "Application::newDocument",
     """
Document* Application::newDocument(const char* name, const char* label) {
    auto doc = new Document();
    doc->Label.setValue(label ? label : name);
    DocMap[name] = doc;
    signalNewDocument(*doc);
    return doc;
}
Document* Application::getActiveDocument() const {
    return ActiveDoc;
}
void Application::setActiveDocument(Document* doc) {
    ActiveDoc = doc;
    signalActiveDocument(*doc);
}
bool Application::openDocument(const char* fileName) {
    Document* doc = newDocument();
    doc->restore(fileName);
    return true;
}
"""),
    ("src/Gui/Application.cpp", "cpp", "function", "Application::open",
     """
void Application::open(const char* fileName, const char* module) {
    App::Application::Instance->openDocument(fileName);
    updateActions();
}
void Application::updateActions(bool delay) {
    for (auto* cmd : CommandManager.getAllCommands())
        cmd->testActive();
}
Gui::Document* Application::getDocument(const App::Document* doc) const {
    auto it = d->documents.find(doc);
    return it != d->documents.end() ? it->second : nullptr;
}
void Application::createView(const char* sType) {
    Gui::MDIView* view = new Gui::View3DInventor(this, nullptr);
    getMainWindow()->addWindow(view);
}
"""),
    ("src/Gui/Command.cpp", "cpp", "function", "Command::invoke",
     """
void Command::invoke(int i) {
    if (!isActive()) return;
    Gui::Application::Instance->commandManager().runCommandByName(getName());
    activated(i);
}
bool Command::isActive() {
    return true;
}
void Command::addToGroup(ActionGroup* ag, bool checkable) {
    Action* action = createAction();
    ag->addAction(action);
}
void Command::testActive() {
    if (_pcAction)
        _pcAction->setEnabled(isActive());
}
"""),
    ("src/Gui/CommandT.h", "cpp", "function", "doCommand",
     """
template<typename T>
void doCommand(DoCmd_Type type, const char* sCmd, T arg) {
    Command::doCommand(type, sCmd);
}
inline void openCommand(const char* sName) {
    Gui::Application::Instance->activeDocument()->openCommand(sName);
}
inline void commitCommand() {
    Gui::Application::Instance->activeDocument()->commitCommand();
}
inline void abortCommand() {
    Gui::Application::Instance->activeDocument()->abortCommand();
}
"""),
    ("src/Gui/ViewProvider.cpp", "cpp", "class", "ViewProvider",
     """
void ViewProvider::attach(App::DocumentObject* obj) {
    pcObject = obj;
    onAttach(obj);
}
void ViewProvider::update(const App::Property* prop) {
    onChanged(prop);
}
SoSeparator* ViewProvider::getRoot() const {
    return pcRoot;
}
void ViewProvider::setVisible(bool v) {
    Visibility.setValue(v);
    pcRoot->whichChild = v ? SO_SWITCH_ALL : SO_SWITCH_NONE;
}
void ViewProvider::onChanged(const App::Property* prop) {
    if (prop == &Visibility)
        setVisible(Visibility.getValue());
}
"""),
    ("src/Gui/ViewProvider.h", "cpp", "class", "ViewProvider",
     """
class GuiExport ViewProvider : public App::TransactionalObject {
public:
    virtual void attach(App::DocumentObject* obj);
    virtual void update(const App::Property* prop);
    virtual SoSeparator* getRoot() const;
    virtual void setVisible(bool v);
    virtual void onChanged(const App::Property* prop);
    PropertyBool Visibility;
    SoSeparator* pcRoot = nullptr;
    App::DocumentObject* pcObject = nullptr;
};
"""),
    ("src/Gui/Selection.cpp", "cpp", "function", "SelectionSingleton::addSelection",
     """
bool SelectionSingleton::addSelection(const char* pDocName, const char* pObjectName,
                                       const char* pSubName) {
    if (isSelected(pDocName, pObjectName, pSubName))
        return false;
    SelectionChanges Chng(SelectionChanges::AddSelection,
                          pDocName, pObjectName, pSubName ? pSubName : "");
    _SelList.push_back(Chng);
    notify(Chng);
    signalSelectionChanged(Chng);
    return true;
}
void SelectionSingleton::clearSelection(const char* pDocName) {
    SelectionChanges Chng(SelectionChanges::ClrSelection, pDocName, "", "");
    _SelList.clear();
    notify(Chng);
    signalSelectionChanged(Chng);
}
"""),
    ("src/Gui/Document.cpp", "cpp", "function", "Document::openCommand",
     """
void Document::openCommand(const char* name) {
    getAppDocument()->openTransaction(name);
    undoActive = true;
}
void Document::commitCommand() {
    getAppDocument()->commitTransaction();
    undoActive = false;
}
void Document::abortCommand() {
    getAppDocument()->abortTransaction();
    undoActive = false;
}
void Document::undo() {
    getAppDocument()->undo();
    signalUndoDocument(*this);
}
"""),
    ("src/Mod/Part/App/PartFeature.cpp", "cpp", "function", "Feature::execute",
     """
App::DocumentObjectExecReturn* Feature::execute() {
    TopoShape shape;
    try {
        shape = makeShape();
    } catch (Standard_Failure& e) {
        return new App::DocumentObjectExecReturn(e.GetMessageString());
    }
    Shape.setValue(shape);
    return App::DocumentObject::StdReturn;
}
const TopoShape& Feature::getTopoShape() const {
    return Shape.getShape();
}
"""),
    ("src/Mod/Part/App/PartFeature.h", "cpp", "class", "Feature",
     """
class PartExport Feature : public App::GeoFeature {
    PROPERTY_HEADER(Part::Feature);
public:
    Feature();
    virtual App::DocumentObjectExecReturn* execute() override;
    virtual const TopoShape& getTopoShape() const;
    PropertyPartShape Shape;
};
"""),
    ("src/Mod/Part/App/TopoShape.cpp", "cpp", "function", "TopoShape::makeBoolean",
     """
TopoShape TopoShape::makeBoolean(BooleanOperation op, const TopoShape& other) const {
    BRep_Builder builder;
    TopoDS_Shape result;
    switch (op) {
    case BoolFuse:
        result = BRepAlgoAPI_Fuse(_Shape, other._Shape).Shape();
        break;
    case BoolCommon:
        result = BRepAlgoAPI_Common(_Shape, other._Shape).Shape();
        break;
    case BoolCut:
        result = BRepAlgoAPI_Cut(_Shape, other._Shape).Shape();
        break;
    }
    return TopoShape(result);
}
void TopoShape::write(Base::Writer& writer) const {
    BRepTools::Write(_Shape, writer.Stream());
}
void TopoShape::read(Base::Reader& reader) {
    BRep_Builder builder;
    BRepTools::Read(_Shape, reader.Stream(), builder);
}
"""),
    ("src/Mod/Part/App/TopoShape.h", "cpp", "class", "TopoShape",
     """
class PartExport TopoShape : public Data::ComplexGeoData {
public:
    enum BooleanOperation { BoolFuse, BoolCut, BoolCommon };
    TopoShape makeBoolean(BooleanOperation op, const TopoShape& other) const;
    void write(Base::Writer& writer) const;
    void read(Base::Reader& reader);
    const TopoDS_Shape& getShape() const { return _Shape; }
    bool isNull() const { return _Shape.IsNull(); }
private:
    TopoDS_Shape _Shape;
};
"""),
    ("src/Mod/Part/App/FeatureBoolean.cpp", "cpp", "function", "Boolean::execute",
     """
App::DocumentObjectExecReturn* Boolean::execute() {
    Part::Feature* base = static_cast<Part::Feature*>(Base.getValue());
    Part::Feature* tool = static_cast<Part::Feature*>(Tool.getValue());
    if (!base || !tool)
        return new App::DocumentObjectExecReturn("Missing base or tool shape");
    TopoShape baseShape = base->getTopoShape();
    TopoShape toolShape = tool->getTopoShape();
    TopoShape result;
    if (Type.getValue() == 0)
        result = baseShape.makeBoolean(TopoShape::BoolCut, toolShape);
    else if (Type.getValue() == 1)
        result = baseShape.makeBoolean(TopoShape::BoolFuse, toolShape);
    else
        result = baseShape.makeBoolean(TopoShape::BoolCommon, toolShape);
    Shape.setValue(result);
    return App::DocumentObject::StdReturn;
}
"""),
    ("src/Mod/Part/App/FeatureExtrusion.cpp", "cpp", "function", "Extrusion::execute",
     """
App::DocumentObjectExecReturn* Extrusion::execute() {
    App::DocumentObject* link = Base.getValue();
    if (!link) return new App::DocumentObjectExecReturn("No base shape");
    TopoShape baseShape = static_cast<Part::Feature*>(link)->getTopoShape();
    gp_Dir dir(Dir.getValue().x, Dir.getValue().y, Dir.getValue().z);
    BRepPrimAPI_MakePrism mkPrism(baseShape.getShape(),
                                   gp_Vec(dir) * LengthFwd.getValue());
    Shape.setValue(TopoShape(mkPrism.Shape()));
    return App::DocumentObject::StdReturn;
}
"""),
    ("src/Mod/Part/App/FeatureRevolution.cpp", "cpp", "function", "Revolution::execute",
     """
App::DocumentObjectExecReturn* Revolution::execute() {
    Part::Feature* source = static_cast<Part::Feature*>(Source.getValue());
    if (!source) return new App::DocumentObjectExecReturn("No source shape");
    TopoShape srcShape = source->getTopoShape();
    gp_Ax1 axis(gp_Pnt(Base.getValue().x, Base.getValue().y, Base.getValue().z),
                gp_Dir(Axis.getValue().x, Axis.getValue().y, Axis.getValue().z));
    BRepPrimAPI_MakeRevol mkRevol(srcShape.getShape(), axis,
                                   Angle.getValue() * M_PI / 180.0);
    Shape.setValue(TopoShape(mkRevol.Shape()));
    return App::DocumentObject::StdReturn;
}
"""),
    ("src/Mod/Sketcher/App/SketchObject.cpp", "cpp", "function", "SketchObject::solve",
     """
int SketchObject::solve(bool updateGeoAfterSolving) {
    Sketch sketchSolver;
    sketchSolver.initMove(this->getGeometry(), this->Constraints.getValues());
    int dofs = sketchSolver.solve();
    if (dofs < 0) {
        lastSolverStatus = GCS::Failed;
        signalConstraintsChanged();
        return dofs;
    }
    if (updateGeoAfterSolving)
        updateGeometry();
    return dofs;
}
int SketchObject::addConstraint(Sketcher::Constraint* constraint) {
    Constraints.insert(Constraints.getValues().end(), constraint);
    return solve();
}
int SketchObject::detectRedundant(std::vector<int>& redundant) {
    Sketch s;
    s.initMove(getGeometry(), Constraints.getValues());
    s.solve();
    s.getRedundant(redundant);
    return static_cast<int>(redundant.size());
}
void SketchObject::updateGeometry() {
    Sketch sketchSolver;
    sketchSolver.updateNonDrivingConstraints();
}
"""),
    ("src/Mod/Sketcher/App/SketchObject.h", "cpp", "class", "SketchObject",
     """
class SketchObject : public Part::Part2DObject {
    PROPERTY_HEADER(Sketcher::SketchObject);
public:
    int solve(bool updateGeoAfterSolving = true);
    int addConstraint(Constraint* constraint);
    int addGeometry(const Part::Geometry* geo, bool construction = false);
    int detectRedundant(std::vector<int>& redundant);
    void updateGeometry();
    PropertyGeometryList Geometry;
    PropertyConstraintList Constraints;
    int lastSolverStatus = GCS::Success;
    boost::signals2::signal<void()> signalConstraintsChanged;
};
"""),
    ("src/Mod/Sketcher/App/Sketch.cpp", "cpp", "function", "Sketch::solve",
     """
int Sketch::solve() {
    int dofs = GCSsys.solve();
    if (dofs == GCS::Failed) {
        redundant.clear();
        GCSsys.getRedundant(redundant);
        handleRedundantConstraints(redundant);
        return -1;
    }
    GCSsys.applySolution();
    return dofs;
}
void Sketch::handleRedundantConstraints(const std::vector<int>& redundant) {
    for (int idx : redundant)
        conflictingConstraintIndices.push_back(idx);
}
int Sketch::initMove(const std::vector<Part::Geometry*>& geos,
                     const std::vector<Constraint*>& constraints) {
    GCSsys.clear();
    addGeometryToGCS(geos);
    addConstraintsToGCS(constraints);
    return GCSsys.dofsNumber();
}
void Sketch::getRedundant(std::vector<int>& out) const {
    GCSsys.getRedundant(out);
}
"""),
    ("src/Mod/Sketcher/App/Sketch.h", "cpp", "class", "Sketch",
     """
class Sketch {
public:
    int solve();
    int initMove(const std::vector<Part::Geometry*>& geos,
                 const std::vector<Constraint*>& constraints);
    void getRedundant(std::vector<int>& out) const;
    void updateNonDrivingConstraints();
private:
    GCS::GCS GCSsys;
    std::vector<int> redundant;
    std::vector<int> conflictingConstraintIndices;
    void addGeometryToGCS(const std::vector<Part::Geometry*>& geos);
    void addConstraintsToGCS(const std::vector<Constraint*>& constraints);
    void handleRedundantConstraints(const std::vector<int>& redundant);
};
"""),
    ("src/Mod/Sketcher/App/planegcs/GCS.cpp", "cpp", "function", "GCS::solve",
     """
int GCS::solve(SubSystem* subsystem, bool isFine, Algorithm alg) {
    switch (alg) {
    case DogLeg:           return solve_DL(subsystem);
    case LevenbergMarquardt: return solve_LM(subsystem);
    case BFGS:             return solve_BFGS(subsystem);
    }
    return Failed;
}
int GCS::solve_DL(SubSystem* subsystem) {
    // Dog-leg trust-region method
    Eigen::VectorXd x, xnew, g, h_sd, h_gn, h_dl;
    subsystem->fillParams(x);
    double f = subsystem->error();
    for (int iter = 0; iter < MaxIterations; iter++) {
        if (f < XconvergenceFine) return Success;
        subsystem->calcJacobian(jacobianMatrix);
        g = jacobianMatrix.transpose() * subsystem->getResiduals();
        double alpha = g.squaredNorm() / (jacobianMatrix * g).squaredNorm();
        h_sd = -alpha * g;
        // trust region update omitted for brevity
    }
    return Failed;
}
int GCS::solve_LM(SubSystem* subsystem) {
    // Levenberg-Marquardt optimizer
    Eigen::VectorXd x;
    subsystem->fillParams(x);
    double lambda = 1e-3;
    for (int iter = 0; iter < MaxIterations; iter++) {
        subsystem->calcJacobian(jacobianMatrix);
        Eigen::MatrixXd JtJ = jacobianMatrix.transpose() * jacobianMatrix;
        JtJ += lambda * Eigen::MatrixXd::Identity(JtJ.rows(), JtJ.cols());
        Eigen::VectorXd step = JtJ.ldlt().solve(-jacobianMatrix.transpose() * subsystem->getResiduals());
        // update and adjust lambda
    }
    return Failed;
}
void GCS::getRedundant(std::vector<int>& redundant) const {
    Eigen::FullPivLU<Eigen::MatrixXd> lu(jacobianMatrix);
    // detect linearly dependent rows in constraint Jacobian
    redundant.clear();
    for (int i = 0; i < jacobianMatrix.rows(); i++) {
        if (lu.rank() < i + 1)
            redundant.push_back(i);
    }
}
int GCS::dofsNumber() const {
    return static_cast<int>(params.size()) - static_cast<int>(constraints.size()) + redundantCount;
}
void GCS::applySolution() {
    for (auto* sys : subSystems)
        sys->applySolution();
}
"""),
    ("src/Mod/Sketcher/App/planegcs/GCS.h", "cpp", "class", "GCS",
     """
class GCS {
public:
    enum SolveStatus { Success = 0, Converged = 1, Failed = -1 };
    enum Algorithm { DogLeg, LevenbergMarquardt, BFGS };
    int solve(SubSystem* subsystem = nullptr, bool isFine = true,
              Algorithm alg = DogLeg);
    int solve_DL(SubSystem* subsystem);
    int solve_LM(SubSystem* subsystem);
    int solve_BFGS(SubSystem* subsystem);
    void getRedundant(std::vector<int>& redundant) const;
    int dofsNumber() const;
    void applySolution();
    void clear();
    int MaxIterations = 100;
    double XconvergenceFine = 1e-10;
private:
    Eigen::MatrixXd jacobianMatrix;
    std::vector<double*> params;
    std::vector<Constraint*> constraints;
    std::vector<SubSystem*> subSystems;
    int redundantCount = 0;
};
"""),
    ("src/Mod/Sketcher/App/planegcs/Constraints.h", "cpp", "class", "Constraint",
     """
class Constraint {
public:
    virtual double error() = 0;
    virtual double grad(double*) = 0;
    virtual void rescale(double coef = 1.0) {}
    ConstraintType getTag() const { return tag; }
protected:
    ConstraintType tag;
};
class ConstraintCoincident : public Constraint {
public:
    ConstraintCoincident(Point& p1, Point& p2);
    double error() override;
    double grad(double* param) override;
};
class ConstraintParallel : public Constraint {
public:
    ConstraintParallel(Line& l1, Line& l2);
    double error() override;
    double grad(double* param) override;
};
class ConstraintPerpendicular : public Constraint {
public:
    ConstraintPerpendicular(Line& l1, Line& l2);
    double error() override;
    double grad(double* param) override;
};
class ConstraintDistance : public Constraint {
public:
    ConstraintDistance(Point& p1, Point& p2, double* d);
    double error() override;
    double grad(double* param) override;
};
"""),
    ("src/Mod/Sketcher/App/planegcs/SubSystem.cpp", "cpp", "class", "SubSystem",
     """
SubSystem::SubSystem(std::vector<Constraint*>& cons, std::vector<double*>& params)
    : constraints(cons), params(params) {}
double SubSystem::error() {
    double err = 0.0;
    for (auto* c : constraints)
        err += c->error() * c->error();
    return 0.5 * err;
}
void SubSystem::calcJacobian(Eigen::MatrixXd& J) {
    J.setZero(constraints.size(), params.size());
    for (int i = 0; i < (int)constraints.size(); i++)
        for (int j = 0; j < (int)params.size(); j++)
            J(i, j) = constraints[i]->grad(params[j]);
}
void SubSystem::fillParams(Eigen::VectorXd& x) const {
    x.resize(params.size());
    for (int i = 0; i < (int)params.size(); i++)
        x[i] = *params[i];
}
Eigen::VectorXd SubSystem::getResiduals() const {
    Eigen::VectorXd r(constraints.size());
    for (int i = 0; i < (int)constraints.size(); i++)
        r[i] = constraints[i]->error();
    return r;
}
void SubSystem::applySolution() {
    for (int i = 0; i < (int)params.size(); i++)
        *params[i] = solution[i];
}
"""),
    ("src/Mod/Sketcher/Gui/ViewProviderSketch.cpp", "cpp", "function",
     "ViewProviderSketch::updateData",
     """
void ViewProviderSketch::updateData(const App::Property* prop) {
    Gui::ViewProvider2D::updateData(prop);
    if (prop == &getSketchObject()->Geometry ||
        prop == &getSketchObject()->Constraints) {
        draw(false);
        signalConstraintsChanged();
    }
}
void ViewProviderSketch::draw(bool temp) {
    drawConstraints();
    drawGeometry();
    drawEdit(temp);
}
SketchObject* ViewProviderSketch::getSketchObject() const {
    return static_cast<Sketcher::SketchObject*>(pcObject);
}
void ViewProviderSketch::drawConstraints() {
    // Render constraint icons in 3D view
}
"""),
    ("src/Mod/Sketcher/Gui/CommandSketcherTools.cpp", "cpp", "function",
     "CmdSketcherConstrainCoincident::activated",
     """
void CmdSketcherConstrainCoincident::activated(int iMsg) {
    Q_UNUSED(iMsg);
    SketchObject* Sketch = sketchViewProvider->getSketchObject();
    const std::vector<Gui::SelectionObject>& selection =
        Gui::Selection().getSelectionEx(nullptr, Sketcher::SketchObject::getClassTypeId());
    if (selection.empty()) return;
    openCommand(QT_TRANSLATE_NOOP("Command", "Add coincident constraint"));
    Gui::cmdAppObjectArgs(Sketch,
        "addConstraint(Sketcher.Constraint('Coincident', %d, %d, %d, %d))",
        firstPointId, firstPointPos, secondPointId, secondPointPos);
    commitCommand();
    tryAutoRecompute(Sketch);
}
"""),
    ("src/Mod/FEM/App/FemMesh.cpp", "cpp", "function", "FemMesh::read",
     """
void FemMesh::read(const char* fileName) {
    SMESH_Mesh* mesh = myMesh->GetMeshDS();
    SMESH_Reader reader;
    reader.read(fileName, mesh);
    updateSMESH();
}
void FemMesh::write(const char* fileName) const {
    SMESH_Writer writer;
    writer.write(myMesh, fileName);
}
int FemMesh::getNodeCount() const {
    return myMesh->GetMeshDS()->NbNodes();
}
int FemMesh::getElementCount() const {
    return myMesh->GetMeshDS()->NbElements();
}
"""),
    ("src/Mod/FEM/App/FemMesh.h", "cpp", "class", "FemMesh",
     """
class FemExport FemMesh : public App::GeoFeature {
public:
    void read(const char* fileName);
    void write(const char* fileName) const;
    int getNodeCount() const;
    int getElementCount() const;
    SMESH_Mesh* getSMesh() const { return myMesh; }
private:
    SMESH_Mesh* myMesh = nullptr;
    void updateSMESH();
};
"""),
    ("src/Mod/FEM/App/FemAnalysis.cpp", "cpp", "class", "FemAnalysis",
     """
void FemAnalysis::addObject(App::DocumentObject* obj) {
    Group.setValues({obj});
}
std::vector<App::DocumentObject*> FemAnalysis::getSolvers() const {
    std::vector<App::DocumentObject*> solvers;
    for (auto* obj : Group.getValues())
        if (obj->isDerivedFrom(FemSolver::getClassTypeId()))
            solvers.push_back(obj);
    return solvers;
}
void FemAnalysis::run() {
    for (auto* solver : getSolvers())
        static_cast<FemSolver*>(solver)->solve();
}
"""),
    ("src/Mod/FEM/Gui/TaskFemConstraint.cpp", "cpp", "function",
     "TaskFemConstraint::onSelectionChanged",
     """
void TaskFemConstraint::changeEvent(QEvent* e) {
    TaskBox::changeEvent(e);
    if (e->type() == QEvent::LanguageChange)
        ui->retranslateUi(this);
}
void TaskFemConstraint::onButtonReference(bool checked) {
    if (checked) {
        Gui::Selection().clearSelection();
        connectSelection();
    }
}
void TaskFemConstraint::onSelectionChanged(const Gui::SelectionChanges& msg) {
    if (msg.Type == Gui::SelectionChanges::AddSelection)
        setReference(msg.pObjectName, msg.pSubName);
}
"""),
    ("src/Mod/TechDraw/App/DrawPage.cpp", "cpp", "function", "DrawPage::addView",
     """
void DrawPage::addView(DrawView* view) {
    Views.insert(Views.getValues().end(), view);
    view->setPage(this);
    requestPaint();
}
void DrawPage::requestPaint() {
    signalGuiPaint(this);
}
double DrawPage::getPageWidth() const {
    return PageWidth.getValue();
}
double DrawPage::getPageHeight() const {
    return PageHeight.getValue();
}
"""),
    ("src/Mod/TechDraw/App/DrawViewPart.cpp", "cpp", "function",
     "DrawViewPart::execute",
     """
App::DocumentObjectExecReturn* DrawViewPart::execute() {
    Part::TopoShape ts = getSourceShape();
    HLRBRep_Algo* brep_hlr = new HLRBRep_Algo();
    brep_hlr->Add(ts.getShape());
    gp_Ax2 transform(getViewAxis());
    HLRBRep_HLRToShape shapes(brep_hlr);
    visibleEdges = shapes.VCompound();
    hiddenEdges  = shapes.HCompound();
    return App::DocumentObject::StdReturn;
}
"""),
    ("src/Mod/Path/App/Area.cpp", "cpp", "function", "Area::build",
     """
void Area::build() {
    myArea.clean();
    for (auto& shape : myShapes) {
        ClipperLib::Paths paths;
        toClipperPaths(shape, paths);
        myArea.add(paths, myOp);
    }
    myArea.build();
}
TopoDS_Shape Area::getShape(int index) const {
    ClipperLib::Paths result;
    myArea.getCombinedPaths(result);
    return fromClipperPaths(result);
}
void Area::setParams(const AreaParams& params) {
    myParams = params;
    build();
}
"""),
    ("src/Base/Writer.cpp", "cpp", "class", "Writer",
     """
Writer::Writer(const char* FileName) {
    FileStream.open(FileName, std::ios::out | std::ios::binary);
    ofs = &FileStream;
}
void Writer::Stream(const char* str) {
    *ofs << str;
}
void Writer::beginCharStream(bool base64) {
    *ofs << "<CharData>";
}
void Writer::endCharStream() {
    *ofs << "</CharData>";
}
void Writer::incInd() { indentation += "  "; }
void Writer::decInd() { if (indentation.size() >= 2) indentation.resize(indentation.size()-2); }
"""),
    ("src/Base/Reader.cpp", "cpp", "class", "Reader",
     """
Reader::Reader(const char* FileName) {
    FileStream.open(FileName, std::ios::in | std::ios::binary);
    ifs = &FileStream;
}
std::string Reader::readLine() {
    std::string line;
    std::getline(*ifs, line);
    return line;
}
bool Reader::isGood() const {
    return ifs && ifs->good();
}
"""),
    ("src/Base/XMLWriter.cpp", "cpp", "class", "XMLWriter",
     """
XMLWriter::XMLWriter(const char* FileName) : Writer(FileName) {
    *ofs << "<?xml version='1.0' encoding='utf-8'?>\n";
    *ofs << "<Document SchemaVersion=\"4\">\n";
}
void XMLWriter::writeElement(const char* tag, const char* val) {
    *ofs << "<" << tag << ">" << encodeXML(val) << "</" << tag << ">\n";
}
void XMLWriter::beginElement(const char* tag) {
    *ofs << "<" << tag << ">\n";
    indent++;
}
void XMLWriter::endElement(const char* tag) {
    indent--;
    *ofs << "</" << tag << ">\n";
}
void XMLWriter::writeAttribute(const char* name, const char* val) {
    *ofs << " " << name << "=\"" << encodeXML(val) << "\"";
}
"""),
    ("src/Base/XMLReader.cpp", "cpp", "class", "XMLReader",
     """
XMLReader::XMLReader(const char* FileName) : Reader(FileName) {
    parseDocument();
}
void XMLReader::readElement(const char* tag) {
    while (!reader.isStartElement(tag))
        reader.next();
}
std::string XMLReader::getAttribute(const char* name) const {
    return reader.attributeValue(name).toStdString();
}
int XMLReader::getAttributeAsInteger(const char* name, const char* def) const {
    std::string v = getAttribute(name);
    return v.empty() ? std::stoi(def) : std::stoi(v);
}
"""),
    ("src/Base/Persistence.cpp", "cpp", "class", "Persistence",
     """
void Persistence::save(Writer& writer) const {
    writer.Stream() << writer.ind() << "<Properties Count=\""
                    << getPropertyCount() << "\">\n";
    writer.incInd();
    for (const auto& pair : getPropertyMap())
        pair.second->save(writer);
    writer.decInd();
    writer.Stream() << writer.ind() << "</Properties>\n";
}
void Persistence::restore(XMLReader& reader) {
    reader.readElement("Properties");
    int count = reader.getAttributeAsInteger("Count", "0");
    for (int i = 0; i < count; i++) {
        reader.readElement("Property");
        std::string name = reader.getAttribute("name");
        Property* prop = getPropertyByName(name.c_str());
        if (prop) prop->restore(reader);
    }
}
"""),
    ("src/Base/FileInfo.cpp", "cpp", "function", "FileInfo::extension",
     """
std::string FileInfo::extension() const {
    auto pos = FileName.rfind('.');
    if (pos == std::string::npos) return "";
    return FileName.substr(pos + 1);
}
bool FileInfo::exists() const {
    return std::filesystem::exists(FileName);
}
std::string FileInfo::dirPath() const {
    return std::filesystem::path(FileName).parent_path().string();
}
bool FileInfo::hasExtension(const char* ext) const {
    return extension() == ext;
}
"""),
    ("src/Base/PyObjectBase.cpp", "cpp", "class", "PyObjectBase",
     """
PyObject* PyObjectBase::repr() {
    std::stringstream str;
    str << "<" << getTypeName() << " object at " << (void*)this << ">";
    return Py_BuildValue("s", str.str().c_str());
}
PyObject* PyObjectBase::getattr(const char* attr) {
    if (strcmp(attr, "__class__") == 0)
        return PyObject_GetAttrString((PyObject*)this, "__class__");
    return PyObject_GenericGetAttr((PyObject*)this, PyUnicode_FromString(attr));
}
void PyObjectBase::setCustomAttributes(const char* attr, PyObject* obj) {
    // Subclasses intercept attribute setting here
}
int PyObjectBase::setattr(const char* attr, PyObject* value) {
    return PyObject_GenericSetAttr((PyObject*)this, PyUnicode_FromString(attr), value);
}
"""),
    ("src/Gui/SelectionView.cpp", "cpp", "function", "SelectionView::onSelectionChanged",
     """
void SelectionView::onSelectionChanged(const Gui::SelectionChanges& msg) {
    if (msg.Type == SelectionChanges::AddSelection) {
        QListWidgetItem* item = new QListWidgetItem(
            QString::fromStdString(msg.pObjectName));
        selectionList->addItem(item);
    } else if (msg.Type == SelectionChanges::ClrSelection) {
        selectionList->clear();
    }
}
void SelectionView::setMode(int mode) {
    selectionMode = mode;
    Gui::Selection().setPreselect(nullptr, nullptr, nullptr, 0, 0, 0);
}
"""),

    # ── Python retrieval system (DSEL) ────────────────────────────────────
    ("src/retrieval/database.py", "python", "class", "SQLiteUnifiedStore",
     """
class UnifiedStore(ABC):
    @abstractmethod
    def vector_search(self, query, user_tier, repo_scope=None, top_k=20): pass
    @abstractmethod
    def graph_search(self, query, user_tier, repo_scope=None, depth=3, breadth=50): pass

class SQLiteUnifiedStore(UnifiedStore):
    def vector_search(self, query, user_tier, repo_scope=None, top_k=20):
        query_embedding = self.embedding_provider.embed(query)
        rows = self._select_allowed_artifacts(user_tier, repo_scope)
        scored = []
        query_terms = self._signal_terms(query)
        for row in rows:
            embedding = json.loads(row['embedding'])
            cosine = self._cosine(query_embedding, embedding)
            keyword_score = sum(1 for term in query_terms if term in row['text'].lower()) * 0.05
            item = self._row_to_dict(row)
            item['score'] = cosine + keyword_score
            scored.append(item)
        scored.sort(key=lambda x: x['score'], reverse=True)
        return scored[:top_k]

    def graph_search(self, query, user_tier, repo_scope=None, depth=3, breadth=50):
        allowed = {row['id']: row for row in self._select_allowed_artifacts(user_tier, repo_scope)}
        anchors = self._find_anchor_ids(query, allowed)
        seen, queue, ordered_ids = set(), [(a,0) for a in anchors if a in allowed], []
        while queue and len(ordered_ids) < breadth:
            artifact_id, current_depth = queue.pop(0)
            if artifact_id in seen or artifact_id not in allowed: continue
            seen.add(artifact_id); ordered_ids.append(artifact_id)
            if current_depth >= depth: continue
            for edge in self._outgoing_edges(artifact_id):
                if edge['target_id'] in allowed and edge['target_id'] not in seen:
                    queue.append((edge['target_id'], current_depth+1))
        return [self._row_to_dict(allowed[aid]) for aid in ordered_ids]

    def upsert_artifacts(self, artifacts):
        # INSERT OR UPDATE into artifacts table
        # fields: id, repository, file_path, language, text, tier, fidelity,
        #         symbol_name, line_start, line_end, kind, embedding, metadata, updated_at
        pass

    def _signal_terms(self, query):
        return {t for t in HashingEmbeddingProvider._tokens(query)
                if t not in QUERY_STOPWORDS and len(t) > 1}

    def _outgoing_edges(self, artifact_id):
        priority = {'calls':0,'defines':1,'imports':2,'inherits':3,'uses':4,'bridges':5}
        rows = list(self._connection.execute(
            'SELECT source_id, target_id, relationship FROM edges WHERE source_id=?', (artifact_id,)))
        rows.sort(key=lambda r: priority.get(r['relationship'], 10))
        return rows

    @staticmethod
    def _cosine(left, right):
        return float(sum(a*b for a,b in zip(left, right)))
"""),

    ("src/retrieval/database.py", "python", "class", "HashingEmbeddingProvider",
     """
class HashingEmbeddingProvider:
    def __init__(self, dimensions=128):
        self.dimensions = dimensions

    def embed(self, text):
        vector = [0.0] * self.dimensions
        for token in self._tokens(text):
            digest = hashlib.sha256(token.encode('utf-8')).digest()
            index = int.from_bytes(digest[:4], 'big') % self.dimensions
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign
        norm = math.sqrt(sum(v*v for v in vector))
        if norm == 0:
            return vector
        return [v/norm for v in vector]

    @staticmethod
    def _tokens(text):
        return re.findall(r'[A-Za-z_][A-Za-z0-9_]*', text.lower())

@dataclass(frozen=True)
class ArtifactRecord:
    artifact_id: str
    repository: str
    file_path: str
    language: str
    text: str
    tier: int
    fidelity: str
    symbol_name: Optional[str] = None
    line_start: int = 1
    line_end: int = 1
    kind: str = 'chunk'
    metadata: Dict[str, Any] = field(default_factory=dict)

QUERY_STOPWORDS = {'a','an','and','are','artifact','as','at','be','by','does','file',
                   'for','from','in','is','it','of','on','or','the','to','what','where',
                   'which','with','symbol','repository','defined','indexed'}
"""),

    ("src/retrieval/hybrid.py", "python", "class", "HybridSearcher",
     """
class HybridSearcher:
    def __init__(self, store, lambda_ratio=0.5, vector_top_k=20, graph_depth=3, graph_breadth=50):
        self.store = store
        self.lambda_ratio = lambda_ratio
        self.vector_top_k = vector_top_k
        self.graph_depth = graph_depth
        self.graph_breadth = graph_breadth

    def search(self, query, user_tier, repo_scope=None):
        if self.lambda_ratio == 1.0:
            return self.store.vector_search(query, user_tier, repo_scope, self.vector_top_k)
        elif self.lambda_ratio == 0.0:
            return self.store.graph_search(query, user_tier, repo_scope, self.graph_depth, self.graph_breadth)
        else:
            v_res = self.store.vector_search(query, user_tier, repo_scope, self.vector_top_k)
            g_res = self.store.graph_search(query, user_tier, repo_scope, self.graph_depth, self.graph_breadth)
            results, seen = [], set()
            vector_slots = max(1, int(len(v_res) * self.lambda_ratio))
            for doc in v_res[:vector_slots] + g_res + v_res[vector_slots:]:
                if doc['id'] not in seen:
                    seen.add(doc['id']); results.append(doc)
            return results
"""),

    ("src/retrieval/assembler.py", "python", "class", "PromptAssembler",
     """
class PromptAssembler:
    def __init__(self, system_rule=None):
        self.system_rule = system_rule

    def _u_shape_order(self, chunks):
        left, right = [], []
        for i, chunk in enumerate(chunks):
            if i % 2 == 0: left.append(chunk)
            else: right.append(chunk)
        return left + right[::-1]

    def assemble(self, query, chunks):
        parts = []
        if self.system_rule:
            parts.append(self.system_rule)
        if chunks:
            parts.append('Context:')
            for chunk in self._u_shape_order(chunks):
                fp, lang, tier, text = chunk.get('file_path'), chunk.get('language'), chunk.get('tier'), chunk.get('text','')
                parts.append(f'--- File: {fp} | Language: {lang} | Tier: {tier} ---')
                parts.append(text)
        parts.append(f'Query: {query}')
        return '\\n'.join(parts)
"""),

    ("src/retrieval/reranker.py", "python", "class", "LexicalReranker",
     """
class LexicalReranker:
    STOPWORDS = {'a','an','and','are','the','to','in','is','it','of','for','with'}

    def rerank(self, query, chunks, top_m=8):
        query_terms = self._terms(query)
        scored = []
        for chunk in chunks:
            searchable = ' '.join(str(chunk.get(f,'')) for f in ('id','symbol_name','file_path','kind','text')).lower()
            overlap_score = len(query_terms & self._terms(searchable, keep_stopwords=True))
            symbol = str(chunk.get('symbol_name') or '').lower()
            file_path = str(chunk.get('file_path') or '').lower()
            file_basename = file_path.split('/')[-1] if file_path else ''
            exact_symbol_score = 4 if symbol and symbol in query.lower() else 0
            file_score = (8 if file_path and file_path in query.lower()
                          else 5 if file_basename and file_basename in query.lower() else 0)
            score = overlap_score + exact_symbol_score + file_score
            c = chunk.copy(); c['rerank_score'] = float(score); scored.append(c)
        scored.sort(key=lambda x: (x['rerank_score'], x.get('score', 0.0)), reverse=True)
        return scored[:top_m]

    @classmethod
    def _terms(cls, text, keep_stopwords=False):
        terms = {t.lower() for t in re.findall(r'[A-Za-z_][A-Za-z0-9_.-]*', text) if t.strip()}
        return terms if keep_stopwords else {t for t in terms if t not in cls.STOPWORDS}
"""),

    ("src/ingestion/indexer.py", "python", "class", "RepositoryIndexer",
     """
class RepositoryIndexer:
    def __init__(self, store):
        self.store = store

    def index_repository(self, repo_name, repo_path):
        records = []
        for path in Path(repo_path).rglob('*'):
            if path.suffix not in {'.py', '.cpp', '.h', '.c', '.rs', '.go'}: continue
            if path.is_file():
                text = path.read_text(errors='ignore')
                artifact_id = hashlib.sha256(f'{repo_name}:{path}'.encode()).hexdigest()[:32]
                records.append(ArtifactRecord(
                    artifact_id=artifact_id, repository=repo_name,
                    file_path=str(path.relative_to(repo_path)),
                    language=path.suffix.lstrip('.'), text=text[:4096],
                    tier=1, fidelity='full', kind='chunk',
                ))
        self.store.upsert_artifacts(records)
"""),
]


def build_corpus(db_path: Path):
    from src.retrieval.database import (
        SQLiteUnifiedStore, HashingEmbeddingProvider, ArtifactRecord,
    )

    db_path.parent.mkdir(parents=True, exist_ok=True)
    store = SQLiteUnifiedStore(db_path, HashingEmbeddingProvider())
    store.delete_repository("freecad")

    records = []
    for file_path, lang, kind, symbol, text in CORPUS:
        uid = hashlib.sha256(f"freecad:{file_path}:{symbol}".encode()).hexdigest()[:32]
        lines = text.strip().splitlines()
        records.append(ArtifactRecord(
            artifact_id=uid,
            repository="freecad",
            file_path=file_path,
            language=lang,
            text=text.strip(),
            tier=1,
            fidelity="high",
            symbol_name=symbol,
            line_start=1,
            line_end=len(lines),
            kind=kind,
            metadata={"source": "synthetic_corpus"},
        ))

    store.upsert_artifacts(records)
    print(f"[corpus] Indexed {len(records)} FreeCAD artifacts into {db_path}")
    return store


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(ROOT / ".cis" / "index.db"))
    args = ap.parse_args()
    build_corpus(Path(args.db))
