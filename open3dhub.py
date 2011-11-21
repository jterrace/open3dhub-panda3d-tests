try: import json
except ImportError: import simplejson as json
import urllib2
import posixpath
from StringIO import StringIO
import gzip

import collada

BASE_URL = 'http://open3dhub.com'
BROWSE_URL = BASE_URL + '/api/browse'
DOWNLOAD_URL = BASE_URL + '/download'
DNS_URL = BASE_URL + '/dns'

def urlfetch(url):
    """Fetches the given URL and returns data from it.
    Will take care of gzip if enabled on server."""
    
    request = urllib2.Request(url)
    request.add_header('Accept-encoding', 'gzip')
    response = urllib2.urlopen(request)
    if response.info().get('Content-Encoding') == 'gzip':
        buf = StringIO(response.read())
        response = gzip.GzipFile(fileobj=buf)
    
    return response.read()

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

def get_mesh(model_json, type):
    """Given a model JSON dictionary and a type to load, returns a pycollada instance"""
    
    types = model_json['metadata']['types']
    if not type in types:
        return None
    
    type_dict = types[type]
    mesh_hash = type_dict['hash']
    
    print 'Downloading mesh', model_json['base_path'], mesh_hash
    
    def inline_loader(filename):
        texture_path = posixpath.normpath(posixpath.join(model_json['base_path'], type, model_json['version_num'], filename))
        texture_url = DNS_URL + texture_path
        texture_json = json.loads(urlfetch(texture_url))
        texture_hash = texture_json['Hash']
        texture_data = urlfetch(DOWNLOAD_URL + '/' + texture_hash)
        return texture_data
    
    data = urlfetch(DOWNLOAD_URL + '/' + mesh_hash)
    
    mesh = collada.Collada(StringIO(urlfetch(DOWNLOAD_URL + '/' + mesh_hash)), aux_file_loader=inline_loader)
    
    #this will force loading of the textures too
    for img in mesh.images:
        img.data
    
    return mesh

def load_mesh(mesh_data, subfiles):
    """Given a downloaded mesh, return a collada instance"""
    
    def inline_loader(filename):
        return subfiles[posixpath.basename(filename)]
    
    mesh = collada.Collada(StringIO(mesh_data), aux_file_loader=inline_loader)
    
    #this will force loading of the textures too
    for img in mesh.images:
        img.data
    
    return mesh

def download_mesh(model_json, type):
    """Given a model JSON dictionary and a type to load, downloads and returns the main
    file data and a dictionary mapping its dependencies to their download data"""
    
    types = model_json['metadata']['types']
    if not type in types:
        return None
    
    type_dict = types[type]
    mesh_hash = type_dict['hash']
    
    print 'Downloading mesh', model_json['base_path'], mesh_hash
    
    def inline_loader(filename):
        texture_path = posixpath.normpath(posixpath.join(model_json['base_path'], type, model_json['version_num'], filename))
        texture_url = DNS_URL + texture_path
        texture_json = json.loads(urlfetch(texture_url))
        texture_hash = texture_json['Hash']
        texture_data = urlfetch(DOWNLOAD_URL + '/' + texture_hash)
        return texture_data
    
    data = urlfetch(DOWNLOAD_URL + '/' + mesh_hash)
    subfile_dict = {}
    
    for subfile in type_dict['subfiles']:
        splitpath = subfile.split('/')
        basename = splitpath[-2]
        
        texture_path = posixpath.normpath(posixpath.join(model_json['base_path'], type, model_json['version_num'], basename))
        texture_url = DNS_URL + texture_path
        texture_json = json.loads(urlfetch(texture_url))
        texture_hash = texture_json['Hash']
        texture_data = urlfetch(DOWNLOAD_URL + '/' + texture_hash)

        subfile_dict[basename] = texture_data
    
    return (data, subfile_dict)
