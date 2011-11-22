import os
import sys
import time
import threading
import Queue
from multiprocessing.pool import Pool
import multiprocessing
import random
import shutil
import math

from direct.showbase.ShowBase import ShowBase
from panda3d.core import TransparencyAttrib, AntialiasAttrib, TextureAttrib, TextureStage
from panda3d.core import VBase4, Vec3
from panda3d.core import PNMImage, Texture, StringStream, GeomNode

import argparse
import collada
from meshtool.filters.panda_filters import pandacore
from meshtool.filters.panda_filters.pandacontrols import KeyboardMovement, MouseDrag, MouseScaleZoom, MouseCamera

import scene
import load_scheduler

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
        
        download_pool = load_scheduler.TaskPool(NUM_DOWNLOAD_PROCS)
        loader_pool = load_scheduler.TaskPool(NUM_LOAD_PROCS)
  
        for model_index in chosen:
            model = load_scheduler.Model(model_json = demo_models[model_index],
                                model_type = MODEL_TYPE,
                                x = random.uniform(-10000, 10000),
                                y = random.uniform(-10000, 10000),
                                z = 0,
                                scale = random.uniform(0.5, 6.0))
            model.solid_angle = solid_angle(Vec3(0, 30000, 10000), Vec3(model.x, model.y, model.z), model.scale * 1000)
            
            dt = load_scheduler.ModelDownloadTask(model, priority=model.solid_angle)
            download_pool.add_task(dt)
        
        while not(download_pool.empty() and loader_pool.empty()):
            finished_tasks = download_pool.poll() + loader_pool.poll()
            
            for finished_task in finished_tasks:
                print 'finished task', type(finished_task), 'has', len(finished_task.dependents), 'dependents'
                
                for dependent in finished_task.dependents:
                    if isinstance(dependent, load_scheduler.DownloadTask):
                        print 'adding a dependent download task'
                        download_pool.add_task(dependent)
                    elif isinstance(dependent, load_scheduler.LoadTask):
                        print 'adding a dependent load task'
                        loader_pool.add_task(dependent)
                    else:
                        print 'Unknown dependent type', type(dependent)
                    
                if isinstance(finished_task, load_scheduler.LoadTask):
                    print 'posting finished load task'
                    load_queue.put((ActionType.LOAD_MODEL, finished_task.model))
                elif isinstance(finished_task, load_scheduler.TextureDownloadTask):
                    load_queue.put((ActionType.UPDATE_TEXTURE, finished_task.model, finished_task.offset, finished_task.data))
                else:
                    print 'not doing anything for type', type(finished_task)
                
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

class ActionType(object):
    LOAD_MODEL = 0
    UPDATE_TEXTURE = 1

def checkForLoad(task):
    try:
        action = load_queue.get_nowait()
    except Queue.Empty:
        action = None
    
    if action is None:
        return task.cont

    action_type = action[0]
    
    if action_type == ActionType.LOAD_MODEL:
        model = action[1]
        loader.loadModel(model.bam_file, callback=modelLoaded)
    elif action_type == ActionType.UPDATE_TEXTURE:
        model = action[1]
        offset = action[2]
        data = action[3]
        print model.model_json['base_path'], 'needs texture updating offset', offset
        texpnm = PNMImage()
        texpnm.read(StringStream(data), 'something.jpg')
        newtex = Texture()
        newtex.load(texpnm)
        
        path_search = '**/' + model.model_json['base_path'].replace('/', '_') + '*'
        np = render.find(path_search)
        
        np.setTextureOff(1)
        np.setTexture(newtex, 1)
    
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
    
    render.setAntialias(AntialiasAttrib.MAuto)
    
    base.run()

if __name__ == '__main__':
    main()
