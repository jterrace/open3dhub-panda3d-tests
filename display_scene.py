import os
import sys
import thread
import threading
import time
import Queue
from multiprocessing.pool import Pool
import multiprocessing
import pickle
import random
import shutil
import math

from direct.showbase.ShowBase import ShowBase
from direct.gui.OnscreenText import OnscreenText
from panda3d.core import TransparencyAttrib, AntialiasAttrib, TextureAttrib, TextureStage
from panda3d.core import VBase4, Vec3
from panda3d.core import PNMImage, Texture, StringStream, GeomNode
from panda3d.core import loadPrcFileData

import argparse
import collada
from meshtool.filters.panda_filters import pandacore
from meshtool.filters.panda_filters.pandacontrols import KeyboardMovement, MouseDrag, MouseScaleZoom, MouseCamera
from meshtool.filters.panda_filters.pdae_utils import PM_OP

import scene
import load_scheduler
from p3d_mesh_updater import update_nodepath

loadPrcFileData('', 'win-size 1024 768')

base = None
render = None
taskMgr = None
loader = None

load_queue = Queue.Queue()

CURDIR = os.path.dirname(__file__)
TEMPDIR = os.path.join(CURDIR, '.temp_models')

FORCE_MODEL_DOWNLOAD = None
SAVE_SS = None
NUM_DOWNLOAD_PROCS = 4 #multiprocessing.cpu_count() * 2
NUM_LOAD_PROCS = 2 #multiprocessing.cpu_count()
START_TIME = 0
LAST_SCREENSHOT = 0
NUM_MODELS = None
EXIT_AFTER = False
MODEL_SUBTYPE = None
MODEL_TYPE = None
HASH_SIZES = None

PANDA3D = False

class MyBase(ShowBase):
    def __init__(self):
        ShowBase.__init__(self)
        
        self.num_models_loaded = 0
        self.quit = False
        self.quit_frame = sys.maxint
        self.screenshot_frame = sys.maxint
        #self.txtModelsLoaded = OnscreenText(text = 'Models Loaded: %d/%d' % (0,NUM_MODELS), pos = (0.9, -0.81), scale = 0.08)
        
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

class LoadingThread(threading.Thread):
    
    def __init__(self, model_list):
        super(LoadingThread, self).__init__()
        self.model_list = model_list
    
    def _run(self):
        
        download_pool = load_scheduler.TaskPool(NUM_DOWNLOAD_PROCS)
        loader_pool = load_scheduler.TaskPool(NUM_LOAD_PROCS)
        last_status = time.time()
        
        for model in self.model_list:
            model.model_type = MODEL_TYPE
            model.solid_angle = solid_angle(Vec3(0, 30000, 10000), Vec3(model.x, model.y, model.z), model.scale * 1000)
            model.bam_file = model.model_json['full_path'].replace('/', '_')
            model.model_subtype = MODEL_SUBTYPE
            model.HASH_SIZES = HASH_SIZES
            extra_part = ''
            if model.model_type == 'progressive':
                extra_part = '.' + MODEL_SUBTYPE
            model.bam_file = os.path.join(TEMPDIR, model.bam_file + '.' + model.model_type + '.' + model.model_type + extra_part + '.bam')
            if False and os.path.isfile(model.bam_file):
                print 'Loading cached model', model.bam_file
                load_queue.put((ActionType.LOAD_MODEL, model))
            else:
                
                if PANDA3D:
                    panda3d_key = 'panda3d_%s_bam' % model.model_subtype if model.model_type == 'progressive' else 'panda3d_bam'
                    panda3d_hash =  model.model_json['metadata']['types'][model.model_type][panda3d_key]
                    download_size = HASH_SIZES[panda3d_hash]['gzip_size']
                else:
                    model_hash =  model.model_json['metadata']['types'][model.model_type]['hash']
                    subfile_hashes = model.model_json['metadata']['types'][model.model_type]['subfile_hashes']
                    
                    download_size = HASH_SIZES[model_hash]['gzip_size']
                    
                    if model.model_type == 'progressive':
                        
                        if model.model_subtype == 'base':
                        
                            for subfile in model.model_json['metadata']['types'][model.model_type]['subfiles']:
                                splitpath = subfile.split('/')
                                basename = './' + splitpath[-2]
                                
                                mipmaps = model.model_json['metadata']['types'][model.model_type]['mipmaps']
                                mipmap_levels = mipmaps[basename]['byte_ranges']
                                offset = 0
                                length = 0
                                for mipmap in mipmap_levels:
                                    offset = mipmap['offset']
                                    length = mipmap['length']
                                    if mipmap['width'] >= 128 or mipmap['height'] >= 128:
                                        break
    
                                download_size += length
                        
                        elif model.model_subtype == 'full':
                            
                            prog_hash = model.model_json['metadata']['types'][model.model_type].get('progressive_stream')
                            if prog_hash is not None:
                                download_size += HASH_SIZES[prog_hash]['gzip_size']
                            
                            for subfile in model.model_json['metadata']['types'][model.model_type]['subfiles']:
                                splitpath = subfile.split('/')
                                basename = './' + splitpath[-2]
                                
                                mipmaps = model.model_json['metadata']['types'][model.model_type]['mipmaps']
                                mipmap_levels = mipmaps[basename]['byte_ranges']
                                length = 0
                                for mipmap in mipmap_levels:
                                    length = mipmap['length']
                                
                                download_size += length
                            
                        else:
                            raise Exception("unknown model subtype")
                        
                    else:
                        for subfile_hash in subfile_hashes:
                            download_size += HASH_SIZES[subfile_hash]['gzip_size']
                    
                    
                # we want to normalize by file size
                priority = model.solid_angle / float(download_size)
                # but then also boost by a lot so that progressive download tasks don't overtake
                priority = priority * 1 * 1000 * 1000 * 1000 * 1000
                
                dt = load_scheduler.ModelDownloadTask(model, priority=priority)
                download_pool.add_task(dt)
        
        while not(download_pool.empty() and loader_pool.empty()):
            now = time.time()
            if now - last_status > 5.0:
                last_status = now
                print 'Downloader has', len(download_pool.running), 'running and', len(download_pool.to_run), 'waiting'
                print 'Loader has', len(loader_pool.running), 'running and', len(loader_pool.to_run), 'waiting'
            
            finished_tasks = download_pool.poll() + loader_pool.poll()
            
            for finished_task in finished_tasks:
                print 'finished task', finished_task, 'has', len(finished_task.dependents), 'dependents'
                
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
        load_queue.put((ActionType.QUIT, ))

    def run(self):
        try:
            self._run()
        except (KeyboardInterrupt, SystemExit):
            return
    
