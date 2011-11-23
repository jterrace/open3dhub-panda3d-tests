import open3dhub
import multiprocessing
import heapq
import time
import math
from collections import namedtuple

class Model(object):
    def __init__(self, model_json, model_type, x, y, z, scale):
        self.model_json = model_json
        self.x = x
        self.y = y
        self.z = z
        self.scale = scale
        self.solid_angle = 0.0
        self.model_type = model_type
        self.bam_file = None
    
    def __str__(self):
        return "<Model '%s' at (%.7g,%.7g,%.7g) scale %.7g>" % (self.model_json['base_path'], self.x, self.y, self.z, self.scale)
    def __repr__(self):
        return str(self)

class Task(object):
    """Base class for tasks that need to be executed"""
    
    def __init__(self, priority, dependents=None):
        """Creates a task with given priority and list of dependent tasks"""
        self.priority = priority
        if dependents is None:
            self.dependents = []
        else:
            self.dependents = dependents

    def run(self, pool):
        """Called when the task should be run, implemented by child classes"""
        raise NotImplementedError
    
    def finished(self, result):
        """Called when the result of a task is complete, implemented by child classes"""
        raise NotImplementedError
    
    def __cmp__(self, other):
        """Reverse compare function so that heapq will return largest priority first"""
        if self.priority == other.priority:
            return 0
        elif self.priority < other.priority:
            return 1
        return -1 

class DownloadTask(Task):
    """Base task class for downloading something"""
    
    def __init__(self, *args, **kwargs):
        super(DownloadTask, self).__init__(*args, **kwargs)
        
    def run(self, pool):
        return NotImplementedError
    
    def finished(self, result):
        return NotImplementedError

class ModelDownloadTask(DownloadTask):
    """Task for downloading a model from CDN"""
    
    def __init__(self, model, *args, **kwargs):
        super(ModelDownloadTask, self).__init__(*args, **kwargs)
        self.model = model
    
    def run(self, pool):
        return pool.apply_async(execute_download, (self.model,))
    
    def finished(self, result):
        print 'finished download task'
        for subtask in result:
            self.dependents.append(subtask)

def execute_download(model):
    """Execute function for a ModelDownloadTask"""
    return open3dhub.download_mesh_and_subtasks(model)

class TextureDownloadTask(DownloadTask):
    """Task for downloading a texture from CDN"""
    
    def __init__(self, model, offset, *args, **kwargs):
        super(TextureDownloadTask, self).__init__(*args, **kwargs)
        self.model = model
        self.offset = offset
        self.data = None
    
    def run(self, pool):
        return pool.apply_async(execute_texture_download, (self.model, self.offset))
    
    def finished(self, result):
        print 'finished texture download task'
        self.data = result

def execute_texture_download(model, offset):
    """Execute function for a TextureDownloadTask"""
    return open3dhub.download_texture(model, offset)
    
class ProgressiveDownloadTask(DownloadTask):
    """Task for downloading progressive stream"""
    
    def __init__(self, model, offset, length, refinements_read, num_refinements, previous_data, *args, **kwargs):
        super(ProgressiveDownloadTask, self).__init__(*args, **kwargs)
        self.model = model
        self.offset = offset
        self.length = length
        self.refinements_read = refinements_read
        self.num_refinements = num_refinements
        self.previous_data = previous_data
    
    def run(self, pool):
        return pool.apply_async(execute_progressive_download, (self.model, self.offset, self.length, self.refinements_read, self.num_refinements, self.previous_data))
    
    def finished(self, result):
        print 'finished progressive download task'
        refinements_read, num_refinements, refinements, previous_data = result
        
        self.refinements = refinements
        
        next_priority = self.model.solid_angle * \
                (math.sqrt(0.3 * open3dhub.PROGRESSIVE_CHUNK_SIZE) /
                 math.sqrt(self.offset + self.length + open3dhub.PROGRESSIVE_CHUNK_SIZE))
        
        if refinements_read < num_refinements:
            next_progressive_task = ProgressiveDownloadTask(self.model,
                                                            self.offset + self.length,
                                                            open3dhub.PROGRESSIVE_CHUNK_SIZE,
                                                            refinements_read = refinements_read,
                                                            num_refinements = num_refinements,
                                                            previous_data = previous_data,
                                                            priority = next_priority)
            self.dependents.append(next_progressive_task)

def execute_progressive_download(model, offset, length, refinements_read, num_refinements, previous_data):
    """Execute function for a ProgressiveDownloadTask"""
    return open3dhub.download_progressive(model, offset, length, refinements_read, num_refinements, previous_data)

class LoadTask(Task):
    """Task for loading a model using pycollada and turning it into 
    a bam file for loading"""
    
    def __init__(self, meshdata, subfiles, model, *args, **kwargs):
        super(LoadTask, self).__init__(*args, **kwargs)
        self.meshdata = meshdata
        self.subfiles = subfiles
        self.model = model
    
    def run(self, pool):
        return pool.apply_async(execute_load, (self.meshdata, self.subfiles, self.model))
    
    def finished(self, result):
        print 'finished load task'
        self.model.bam_file = result
        
def execute_load(meshdata, subfiles, model):
    """Execute function for LoadTask"""
    return open3dhub.load_into_bamfile(meshdata, subfiles, model)
    

TaskResult = namedtuple('TaskResult', 'task, result')
"""A task and its result"""

class TaskPool(object):
    """A task pool for running tasks"""
    
    def __init__(self, NUM_PROCS):
        """Initializes the pool with given number of processes"""
        self.NUM_PROCS = NUM_PROCS
        self.pool = multiprocessing.Pool(self.NUM_PROCS)
        self.to_run = []
        self.running = []

    def add_task(self, task):
        """Add a task to the pool"""
        heapq.heappush(self.to_run, task)

    def check_waiting(self):
        """Checks list of running tasks for any that have finished"""
        finished = []
        new_running = []
        for runningtask in self.running:
            if runningtask.result.ready():
                finished.append(runningtask)
            else:
                new_running.append(runningtask)
        self.running = new_running
        return finished

    def empty(self):
        """Returns True if the pool is empty"""
        return len(self.to_run) + len(self.running) == 0

    def poll(self):
        """Executes tasks and gets results. Should be executed often."""
        finished_running = self.check_waiting()

        while len(self.running) < self.NUM_PROCS and len(self.to_run) > 0:
            task = heapq.heappop(self.to_run)
            self.running.append(TaskResult(task=task, result=task.run(self.pool)))
        
        to_return = []
        for runningtask in finished_running:
            print 'taskpool finished a task', len(self.to_run) + len(self.running), 'left'
            result = runningtask.result.get()
            runningtask.task.finished(result)
            to_return.append(runningtask.task)
        
        return to_return
