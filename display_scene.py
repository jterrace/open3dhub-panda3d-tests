import os
import sys
import time
import threading
import Queue
from multiprocessing.pool import Pool
import multiprocessing
import random
import tempfile
import shutil
import math
import heapq

from direct.showbase.ShowBase import ShowBase
from panda3d.core import TransparencyAttrib, RigidBodyCombiner, AntialiasAttrib
from panda3d.core import StringStream, NodePath, GeomNode
from panda3d.core import Mat4, VBase4, Vec3
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
loader = None

load_queue = Queue.Queue()

CURDIR = os.path.dirname(__file__)
TEMPDIR = os.path.join(CURDIR, '.temp_models')

FORCE_DOWNLOAD = None
MODEL_TYPE = None
NUM_MODELS = None
SEED = None
NUM_DOWNLOAD_PROCS = 2
NUM_LOAD_PROCS = multiprocessing.cpu_count()

MAX_SOLID_ANGLE = 4.0 * math.pi
def solid_angle(cameraLoc, objLoc, objRadius):
    """Calculates the solid angle between the camera and an object"""
    
    to_center = cameraLoc - objLoc
    
    to_center_len = to_center.length()
    if to_center_len <= objRadius:
        return MAX_SOLID_ANGLE
    
    sin_alpha = objRadius / to_center_len
    cos_alpha = math.sqrt(1.0 - sin_alpha * sin_alpha)
    return 2.0 * math.pi * (1.0 - cos_alpha)

class Model(object):
    def __init__(self, model_json, x, y, z, scale):
        self.model_json = model_json
        self.x = x
        self.y = y
        self.z = z
        self.scale = scale
        self.bam_file = None
        self.solid_angle = 0.0
        self.data = None
        self.subfiles = None
    
    def __str__(self):
        return "<Model '%s' at (%.7g,%.7g,%.7g) scale %.7g>" % (self.model_json['base_path'], self.x, self.y, self.z, self.scale)
    def __repr__(self):
        return str(self)
        
def load_model(model):
    
    mesh = open3dhub.load_mesh(model.data, model.subfiles)
    mesh.data = None
    mesh.subfiles = None
    print 'got mesh', mesh
    scene_members = pandacore.getSceneMembers(mesh)
    print 'got', len(scene_members), 'members'
    
    rotateNode = GeomNode("rotater")
    rotatePath = NodePath(rotateNode)
    matrix = numpy.identity(4)
    if mesh.assetInfo.upaxis == collada.asset.UP_AXIS.X_UP:
        r = collada.scene.RotateTransform(0,1,0,90)
        matrix = r.matrix
    elif mesh.assetInfo.upaxis == collada.asset.UP_AXIS.Y_UP:
        r = collada.scene.RotateTransform(1,0,0,90)
        matrix = r.matrix
    rotatePath.setMat(Mat4(*matrix.T.flatten().tolist()))
    
    #rbc = RigidBodyCombiner('combiner')
    #rbcPath = rotatePath.attachNewNode(rbc)
    
    for geom, renderstate, mat4 in scene_members:
        node = GeomNode("primitive")
        node.addGeom(geom)
        if renderstate is not None:
            node.setGeomState(0, renderstate)
        geomPath = rotatePath.attachNewNode(node)
        geomPath.setMat(mat4)
        
    #rbc.collect()
    rotatePath.flattenStrong()
    
    wrappedNode = pandacore.centerAndScale(rotatePath)
    wrappedNode.setPos(model.x, model.y, model.z)
    wrappedNode.setScale(model.scale, model.scale, model.scale)
    minPt, maxPt = wrappedNode.getTightBounds()
    zRange = math.fabs(minPt.getZ() - maxPt.getZ())
    wrappedNode.setPos(model.x, model.y, zRange / 2.0)
    
    bam_temp = tempfile.mktemp('.bam', dir=TEMPDIR)
    wrappedNode.writeBamFile(bam_temp)
    model.bam_file = bam_temp
    
    print 'returning bam file', bam_temp
    
    return model

