import json
import posixpath
from StringIO import StringIO
import gzip
import tempfile
import math
import os
import requests
import pickle
import time

import numpy
import collada
from meshtool.filters.panda_filters import pandacore
from meshtool.filters.panda_filters import pdae_utils
from meshtool.filters.simplify_filters import add_back_pm
from panda3d.core import GeomNode, NodePath, Mat4

import load_scheduler

BASE_URL = 'http://open3dhub.com'
# 'http://singular.stanford.edu'
BROWSE_URL = BASE_URL + '/api/browse'
DOWNLOAD_URL = BASE_URL + '/download'
DNS_URL = BASE_URL + '/dns'

PANDA3D = False

PROGRESSIVE_CHUNK_SIZE = 2 * 1024 * 1024 # 2 MB

CURDIR = os.path.dirname(__file__)
TEMPDIR = os.path.join(CURDIR, '.temp_models')

REQUESTS_SESSION = requests.session()

class PathInfo(object):
    """Helper class for dealing with CDN paths"""
    def __init__(self, filename):
        self.filename = filename
        self.normpath = posixpath.normpath(filename)
        """Normalized original path"""
        
        split = self.normpath.split("/")
        try:
            self.version = str(int(split[-1]))
            """Version number of the path"""
        except ValueError:
            self.version = None
    
        if self.version is None:
            self.basename = split[-1]
            """The filename of the path"""
            self.basepath = self.normpath
            """The base of the path, without the version number"""
        else:
            self.basename = split[-2]
            self.basepath = '/'.join(split[:-1])
            
    def __str__(self):
        return "<PathInfo filename='%s', normpath='%s', basepath='%s', basename='%s', version='%s'>" % \
                (self.filename, self.normpath, self.basepath, self.basename, self.version)
    
    def __repr__(self):
        return str(self)

def urlfetch(url, httprange=None):
    """Fetches the given URL and returns data from it.
    Will take care of gzip if enabled on server."""
    
    headers = {}
    if httprange is not None:
        offset, length = httprange
        headers['Range'] = 'bytes=%d-%d' % (offset, offset+length-1)
    
    resp = REQUESTS_SESSION.get(url, headers=headers)
    
    return resp.content
    

def hashfetch(dlhash, httprange=None):
    """Fetches the given hash and returns data from it."""
    return urlfetch(DOWNLOAD_URL + '/' + dlhash, httprange)

def get_subfile_hash(subfile_path):
    subfile_url = DNS_URL + subfile_path
    subfile_json = json.loads(urlfetch(subfile_url))
    subfile_hash = subfile_json['Hash']
    return subfile_hash

def get_list(limit=20):
    """Returns a list of dictionaries containing model JSON"""
    
    next_start = ''
    all_items = []
    unique_models = set()

    while len(all_items) < limit and next_start != None:
        print 'got', len(all_items), 'so far'
        
        models_js = json.loads(urlfetch(BROWSE_URL + '/' + next_start))
        next_start = models_js['next_start']
        
        models_js = models_js['content_items']
        
        for model_js in models_js:
            
            progressive = model_js['metadata']['types'].get('progressive')
            if progressive is not None and 'mipmaps' in progressive:
                for mipmap_name, mipmap_data in progressive['mipmaps'].iteritems():
                    old_byte_ranges = mipmap_data['byte_ranges']
                    new_byte_ranges = []
                    offset = 0
                    for byte_data in old_byte_ranges:
                        offset += 512
                        new_byte_data = dict(byte_data)
                        if offset != new_byte_data['offset']:
                            new_byte_data['offset'] = offset
                        file_len = new_byte_data['length']
                        file_len = 512 * ((file_len + 512 - 1) / 512)
                        offset += file_len
                        new_byte_ranges.append(new_byte_data)
                    model_js['metadata']['types']['progressive']['mipmaps'][mipmap_name]['byte_ranges'] = new_byte_ranges
            
            if model_js['full_path'] in unique_models:
                print 'OMG< FOUND A DUPLICATE', model_js['full_path']
            else:
                unique_models.add(model_js['full_path'])
                all_items.append(model_js)
        
    if len(all_items) > limit:
        all_items = all_items[0:limit]
        
    return all_items

def get_hash_sizes(items):

    hash_keys = ['zip', 'screenshot', 'hash', 'thumbnail',
                 'progressive_stream', 'panda3d_base_bam',
                 'panda3d_full_bam', 'panda3d_bam',
                 'subfile_hashes']
       
    unique_keys = set()
    for item in items:
        
        for type_name, type_data in item['metadata']['types'].iteritems():
        
            for hash_key in hash_keys:
                hash_key_val = type_data.get(hash_key)
                if hash_key_val is not None:
                    if isinstance(hash_key_val, basestring):
                        unique_keys.add(type_data[hash_key])
                    else:
                        unique_keys.update(type_data[hash_key])
                    
            #progressive mipmaps are nested
            if 'mipmaps' in type_data:
                for mipmap_data in type_data['mipmaps'].itervalues():
                    unique_keys.add(mipmap_data['hash'])
    
    cache_file = os.path.join(CURDIR, 'hash-size-cache.pickle')
    hash_cache = {}
    if os.path.isfile(cache_file):
        hash_cache = pickle.load(open(cache_file, 'rb'))
        
    hash_sizes = {}
    for hash in unique_keys:
        if hash in hash_cache:
            hash_sizes[hash] = hash_cache[hash]
        else:
            resp = REQUESTS_SESSION.get(DOWNLOAD_URL + '/' + hash)
            hash_sizes[hash] = {'size': len(resp.content),
                                'gzip_size': int(resp.headers['content-length'])}
            hash_cache[hash] = hash_sizes[hash]
    
    pickle.dump(hash_cache, open(cache_file, 'wb'))
    
    return hash_sizes

