import sys
import time
import threading
import Queue

from direct.showbase.ShowBase import ShowBase
from panda3d.core import TransparencyAttrib, GeomNode, Mat4, RigidBodyCombiner
from pandac import PandaModules as pm

import numpy
import collada
from meshtool.filters.panda_filters import pandacore
from meshtool.filters.panda_filters.pandacontrols import KeyboardMovement, MouseDrag, MouseScaleZoom, MouseCamera

import open3dhub
import scene

load_queue = Queue.Queue()

class LoadingThread(threading.Thread):
    def _run(self):
        demo_models = scene.get_demo_models()
        print 'Loaded', len(demo_models), 'models'
        mesh = open3dhub.get_mesh(demo_models[75], 'optimized')
        load_queue.put(mesh)

    def run(self):
        try:
            self._run()
        except (KeyboardInterrupt, SystemExit):
            return

class MyBase(ShowBase):
    def userExit(self):
        sys.exit(0)

def checkForLoad(task):
    try:
        mesh = load_queue.get_nowait()
    except Queue.Empty:
        mesh = None
    
    if mesh is None:
        return task.cont
    
    print 'Loading model', mesh
    scene_members = pandacore.getSceneMembers(mesh)
    rotateNode = GeomNode("rotater")
    rotatePath = render.attachNewNode(rotateNode)
    matrix = numpy.identity(4)
    if mesh.assetInfo.upaxis == collada.asset.UP_AXIS.X_UP:
        r = collada.scene.RotateTransform(0,1,0,90)
        matrix = r.matrix
    elif mesh.assetInfo.upaxis == collada.asset.UP_AXIS.Y_UP:
        r = collada.scene.RotateTransform(1,0,0,90)
        matrix = r.matrix
    rotatePath.setMat(Mat4(*matrix.T.flatten().tolist()))
    
    rbc = RigidBodyCombiner('combiner')
    rbcPath = rotatePath.attachNewNode(rbc)
    
    for geom, renderstate, mat4 in scene_members:
        node = GeomNode("primitive")
        node.addGeom(geom)
        if renderstate is not None:
            node.setGeomState(0, renderstate)
        geomPath = rbcPath.attachNewNode(node)
        geomPath.setMat(mat4)
        
    rbc.collect()
    
    wrappedNode = pandacore.centerAndScale(rotatePath)
    
    print 'Model loaded.'
    
    return task.cont

base = MyBase()
render = base.render
taskMgr = base.taskMgr

base.disableMouse()
pandacore.attachLights(render)
render.setShaderAuto()
render.setTransparency(TransparencyAttrib.MDual, 1)

base.cam.setPos(1500, -1500, 1)
base.cam.lookAt(0.0, 0.0, 0.0)

t = LoadingThread()
t.daemon = True
t.start()

taskMgr.add(checkForLoad, "checkForLoad")

KeyboardMovement()
MouseCamera()

base.run()
