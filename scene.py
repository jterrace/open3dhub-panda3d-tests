import open3dhub
import cPickle
import os

CURDIR = os.path.dirname(__file__)

def filter_non_progressive(models):
    """Filters out models that don't have a progressive version"""
    
    filtered = []
    
    for m in models:
        types = m['metadata']['types']
        if 'progressive' in types:
            filtered.append(m)
    
    return filtered

def filter_zero_progressive(models):
    """Filters out models that have zero triangles in the progressive stream"""
    
    filtered = []
    
    for m in models:
        progressive = m['metadata']['types']['progressive']
        if progressive['progressive_stream_num_triangles'] > 0:
            filtered.append(m)
    
    return filtered

def filter_large_triangles(models):
    """Filters out models that have a base number of triangles that is too large"""
    
    filtered = []
    
    for m in models:
        progressive = m['metadata']['types']['progressive']
        if 'metadata' in progressive and progressive['metadata']['num_triangles'] < 100000:
            filtered.append(m)
    
    return filtered

def filter_no_textures(models):
    """Filters out models that have no textures"""
    
    filtered = []
    
    for m in models:
        optimized = m['metadata']['types']['optimized']
        if 'metadata' in optimized and optimized['metadata']['num_images'] > 0:
            filtered.append(m)
    
    return filtered

def filter_too_complicated(models):
    """Filters out models that have too many draw calls"""
    
    filtered = []
    
    for m in models:
        optimized = m['metadata']['types']['optimized']
        if 'metadata' in optimized and optimized['metadata']['num_draw_calls'] < 100:
            filtered.append(m)
    
    return filtered

def filter_cityengine(models):
    """Filters out cityengine models that tahir uploaded"""
    
    filtered = []
    
    for m in models:
        if 'tahirazim/apiupload' not in m['base_path']:
            filtered.append(m)
    
    return filtered

BAD_LIST = set(['/ayyyeung/models/tree.dae',
                '/kittyvision/house21.dae',
                '/emily2e/models/apartment_smallLuxury.dae',
                '/echeslack/chess.dae',
                '/kittyvision/apartment1.dae',
                '/zhihongmax/RX_0_Unicorn_Gundam.dae',
                '/emily2e/models/roadblock.dae',
                '/kchung25/models/model.dae',
                '/bmistree/models/EarlyGalleon1.dae',
                '/emily2e/models/familyfare.dae',
                '/cedar/McLaren_F1_LM.dae'])
def filter_bad_list(models):
    """Filters out models that are known to be bad"""
    
    filtered = []
    for m in models:
        if m['base_path'] not in BAD_LIST:
            filtered.append(m)
    return filtered

def filter_non_panda3d(models):
    """Filters out models that don't have panda3d files generated"""
    
    filtered = []
    for m in models:
        types = m['metadata']['types']
        if 'progressive' not in types:
            continue
        progressive = types['progressive']
        if 'panda3d_base_bam' in progressive and 'panda3d_full_bam' in progressive:
            filtered.append(m)
    return filtered

def filter_non_big(models):
    filtered = []
    for m in models:
        optimized = m['metadata']['types']['optimized']
        num_triangles = optimized['metadata']['num_triangles']
        if num_triangles > 20000:
            filtered.append(m)
    return filtered

def filter_non_small(models):
    filtered = []
    for m in models:
        optimized = m['metadata']['types']['optimized']
        num_triangles = optimized['metadata']['num_triangles']
        if num_triangles <= 20000:
            filtered.append(m)
    return filtered

def filter_for_demo(models):
    """Filters out models that we don't want to use for the demo"""
    
    models = filter_non_progressive(models)
    models = filter_zero_progressive(models)
    models = filter_large_triangles(models)
    models = filter_no_textures(models)
    models = filter_too_complicated(models)
    models = filter_bad_list(models)
    
    return models

def get_demo_models(force=False):
    """Returns demo models. Loads from a cache unless force is set to True"""
    
    demo_model_file = os.path.join(CURDIR, ".demo-models")
    if not force and os.path.isfile(demo_model_file):
        return cPickle.load(open(demo_model_file, 'r'))
    
    all_cdn_models = open3dhub.get_list(100000)
    demo_models = filter_for_demo(all_cdn_models)
    cPickle.dump(demo_models, open(demo_model_file, 'w'), protocol=cPickle.HIGHEST_PROTOCOL)
    
    return demo_models

def get_progressive_models(force=False):
    """Returns all models that have a progressive format."""
    
    all_cdn_models = open3dhub.get_list(100000)
    progressive_models = filter_non_progressive(all_cdn_models)
    progressive_models = filter_bad_list(progressive_models)
    #progressive_models = filter_non_panda3d(progressive_models)
    progressive_models = filter_large_triangles(progressive_models)
    progressive_models = filter_too_complicated(progressive_models)
    progressive_models = filter_cityengine(progressive_models)
    
    
    return progressive_models

def get_all_models(force=False):
    """Returns all models. Loads from a cache unless force is set to True"""
    
    all_model_file = os.path.join(CURDIR, ".all-models")
    if not force and os.path.isfile(all_model_file):
        return cPickle.load(open(all_model_file, 'r'))
    
    all_cdn_models = open3dhub.get_list(100000)
    cPickle.dump(all_cdn_models, open(all_model_file, 'w'), protocol=cPickle.HIGHEST_PROTOCOL)
    
    return all_cdn_models
