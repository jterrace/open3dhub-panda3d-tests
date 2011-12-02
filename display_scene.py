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
from direct.gui.OnscreenText import OnscreenText
from panda3d.core import TransparencyAttrib, AntialiasAttrib, TextureAttrib, TextureStage
from panda3d.core import VBase4, Vec3
from panda3d.core import PNMImage, Texture, StringStream, GeomNode
from panda3d.core import GeomVertexRewriter, GeomVertexWriter, GeomVertexReader

import argparse
import collada
from meshtool.filters.panda_filters import pandacore
from meshtool.filters.panda_filters.pandacontrols import KeyboardMovement, MouseDrag, MouseScaleZoom, MouseCamera
from meshtool.filters.panda_filters.pdae_utils import PM_OP

import scene
import load_scheduler

base = None
render = None
taskMgr = None
loader = None

load_queue = Queue.Queue()

CURDIR = os.path.dirname(__file__)
TEMPDIR = os.path.join(CURDIR, '.temp_models')

FORCE_DOWNLOAD = None
FORCE_MODEL_DOWNLOAD = None
MODEL_TYPE = None
NUM_MODELS = None
SEED = None
SAVE_SS = None
NUM_DOWNLOAD_PROCS = multiprocessing.cpu_count()
NUM_LOAD_PROCS = multiprocessing.cpu_count()
START_TIME = 0
LAST_SCREENSHOT = 0

class MyBase(ShowBase):
    def __init__(self):
        ShowBase.__init__(self)
        
        if MODEL_TYPE == 'progressive':
            text = 'Progressive'
        else:
            text = 'Original'
        
        self.txtType = OnscreenText(text = text, pos = (-0.90, -0.89), scale = 0.15)
        
        self.num_models_loaded = 0
        self.txtModelsLoaded = OnscreenText(text = 'Models Loaded: %d/%d' % (0,NUM_MODELS), pos = (0.9, -0.81), scale = 0.08)
        
    def userExit(self):
        sys.exit(0)

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

def gen_x_y(num_models):
    X_SIZE = 3
    Y_SIZE = int(math.ceil(float(num_models) / X_SIZE))
    for x in range(X_SIZE):
        for y in range(Y_SIZE):
            yield ((float(x + 0.5 + random.uniform(-0.2,0.2)) / X_SIZE) * 16000 - 8000,
                   (float(y + 0.5 + random.uniform(-0.2,0.2))) * -8000 + 8000)

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
        
        xygen = gen_x_y(len(chosen))
        for model_index in chosen:
            x, y = next(xygen)
            
            model = load_scheduler.Model(model_json = demo_models[model_index],
                                model_type = MODEL_TYPE,
                                x = x,
                                y = y,
                                z = 0,
                                scale = random.uniform(0.5, 6.0))
            model.solid_angle = solid_angle(Vec3(0, 30000, 10000), Vec3(model.x, model.y, model.z), model.scale * 1000)
            
            model.bam_file = model.model_json['full_path'].replace('/', '_')
            model.bam_file = os.path.join(TEMPDIR, model.bam_file + '.' + model.model_type + '.bam')
            if os.path.isfile(model.bam_file):
                print 'Loading cached model', model.bam_file
                load_queue.put((ActionType.LOAD_MODEL, model))
            else:
                dt = load_scheduler.ModelDownloadTask(model, priority=model.solid_angle * 100)
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
                elif isinstance(finished_task, load_scheduler.ProgressiveDownloadTask):
                    load_queue.put((ActionType.PROGRESSIVE_ADDITION, finished_task.model, finished_task.refinements))
                else:
                    print 'not doing anything for type', type(finished_task)
                
            time.sleep(0.05)
            
        print 'Finished loading all models'

    def run(self):
        try:
            self._run()
        except (KeyboardInterrupt, SystemExit):
            return

screenshot_next_frame = -1
def doScreenshot():
    this_timestamp = (time.clock() - START_TIME)
    global LAST_SCREENSHOT, screenshot_next_frame
    if this_timestamp - LAST_SCREENSHOT > 0.5 and SAVE_SS is not None:
        LAST_SCREENSHOT = this_timestamp
        base.win.saveScreenshot(os.path.join(SAVE_SS, ('%.7g' % this_timestamp) + '.png'))
    screenshot_next_frame = -1
    
def triggerScreenshot():
    global screenshot_next_frame
    screenshot_next_frame = 2

def modelLoaded(np, model):
    print 'Model loaded'
    np.setPos(model.x, model.y, model.z)
    np.setScale(model.scale, model.scale, model.scale)
    minPt, maxPt = np.getTightBounds()
    zRange = math.fabs(minPt.getZ() - maxPt.getZ())
    np.setPos(model.x, model.y, zRange / 2.0)
    np.reparentTo(render)
    base.num_models_loaded += 1
    base.txtModelsLoaded.setText('Models Loaded: %d/%d' % (base.num_models_loaded, NUM_MODELS))
    if base.num_models_loaded >= NUM_MODELS:
        print 'Exiting because all models are loaded.'
        sys.exit(0)
    triggerScreenshot()

class ActionType(object):
    LOAD_MODEL = 0
    UPDATE_TEXTURE = 1
    PROGRESSIVE_ADDITION = 2