def triggerScreenshot(task):
    global LAST_SCREENSHOT
    this_timestamp = (time.clock() - START_TIME)
    if this_timestamp - LAST_SCREENSHOT >= 1.0:
        LAST_SCREENSHOT = this_timestamp
        base.screenshot_frame = globalClock.getFrameCount()
        base.win.saveScreenshot(os.path.join(SAVE_SS, ('%07.2f' % this_timestamp) + '.png'))
    return task.cont

model_queued = False
model_queue = []

def checkQueue():
    global model_queue
    global model_queued
    
    if not model_queued and len(model_queue) > 0:
        model_queued = True
        model = model_queue.pop(0)
        print 'LOADING MODEL', model.bam_file, modelLoaded
        loader.loadModel(model.bam_file, callback=modelLoaded, extraArgs=[model])

def modelLoaded(np, model):
    global model_queued
    
    print 'Model loaded', base.num_models_loaded, model.model_json['full_path']
    np.setPos(model.x, model.y, model.z)
    np.setScale(model.scale, model.scale, model.scale)
    minPt, maxPt = np.getTightBounds()
    zRange = math.fabs(minPt.getZ() - maxPt.getZ())
    np.setPos(model.x, model.y, zRange / 2.0)
    np.reparentTo(render)
    base.num_models_loaded += 1
    base.quit_frame = globalClock.getFrameCount()
    model_queued = False
    #base.txtModelsLoaded.setText('Models Loaded: %d/%d' % (base.num_models_loaded, NUM_MODELS))

class ActionType(object):
    LOAD_MODEL = 0
    UPDATE_TEXTURE = 1
    PROGRESSIVE_ADDITION = 2
    QUIT = 3

def checkForLoad(task):
    
    #print globalClock.getAverageFrameRate()
    global model_queue
    
    checkQueue()
    
    try:
        action = load_queue.get_nowait()
    except Queue.Empty:
        action = None
    
    if EXIT_AFTER and action is None and base.num_models_loaded >= NUM_MODELS and base.quit and base.screenshot_frame > base.quit_frame:
        sys.exit(0)
    elif action is None and base.num_models_loaded >= NUM_MODELS and base.quit and base.screenshot_frame > base.quit_frame:
        base.render.analyze()
        base.quit = False
    
    if action is None:
        return task.cont

    action_type = action[0]
    
    if action_type == ActionType.LOAD_MODEL:
        model = action[1]
        print 'Queueing model for load:', model.model_json['full_path'], 'queue size', len(model_queue)
        model_queue.append(model)
        checkQueue()
    
    elif action_type == ActionType.UPDATE_TEXTURE:
        model = action[1]
        offset = action[2]
        data = action[3]
        print model.model_json['base_path'], 'needs texture updating offset', offset
        texpnm = PNMImage()
        texpnm.read(StringStream(data), 'something.jpg')
        newtex = Texture()
        newtex.load(texpnm)
        
        path_search = '**/*' + model.model_json['full_path'].replace('/', '_') + '*'
        np = render.find(path_search)
        
        np.setTextureOff(1)
        np.setTexture(newtex, 1)
    
    elif action_type == ActionType.PROGRESSIVE_ADDITION:
        model = action[1]
        refinements = action[2]
        
        path_search = '**/*' + model.model_json['full_path'].replace('/', '_') + '*'
        np = render.find(path_search)
        np = np.find("**/primitive")
        pnode = np.node()
        
        
        start = time.time()
        update_nodepath(pnode, refinements)
        end = time.time()
    
        print '---JUST UPDATED ' + model.model_json['full_path'] + ' ----'
        
    elif action_type == ActionType.QUIT:
        print 'Got a quit message, triggering quit flag'
        base.quit = True
    
    return task.cont

