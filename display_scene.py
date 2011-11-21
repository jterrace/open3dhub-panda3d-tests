import sys
import time
import threading
import Queue
from multiprocessing.pool import ThreadPool
import random
import copy_reg
import types

from direct.showbase.ShowBase import ShowBase
from panda3d.core import TransparencyAttrib, GeomNode, Mat4, RigidBodyCombiner, VBase4
from pandac import PandaModules as pm

import argparse
import numpy
import collada
from meshtool.filters.panda_filters import pandacore
from meshtool.filters.panda_filters.pandacontrols import KeyboardMovement, MouseDrag, MouseScaleZoom, MouseCamera

import open3dhub
import scene

class MyBase(ShowBase):
    def userExit(self):
        sys.exit(0)

base = None
render = None
taskMgr = None

pool = ThreadPool(2)
load_queue = Queue.Queue()

FORCE_DOWNLOAD = None
MODEL_TYPE = None
NUM_MODELS = None
SEED = None

class Model(object):
    def __init__(self, model_json, x, y, z, scale):
        self.model_json = model_json
        self.x = x
        self.y = y
        self.z = z
        self.scale = scale
        self.mesh = None
    
    def __str__(self):
        return "<Model '%s' at (%.7g,%.7g,%.7g)>" % (self.model_json['base_path'], self.x, self.y, self.z)
    def __repr__(self):
        return str(self)
        
def load_model(model):
    mesh = open3dhub.get_mesh(model.model_json, MODEL_TYPE)
    model.mesh = mesh
    return model

class LoadingThread(threading.Thread):
    def _run(self):
        demo_models = scene.get_demo_models(force=FORCE_DOWNLOAD)
        print 'Loaded', len(demo_models), 'models'
        
        to_choose = range(len(demo_models))
        chosen = []
        while len(chosen) < NUM_MODELS:
            rand_index = random.randrange(len(to_choose))
            chosen_index = to_choose.pop(rand_index)
            chosen.append(chosen_index)
        
        models = []    
        for model_index in chosen:
            models.append(Model(demo_models[model_index],
                                random.uniform(-10000, 10000),
                                random.uniform(-10000, 10000),
                                0,
                                random.uniform(0.5, 3.0)))
        
        waiting_for = []
        for model in models:
            waiting_for.append(pool.apply_async(load_model, (model,)))
        
        while len(waiting_for) > 0:
            finished = []
            new_waiting = []
            for res in waiting_for:
                if res.ready():
                    finished.append(res)
                else:
                    new_waiting.append(res)
            waiting_for = new_waiting
            
            for res in finished:
                load_queue.put(res.get())
                
            time.sleep(0.1)

    def run(self):
        try:
            self._run()
        except (KeyboardInterrupt, SystemExit):
            return

def checkForLoad(task):
    try:
        model = load_queue.get_nowait()
    except Queue.Empty:
        model = None
    
    if model is None:
        return task.cont
    
    mesh = model.mesh
    
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
    wrappedNode.setPos(model.x, model.y, model.z)
    wrappedNode.setScale(model.scale, model.scale, model.scale)
    
    print 'Model loaded.'
    
    return task.cont

def main():
    
    parser = argparse.ArgumentParser(description='Tool for displaying a scene from open3dhub')
    
    parser.add_argument('--force-download', dest='force', action='store_true', help='Force re-downloading of model list')
    parser.add_argument('type', help='Model type to use', choices=['optimized', 'progressive'])
    parser.add_argument('num_models', help='Number of models to use', type=int)
    parser.add_argument('--seed', required=False, help='Seed for random number generator', type=str)
    
    args = parser.parse_args()
    
    global FORCE_DOWNLOAD
    global MODEL_TYPE
    global NUM_MODELS
    global SEED
    
    FORCE_DOWNLOAD = args.force
    MODEL_TYPE = args.type
    NUM_MODELS = args.num_models
    SEED = args.seed
    
    if SEED is not None:
        random.seed(SEED)
    
    global base, render, taskMgr
    base = MyBase()
    render = base.render
    taskMgr = base.taskMgr
    
    base.disableMouse()
    pandacore.attachLights(render)
    render.setShaderAuto()
    render.setTransparency(TransparencyAttrib.MDual, 1)
    
    base.cam.setPos(0, 30000, 15000)
    base.cam.lookAt(0, 0, 0.0)
    
    t = LoadingThread()
    t.daemon = True
    t.start()
    
    taskMgr.add(checkForLoad, "checkForLoad")
    
    KeyboardMovement()
    MouseCamera()
    
    base.run()

if __name__ == '__main__':
    main()
