import json
import urllib2
import posixpath
from StringIO import StringIO
import gzip
import tempfile
import math
import os

import numpy
import collada
from meshtool.filters.panda_filters import pandacore
from panda3d.core import GeomNode, NodePath, Mat4

import load_scheduler

BASE_URL = 'http://open3dhub.com'
BROWSE_URL = BASE_URL + '/api/browse'
DOWNLOAD_URL = BASE_URL + '/download'
DNS_URL = BASE_URL + '/dns'

CURDIR = os.path.dirname(__file__)
TEMPDIR = os.path.join(CURDIR, '.temp_models')

def urlfetch(url, httprange=None):
    """Fetches the given URL and returns data from it.
    Will take care of gzip if enabled on server."""
    
    request = urllib2.Request(url)
    request.add_header('Accept-encoding', 'gzip')
    if httprange is not None:
        offset, length = httprange
        request.add_header('Range', 'bytes=%d-%d' % (offset, offset+length-1))
    response = urllib2.urlopen(request)
    if response.info().get('Content-Encoding') == 'gzip':
        buf = StringIO(response.read())
        response = gzip.GzipFile(fileobj=buf)
    
    return response.read()

def hashfetch(dlhash, httprange=None):
    """Fetches the given hash and returns data from it."""
    return urlfetch(DOWNLOAD_URL + '/' + dlhash, httprange)

def get_list(limit=20):
    """Returns a list of dictionaries containing model JSON"""
    
    next_start = ''
    all_items = []

    while len(all_items) < limit and next_start != None:
        models_js = json.loads(urlfetch(BROWSE_URL + '/' + next_start))
        next_start = models_js['next_start']
        
        models_js = models_js['content_items']
        all_items.extend(models_js)

    if len(all_items) > limit:
        all_items = all_items[0:limit]
        
    return all_items

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
    if not model.model_type in types:
        return None
    
    type_dict = types[model.model_type]
    
    mipmaps = type_dict.get('mipmaps')
    if mipmaps:
        mipmaps = dict((posixpath.basename(p), info) for p, info in mipmaps.iteritems())
    
    mesh_hash = type_dict['hash']
    
    print 'Downloading mesh', model.model_json['base_path'], mesh_hash
    
    data = hashfetch(mesh_hash)
    subfile_dict = {}
    
    texture_task_base = None
    
    for subfile in type_dict['subfiles']:
        splitpath = subfile.split('/')
        basename = splitpath[-2]
        
        if mipmaps is not None and basename in mipmaps:
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

            texture_data = hashfetch(tar_hash, httprange=(offset, length))
            subfile_dict[basename] = texture_data
            
            for mipmap in reversed(mipmap_levels):
                mipmap_pixels = mipmap['width'] * mipmap['height']
                if mipmap_pixels <= base_pixels:
                    break

                priority = math.sqrt(float(base_pixels) / mipmap_pixels)
                
                tex_dt = load_scheduler.TextureDownloadTask(model, mipmap['offset'], priority=model.solid_angle * priority)
                if texture_task_base is not None:
                    tex_dt.dependents.append(texture_task_base)
                texture_task_base = tex_dt
        
        else:
            texture_path = posixpath.normpath(posixpath.join(model.model_json['base_path'], model.model_type, model.model_json['version_num'], basename))
            texture_url = DNS_URL + texture_path
            texture_json = json.loads(urlfetch(texture_url))
            texture_hash = texture_json['Hash']
            texture_data = hashfetch(texture_hash)
    
            subfile_dict[basename] = texture_data
    
    load_task = load_scheduler.LoadTask(data, subfile_dict, model, priority=model.solid_angle)
    if texture_task_base is not None:
        load_task.dependents.append(texture_task_base)
    return [load_task]

def download_texture(model, download_offset):
    """Given a model and texture offset, downloads the texture"""
    
    types = model.model_json['metadata']['types']
    if not model.model_type in types:
        return None
    
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

def load_into_bamfile(meshdata, subfiles, model):
    """Uses pycollada and panda3d to load meshdata and subfiles and
    write out to a bam file on disk"""
    
    mesh = load_mesh(meshdata, subfiles)

    print 'got mesh', mesh
    scene_members = pandacore.getSceneMembers(mesh)
    
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

    rotatePath.flattenStrong()
    
    wrappedNode = pandacore.centerAndScale(rotatePath)
    wrappedNode.setPos(model.x, model.y, model.z)
    wrappedNode.setScale(model.scale, model.scale, model.scale)
    minPt, maxPt = wrappedNode.getTightBounds()
    zRange = math.fabs(minPt.getZ() - maxPt.getZ())
    wrappedNode.setPos(model.x, model.y, zRange / 2.0)
    wrappedNode.setName(model.model_json['base_path'].replace('/', '_'))
    
    bam_temp = tempfile.mktemp('.bam', dir=TEMPDIR)
    wrappedNode.writeBamFile(bam_temp)
    
    return bam_temp