def load_mesh(mesh_data, subfiles):
    """Given a downloaded mesh, return a collada instance"""
    
    def inline_loader(filename):
        return subfiles[posixpath.basename(filename)]
    
    mesh = collada.Collada(StringIO(mesh_data), aux_file_loader=inline_loader)
    
    #this will force loading of the textures too
    for img in mesh.images:
        img.data
    
    return mesh

def download_mesh_and_subtasks(model):
    """Given a model, downloads the mesh and returns a set of subtasks."""
    
    types = model.model_json['metadata']['types']
    model_type = model.model_type
    if model_type == 'optimized_unflattened':
        model_type = 'optimized'
    elif model_type == 'progressive_full':
        model_type = 'progressive'
    
    if not model_type in types:
        return None
    
    type_dict = types[model_type]
    
    mipmaps = type_dict.get('mipmaps')
    if mipmaps:
        mipmaps = dict((posixpath.basename(p), info) for p, info in mipmaps.iteritems())
    
    mesh_hash = type_dict['hash']
    
    panda3d_key = 'panda3d_%s_bam' % model.model_subtype if model_type == 'progressive' else 'panda3d_bam'
    is_bam = False
    if PANDA3D and panda3d_key in type_dict:
        bam_hash = type_dict[panda3d_key]
        print 'Downloading mesh (from bamfile)', model.model_json['base_path'], bam_hash
        data = hashfetch(bam_hash)
        is_bam = True
    else:
        print 'Downloading mesh', model.model_json['base_path'], mesh_hash
        data = hashfetch(mesh_hash)
    
    subfile_basenames = [PathInfo(s).basepath for s in type_dict['subfiles']]
    subfile_name_hash_map = dict(zip(subfile_basenames, type_dict['subfile_hashes']))
    
    subfile_dict = {}
    
    texture_task_base = None
    
    progressive_hash = type_dict.get('progressive_stream')
    progressive_task = None
    if progressive_hash is not None and model.model_subtype != 'full':
        # priority is the solid angle
        priority = model.solid_angle
        # multiplied by a scale factor that makes earlier chunks have more weight
        percentage = float(0 + PROGRESSIVE_CHUNK_SIZE) / model.HASH_SIZES[progressive_hash]['size']
        priority = priority * ((1.0 - percentage) ** 2)
        # divided by the gzip size
        priority = priority / model.HASH_SIZES[progressive_hash]['gzip_size']
        
        progressive_task = load_scheduler.ProgressiveDownloadTask(model,
                                                                  0,
                                                                  PROGRESSIVE_CHUNK_SIZE,
                                                                  priority = priority,
                                                                  refinements_read = 0,
                                                                  num_refinements = None,
                                                                  previous_data = '')
    
    for subfile in type_dict['subfiles']:
        splitpath = subfile.split('/')
        basename = splitpath[-2]
        
        if mipmaps is not None and basename in mipmaps and model.model_subtype != 'full':
            mipmap_levels = mipmaps[basename]['byte_ranges']
            tar_hash = mipmaps[basename]['hash']
            
            base_pixels = 0
            offset = 0
            length = 0
            for mipmap in mipmap_levels:
                offset = mipmap['offset']
                length = mipmap['length']
                base_pixels = mipmap['width'] * mipmap['height']
                if mipmap['width'] >= 128 or mipmap['height'] >= 128:
                    break

            if not is_bam:
                print 'GETTING TEXTURE', subfile, 'AT RANGE', offset, length
                texture_data = hashfetch(tar_hash, httprange=(offset, length))
                subfile_dict[basename] = texture_data
            
            for mipmap in reversed(mipmap_levels):
                mipmap_pixels = mipmap['width'] * mipmap['height']
                if mipmap_pixels <= base_pixels:
                    break

                # priority is the solid angle
                priority = model.solid_angle
                # multiplied by a factor to make smaller textures higher priority over larger
                priority = priority * math.sqrt(float(base_pixels) / mipmap_pixels)
                # multiplied by how big this tar range is relative to the total size
                priority = priority * (float(mipmap['length']) / model.HASH_SIZES[tar_hash]['size'])
                # divided by the gzip size
                priority = priority / model.HASH_SIZES[tar_hash]['gzip_size']
                
                tex_dt = load_scheduler.TextureDownloadTask(model, mipmap['offset'], priority=priority)
                if texture_task_base is not None:
                    tex_dt.dependents.append(texture_task_base)
                texture_task_base = tex_dt
        
        elif mipmaps is not None and basename in mipmaps and model.model_subtype == 'full':
            mipmap_levels = mipmaps[basename]['byte_ranges']
            tar_hash = mipmaps[basename]['hash']

            model.prog_data = None
            if progressive_hash is not None:
                print 'DOWNLOADING PROGRESSIVE STREAM'
                prog_data = hashfetch(progressive_hash)
                model.prog_data = prog_data
            
            full_texture = list(reversed(mipmap_levels))[0]
            
            texture_basepath = PathInfo(subfile).basepath
            print 'DOWNLOADING HIGHEST TEXTURE SIZE'
            texture_data = hashfetch(tar_hash, httprange=(full_texture['offset'], full_texture['length']))
            subfile_dict[basename] = texture_data
        
        elif model.model_subtype != 'full':
            #texture_path = posixpath.normpath(posixpath.join(model.model_json['base_path'], model_type, model.model_json['version_num'], basename))
            #texture_hash = get_subfile_hash(texture_path)
            texture_basepath = PathInfo(subfile).basepath
            texture_hash = subfile_name_hash_map[texture_basepath]
            texture_data = hashfetch(texture_hash)
    
            subfile_dict[basename] = texture_data
    
    load_task = load_scheduler.LoadTask(data, subfile_dict, model, priority=model.solid_angle, is_bam=is_bam)
    if texture_task_base is not None:
        load_task.dependents.append(texture_task_base)
    if progressive_task is not None:
        load_task.dependents.append(progressive_task)
    return [load_task]

