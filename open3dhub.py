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

def urlfetch(url, range=None):
    """Fetches the given URL and returns data from it.
    Will take care of gzip if enabled on server."""
    
    request = urllib2.Request(url)
    request.add_header('Accept-encoding', 'gzip')
    if range is not None:
        offset, length = range
        request.add_header('Range', 'bytes=%d-%d' % (offset, offset+length-1))
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
    
    mipmaps = type_dict.get('mipmaps')
    if mipmaps:
        mipmaps = dict((posixpath.basename(p), info) for p, info in mipmaps.iteritems())
    
    mesh_hash = type_dict['hash']
    
    print 'Downloading mesh', model_json['base_path'], mesh_hash
    
    data = urlfetch(DOWNLOAD_URL + '/' + mesh_hash)
    subfile_dict = {}
    
    for subfile in type_dict['subfiles']:
        splitpath = subfile.split('/')
        basename = splitpath[-2]
        
        if mipmaps is not None and basename in mipmaps:
            mipmap_levels = mipmaps[basename]['byte_ranges']
            tar_hash = mipmaps[basename]['hash']
            offset = 0
            length = 0
            for mipmap in mipmap_levels:
                offset = mipmap['offset']
                length = mipmap['length']
                if mipmap['width'] >= 128 or mipmap['height'] >= 128:
                    break

            texture_data = urlfetch(DOWNLOAD_URL + '/' + tar_hash, range=(offset, length))
            subfile_dict[basename] = texture_data
        
        else:
            texture_path = posixpath.normpath(posixpath.join(model_json['base_path'], type, model_json['version_num'], basename))
            texture_url = DNS_URL + texture_path
            texture_json = json.loads(urlfetch(texture_url))
            texture_hash = texture_json['Hash']
            texture_data = urlfetch(DOWNLOAD_URL + '/' + texture_hash)
    
            subfile_dict[basename] = texture_data
    
    return (data, subfile_dict)