def download_model(model):
    (data, subfile_dict) = open3dhub.download_mesh(model.model_json, MODEL_TYPE)
    model.data = data
    model.subfiles = subfile_dict
    return model

def check_waiting(waiting):
    finished = []
    new_waiting = []
    for res in waiting:
        if res.ready():
            finished.append(res)
        else:
            new_waiting.append(res)
    return finished, new_waiting

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
        
        to_download = []    
        for model_index in chosen:
            model = Model(demo_models[model_index],
                                random.uniform(-10000, 10000),
                                random.uniform(-10000, 10000),
                                0,
                                random.uniform(0.5, 6.0))
            model.solid_angle = solid_angle(Vec3(0, 30000, 10000), Vec3(model.x, model.y, model.z), model.scale * 1000)
            to_download.append((-1 * model.solid_angle, model))
            
        heapq.heapify(to_download)
        
        downloading_pool = Pool(NUM_DOWNLOAD_PROCS)
        loading_pool = Pool(NUM_LOAD_PROCS)
        downloading = []
        to_load = []
        loading = []
        
        while len(to_download) > 0 or len(downloading) > 0 or len(loading) > 0:
            finished_downloading, downloading = check_waiting(downloading)
            finished_loading, loading = check_waiting(loading)
            
            while len(downloading) < NUM_DOWNLOAD_PROCS and len(to_download) > 0:
                priority, model = heapq.heappop(to_download)
                downloading.append(downloading_pool.apply_async(download_model, (model,)))
            
            for res in finished_downloading:
                print 'finished a download', len(to_download) + len(downloading), 'left'
                model = res.get()
                heapq.heappush(to_load, (-1 * model.solid_angle, model))
            
            while len(loading) < NUM_LOAD_PROCS and len(to_load) > 0:
                priority, model = heapq.heappop(to_load)
                loading.append(loading_pool.apply_async(load_model, (model,)))
            
            for res in finished_loading:
                print 'finished loading a model', len(to_load) + len(loading), 'left'
                load_queue.put(res.get())
                
            time.sleep(0.05)
            
        print 'Finished loading all models'

    def run(self):
        try:
            self._run()
        except (KeyboardInterrupt, SystemExit):
            return

def modelLoaded(np):
    print 'Model loaded'
    np.reparentTo(render)

def checkForLoad(task):
    try:
        model = load_queue.get_nowait()
    except Queue.Empty:
        model = None
    
    if model is None:
        return task.cont

    loader.loadModel(model.bam_file, callback=modelLoaded)
    
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
    
    global base, render, taskMgr, loader
    base = MyBase()
    render = base.render
    taskMgr = base.taskMgr
    loader = base.loader
    
    try:
        shutil.rmtree(TEMPDIR)
    except OSError:
        pass
    os.mkdir(TEMPDIR)
    
    base.disableMouse()
    pandacore.attachLights(render)
    render.setShaderAuto()
    render.setTransparency(TransparencyAttrib.MDual, 1)
    
    base.cam.setPos(0, 30000, 10000)
    base.cam.lookAt(0, 0, 0.0)
    
    t = LoadingThread()
    t.daemon = True
    t.start()
    
    taskMgr.add(checkForLoad, "checkForLoad")
    
    KeyboardMovement()
    MouseCamera()
    
    base.win.setClearColor(VBase4(0.9,0.9,0.9,1))
    environ = loader.loadModel("models/environment")
    environ.reparentTo(render)
    minPt, maxPt = environ.getTightBounds()
    xRange = math.fabs(minPt.getX() - maxPt.getX())
    yRange = math.fabs(minPt.getY() - maxPt.getY())
    zRange = math.fabs(minPt.getZ() - maxPt.getZ())
    environ.setScale(30000 / xRange, 30000 / yRange, 1)
    environ.setPos(0, 0, -1 * zRange / 2.0)
    #environ.setPos(0, 0, -100)
    
    render.setAntialias(AntialiasAttrib.MAuto)
    
    base.run()

if __name__ == '__main__':
    main()
