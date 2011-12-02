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
import open3dhub

base = None
render = None
taskMgr = None
loader = None

CURDIR = os.path.dirname(__file__)
TEMPDIR = os.path.join(CURDIR, '.temp_models')

try:
    os.mkdir(TEMPDIR)
except OSError:
    pass

class MyBase(ShowBase):
    def __init__(self):
        ShowBase.__init__(self)
        
    def userExit(self):
        sys.exit(0)

def getModel(index_num):
    demo_models = scene.get_all_models()
    #print 'Got', len(demo_models), 'models.'
    
    if True: #for model_index in range(len(demo_models)):
        model_index = index_num
        print 'yielding model', model_index, 'out of', len(demo_models)
        for model_type in ['optimized', 'optimized_unflattened', 'progressive', 'progressive_full']:
            model = load_scheduler.Model(model_json = demo_models[model_index],
                                model_type = model_type,
                                x = 0,
                                y = 0,
                                z = 0,
                                scale = 1)
            model.solid_angle = 1
            
            model.bam_file = model.model_json['full_path'].replace('/', '_')
            model.bam_file = os.path.join(TEMPDIR, model.bam_file + '.' + model.model_type + '.bam')
            if os.path.isfile(model.bam_file):
                #print 'Loading cached model', model.bam_file
                yield model.bam_file
            else:
                #print 'calling download subtask for model', model.model_json['full_path']
                load_task = open3dhub.download_mesh_and_subtasks(model)[0]
                yield open3dhub.load_into_bamfile(load_task.meshdata, load_task.subfiles, load_task.model)

outContents = []
model_iter = None #iter(getModels())
def nextModelTask(task):
    global model_iter, outContents
    try:
        nextModel = next(model_iter)
    except StopIteration:
        outFile = open('throughput_results.txt', 'a')
        outFile.write(' '.join(outContents))
        outFile.write('\n')
        outFile.close()
        sys.exit(0)
    taskMgr.add(doModelTask, 'doModelTask', extraArgs=[nextModel], appendTask=True, uponDeath=nextModelTask)

curModelInit = False
totFrameRate = 0.0
numFrames = 0.0
curNp = None
startedTime = 0
def doModelTask(bam_file, task):
    global curModelInit, totFrameRate, numFrames, curNp, outContents, startedTime
    
    if not curModelInit:
        #print 'Loading', bam_file
        np = loader.loadModel(bam_file)
        curNp = np
        np.setPos(0,0,0)
        np.setScale(10)
        np.reparentTo(render)
        curModelInit = True
        startedTime = time.clock()
        #print 'Done Loading'
    else:
        if task.frame < 300 or task.time < 5: 
            totFrameRate += globalClock.getAverageFrameRate()
            numFrames += 1
        else:
            outContents.append('%f' % (totFrameRate / numFrames,))
            curModelInit = False
            numFrames = 0.0
            totFrameRate = 0.0
            curNp.removeNode()
            curNp = None
            return task.done
    
    return task.cont

def main():
    
    global base, render, taskMgr, loader, model_iter

    model_iter = iter(getModel(int(sys.argv[1])))

    base = MyBase()
    render = base.render
    taskMgr = base.taskMgr
    loader = base.loader
    
    base.disableMouse()
    pandacore.attachLights(render)
    render.setShaderAuto()
    render.setTransparency(TransparencyAttrib.MDual, 1)
    
    base.cam.setPos(0, 30000, 10000)
    base.cam.lookAt(0, 0, 0.0)

    KeyboardMovement()
    MouseCamera()
    
    base.win.setClearColor(VBase4(0.9,0.9,0.9,1))
    
    render.setAntialias(AntialiasAttrib.MAuto)
    
    taskMgr.add(nextModelTask, 'nextModelTask')
    
    base.run()

if __name__ == '__main__':
    main()