def download_texture(model, download_offset):
    """Given a model and texture offset, downloads the texture"""
    
    types = model.model_json['metadata']['types']
    type_dict = types[model.model_type]
    
    mipmaps = type_dict.get('mipmaps')
    if mipmaps:
        mipmaps = dict((posixpath.basename(p), info) for p, info in mipmaps.iteritems())
    
    assert(len(mipmaps) == 1)
    basename = next(mipmaps.iterkeys())
    
    mipmap_levels = mipmaps[basename]['byte_ranges']
    tar_hash = mipmaps[basename]['hash']
    
    for mipmap in mipmap_levels:
        offset = mipmap['offset']
        length = mipmap['length']
        
        if offset == download_offset:
            texture_data = hashfetch(tar_hash, httprange=(offset, length))
            return texture_data

def download_progressive(model, offset, length, refinements_read, num_refinements, previous_data):
    """Given a model, offset and length, download progressive hash data"""
    
    types = model.model_json['metadata']['types']
    type_dict = types[model.model_type]
    progressive_hash = type_dict['progressive_stream']

    data = hashfetch(progressive_hash, httprange=(offset, length))
    
    if previous_data is not None:
        data = previous_data + data

    refinements = pdae_utils.readPDAEPartial(data, refinements_read, num_refinements)
    
    return refinements
    

def load_into_bamfile(meshdata, subfiles, model):
    """Uses pycollada and panda3d to load meshdata and subfiles and
    write out to a bam file on disk"""

    if os.path.isfile(model.bam_file):
        print 'returning cached bam file'
        return model.bam_file

    mesh = load_mesh(meshdata, subfiles)
    model_name = model.model_json['full_path'].replace('/', '_')
    
    if model.model_type == 'progressive' and model.model_subtype == 'full':
        progressive_stream = model.model_json['metadata']['types']['progressive'].get('progressive_stream')
        if progressive_stream is not None:
            print 'LOADING PROGRESSIVE STREAM'
            data = model.prog_data
            try:
                mesh = add_back_pm.add_back_pm(mesh, StringIO(data), 100)
                print '-----'
                print 'SUCCESSFULLY ADDED BACK PM'
                print '-----'
            except:
                f = open(model.bam_file, 'w')
                f.close()
                raise

    print 'loading into bamfile', model_name, mesh
    scene_members = pandacore.getSceneMembers(mesh)
    print 'got scene members', model_name, mesh
    
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

    for geom, renderstate, mat4 in scene_members:
        node = GeomNode("primitive")
        node.addGeom(geom)
        if renderstate is not None:
            node.setGeomState(0, renderstate)
        geomPath = rotatePath.attachNewNode(node)
        geomPath.setMat(mat4)
        
    print 'created np', model_name, mesh

    if model.model_type != 'optimized_unflattened' and model.model_type != 'progressive':
        print 'ABOUT TO FLATTEN'
        rotatePath.flattenStrong()
        print 'DONE FLATTENING'
        
    print 'flattened', model_name, mesh
    
    wrappedNode = pandacore.centerAndScale(rotatePath)
    wrappedNode.setName(model_name)

    wrappedNode.writeBamFile(model.bam_file)
    print 'saved', model_name, mesh
    wrappedNode = None
    
    return model.bam_file