def checkForLoad(task):
    global screenshot_next_frame
    if screenshot_next_frame != -1:
        screenshot_next_frame -= 1
        if screenshot_next_frame <= 0:
            doScreenshot()
    
    #print globalClock.getAverageFrameRate()
    
    try:
        action = load_queue.get_nowait()
    except Queue.Empty:
        action = None
    
    if action is None:
        return task.cont

    action_type = action[0]
    
    if action_type == ActionType.LOAD_MODEL:
        model = action[1]
        loader.loadModel(model.bam_file, callback=modelLoaded, extraArgs=[model])
    
    elif action_type == ActionType.UPDATE_TEXTURE:
        model = action[1]
        offset = action[2]
        data = action[3]
        print model.model_json['base_path'], 'needs texture updating offset', offset
        texpnm = PNMImage()
        texpnm.read(StringStream(data), 'something.jpg')
        newtex = Texture()
        newtex.load(texpnm)
        
        path_search = '**/' + model.model_json['full_path'].replace('/', '_') + '*'
        np = render.find(path_search)
        
        np.setTextureOff(1)
        np.setTexture(newtex, 1)
        triggerScreenshot()
    
    elif action_type == ActionType.PROGRESSIVE_ADDITION:
        model = action[1]
        refinements = action[2]
        
        path_search = '**/' + model.model_json['full_path'].replace('/', '_') + '*'
        np = render.find(path_search)
        
        np = np.find("**/primitive")

        geom = np.node().modifyGeom(0)
        
        vertdata = geom.modifyVertexData()
        prim = geom.modifyPrimitive(0)
        indexdata = prim.modifyVertices()
        
        indexrewriter = GeomVertexRewriter(indexdata)
        indexrewriter.setColumn(0)
        nextTriangleIndex = indexdata.getNumRows()
        
        vertwriter = GeomVertexWriter(vertdata, 'vertex')
        numverts = vertdata.getNumRows()
        vertwriter.setRow(numverts)
        normalwriter = GeomVertexWriter(vertdata, 'normal')
        normalwriter.setRow(numverts)
        uvwriter = GeomVertexWriter(vertdata, 'texcoord')
        uvwriter.setRow(numverts)
        
        for refinement in refinements:
            for op_index in range(len(refinement)):
                vals = refinement[op_index]
                op = vals[0]
                if op == PM_OP.TRIANGLE_ADDITION:
                    indexrewriter.setRow(nextTriangleIndex)
                    nextTriangleIndex += 3
                    indexrewriter.addData1i(vals[1])
                    indexrewriter.addData1i(vals[2])
                    indexrewriter.addData1i(vals[3])
                elif op == PM_OP.INDEX_UPDATE:
                    indexrewriter.setRow(vals[1])
                    indexrewriter.setData1i(vals[2])
                elif op == PM_OP.VERTEX_ADDITION:
                    numverts += 1
                    vertwriter.addData3f(vals[1], vals[2], vals[3])
                    normalwriter.addData3f(vals[4], vals[5], vals[6])
                    uvwriter.addData2f(vals[7], vals[8])
    
        print '---JUST UPDATED ' + model.model_json['full_path'] + ' ----'
        triggerScreenshot()
    
    return task.cont

def main():
    
    parser = argparse.ArgumentParser(description='Tool for displaying a scene from open3dhub')
    
    parser.add_argument('--force-model-download', dest='force_model', action='store_true', help='Force re-downloading models')
    parser.add_argument('--force-download', dest='force', action='store_true', help='Force re-downloading of model list')
    parser.add_argument('type', help='Model type to use', choices=['optimized', 'progressive'])
    parser.add_argument('num_models', help='Number of models to use', type=int)
    parser.add_argument('--seed', required=False, help='Seed for random number generator', type=str)
    parser.add_argument('--screenshots', required=False, help='Directory to save screenshots', type=str)
    
    args = parser.parse_args()
    
    global FORCE_DOWNLOAD
    global FORCE_MODEL_DOWNLOAD
    global MODEL_TYPE
    global NUM_MODELS
    global SEED
    global SAVE_SS
    global START_TIME
    global LAST_SCREENSHOT
    
    FORCE_DOWNLOAD = args.force
    FORCE_MODEL_DOWNLOAD = args.force_model
    MODEL_TYPE = args.type
    NUM_MODELS = args.num_models
    SEED = args.seed
    SAVE_SS = args.screenshots
    
    if SEED is not None:
        random.seed(SEED)
        
    if SAVE_SS is not None:
        if not os.path.isdir(SAVE_SS):
            print >> sys.stderr, 'Invalid screenshots directory'
            parser.print_usage()
            sys.exit(1)
    START_TIME = time.clock()
    LAST_SCREENSHOT = time.clock()
    
    global base, render, taskMgr, loader
    base = MyBase()
    render = base.render
    taskMgr = base.taskMgr
    loader = base.loader
    
    if FORCE_MODEL_DOWNLOAD:
        try:
            shutil.rmtree(TEMPDIR)
        except OSError:
            pass
    try:
        os.mkdir(TEMPDIR)
    except OSError:
        pass
    
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
    
    environ.setTransparency(TransparencyAttrib.MAlpha)
    environ.setAlphaScale(0.3)
    
    render.setAntialias(AntialiasAttrib.MAuto)
    
    base.run()

if __name__ == '__main__':
    main()