def main():
    
    parser = argparse.ArgumentParser(description='Tool for displaying a scene from open3dhub')

    parser.add_argument('--model-type', choices=['progressive', 'optimized'], default='progressive', required=False, help='Model type to use')
    parser.add_argument('--model-subtype', choices=['base', 'full'], default='base', required=False, help='Model subtype (currently only for progressive)')
    parser.add_argument('--force-model-download', dest='force_model', action='store_true', help='Force re-downloading models')
    parser.add_argument('scene_file', help='Scene file to use, generated with scene_generator', type=argparse.FileType('r'))
    parser.add_argument('--screenshots', required=False, help='Directory to save screenshots', type=str)
    parser.add_argument('--exit-after-load', required=False, default=False, action='store_true', help='Exit the program after all models are loaded')
    
    args = parser.parse_args()
    
    global FORCE_MODEL_DOWNLOAD
    global SAVE_SS
    global START_TIME
    global LAST_SCREENSHOT
    global NUM_MODELS
    global EXIT_AFTER
    global MODEL_TYPE
    global MODEL_SUBTYPE
    global HASH_SIZES
    
    EXIT_AFTER = args.exit_after_load
    FORCE_MODEL_DOWNLOAD = args.force_model
    SAVE_SS = args.screenshots
    MODEL_TYPE = args.model_type
    MODEL_SUBTYPE = args.model_subtype
        
    if SAVE_SS is not None:
        if os.path.isdir(SAVE_SS):
            #yn = raw_input("Delete existing ss dir? ")
            yn = 'y'
            if yn == 'y':
                shutil.rmtree(SAVE_SS)
            else:
                print 'Exiting then'
                sys.exit(1)
        if not os.path.isdir(SAVE_SS):
            os.mkdir(SAVE_SS)
        if not os.path.isdir(SAVE_SS):
            print >> sys.stderr, 'Invalid screenshots directory'
            parser.print_usage()
            sys.exit(1)
    START_TIME = time.clock()
    LAST_SCREENSHOT = START_TIME
    
    scene_dict = pickle.load(args.scene_file)
    HASH_SIZES = scene_dict['sizes']
    scene_models = scene_dict['models']
    NUM_MODELS = len(scene_models)
    
    global base, render, taskMgr, loader
    base = MyBase()
    render = base.render
    taskMgr = base.taskMgr
    loader = base.loader
    
    #if FORCE_MODEL_DOWNLOAD:
    #    try:
    #        shutil.rmtree(TEMPDIR)
    #    except OSError:
    #        pass
    try:
        os.mkdir(TEMPDIR)
    except OSError:
        pass
    
    base.disableMouse()
    pandacore.attachLights(render)
    
    base.cam.setPos(0, 30000, 10000)
    base.cam.lookAt(0, 0, 2000)
    
    t = LoadingThread(scene_models)
    t.daemon = True
    t.start()
    
    taskMgr.add(checkForLoad, "checkForLoad")
    if SAVE_SS is not None:
        taskMgr.add(triggerScreenshot, "triggerScreenshot")
    
    KeyboardMovement(scale=10.0)
    MouseCamera()
    
    #base.win.setClearColor(VBase4(0.9,0.9,0.9,1))
    base.win.setClearColor(VBase4(0.529,0.807,0.98,1))
    environ = loader.loadModel("grass.egg")
    environ.reparentTo(render)
    minPt, maxPt = environ.getTightBounds()
    xRange = math.fabs(minPt.getX() - maxPt.getX())
    yRange = math.fabs(minPt.getY() - maxPt.getY())
    zRange = math.fabs(minPt.getZ() - maxPt.getZ())
    environ.setScale(500, 2500, 100)
    environ.setPos(0, 1000, 0) #-1 * zRange / 2.0)
    environ.setP(180)
    #environ.lookAt(200, 200, 0)
    #environ.lookAt(base.cam)
    
    #environ.setTransparency(TransparencyAttrib.MAlpha)
    #environ.setAlphaScale(0.3)
    
    render.setShaderAuto()
    render.setAntialias(AntialiasAttrib.MAuto)
    environ.setShaderOff()
    
    # effectively disable distance culling
    base.camLens.setFar(sys.maxint)
    base.camLens.setNear(8.0)
    
    base.setFrameRateMeter(True)
    base.run()

if __name__ == '__main__':
    main()
